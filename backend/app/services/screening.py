"""Task 1 -- candidate screening over a voice call.

The flow:
  1. A job carries a list of screening questions.
  2. Those questions are compiled into a Hunar agent: `agent_prompt` tells the
     agent how to conduct the conversation, `result_schema` tells it exactly
     what JSON to hand back. Hunar does the extraction, so there is no second
     LLM in this path.
  3. The agent is provisioned lazily -- the first time a job actually places a
     call -- so drafting a job costs nothing upstream.
  4. The call is placed with `callback_config` pointing at our webhook, and the
     `Call` row is updated as webhooks arrive.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.hunar import HunarClient
from app.models import Call, CallPurpose, CallStatus, Candidate, Job

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/api/webhooks/hunar"

# Two extras appended to every screening schema. They give the dashboard a
# human-readable line and a coarse yes/no even when the role-specific answers
# are sparse. Skipped if the job already defines a question with that key.
EXTRA_FIELDS = {
    "interested": {
        "type": "boolean",
        "description": (
            "true if the candidate expressed interest in moving forward with this "
            "role, false if they declined or are not looking"
        ),
    },
    "summary": {
        "type": "string",
        "description": "Two or three sentences summarising the candidate's responses",
    },
}


class CallNotAllowed(RuntimeError):
    """A safety guard refused to place this call."""


# --------------------------------------------------------------------------
# Compiling a job into a Hunar agent
# --------------------------------------------------------------------------


def build_result_schema(questions: list[dict]) -> dict:
    """Compile screening questions into the JSON schema Hunar extracts into.

    The question `key` becomes the property name, which is what the results
    dashboard keys its columns on -- so keys must stay stable once calls exist.
    """
    properties: dict[str, Any] = {}

    for q in questions:
        key = q.get("key")
        if not key:
            continue
        qtype = q.get("type", "text")
        prompt = q.get("question", "")

        asked = (
            f"The candidate's answer to: {prompt}"
            if prompt
            else f"The candidate's answer for {key}"
        )

        if qtype == "boolean":
            prop: dict[str, Any] = {"type": "boolean", "description": asked}
        elif qtype == "number":
            # Not a bare number type. People answer "four or five years" and
            # "2-3", and a strict number forces the extractor to drop the
            # answer entirely rather than record something imprecise.
            prop = {
                "type": ["number", "string"],
                "description": (
                    f"{asked} Use a plain number when the candidate gives one. If they "
                    "give a range or an approximation, record it as text exactly as they "
                    "said it (for example '4 to 5') rather than leaving this empty."
                ),
            }
        elif qtype == "choice" and q.get("options"):
            # Deliberately not a JSON Schema `enum`. A hard enum means any
            # answer outside the list -- "30 to 45 days" against buckets of
            # 15/30/60 -- is discarded, and the column shows blank as though
            # the question was never asked. Steering beats constraining here.
            options = ", ".join(str(o) for o in q["options"])
            prop = {
                "type": "string",
                "description": (
                    f"{asked} Prefer one of these when it genuinely fits: {options}. If the "
                    "candidate's answer falls between the options or does not match any of "
                    "them, record what they actually said (for example '30 to 45 days') "
                    "instead of leaving this empty or forcing it into the nearest option."
                ),
            }
        else:
            prop = {"type": "string", "description": asked}

        properties[key] = prop

    for key, prop in EXTRA_FIELDS.items():
        properties.setdefault(key, dict(prop))

    return {"type": "object", "properties": properties}


def build_agent_payload(job: Job) -> dict:
    """Everything Hunar needs to create the agent that screens for this job."""
    questions: list[dict] = list(job.questions or [])
    numbered = "\n".join(
        f"{i}. {q.get('question', '')}" for i, q in enumerate(questions, start=1)
    ) or "1. Ask about their current role and relevant experience."

    location_line = f" The role is based in {job.location}." if job.location else ""
    description_block = (
        f"\n\nAbout the role:\n{job.description.strip()}" if job.description else ""
    )

    agent_prompt = (
        f"You are a friendly, professional recruiting assistant screening candidates "
        f"for the role of {job.title}.{location_line}{description_block}\n\n"
        "How to run the conversation:\n"
        "- Greet the candidate by name and confirm you are speaking to the right person.\n"
        "- Say you are calling about the role and ask if it is a good time to talk for "
        "two or three minutes. If it is not, offer to call back and end politely.\n"
        "- Ask the screening questions below one at a time, in order. Wait for the "
        "answer before moving on.\n"
        "- If an answer is vague or incomplete, ask one short follow-up, then move on.\n"
        "- Never invent details about salary, benefits or the interview process. If you "
        "are asked something you were not told, say a recruiter will follow up.\n"
        "- Keep your turns short and conversational. Do not read out a script.\n"
        "- If the candidate is not interested, thank them warmly and end the call.\n"
        "- At the end, thank them and say the team will be in touch.\n\n"
        f"Screening questions:\n{numbered}"
    )

    result_prompt = (
        "From the conversation transcript, extract the candidate's answers into the "
        "provided schema. Use only what the candidate actually said -- never guess or "
        "fill in a plausible value. If a question was genuinely not asked or not "
        "answered, omit that field entirely. Do not write placeholder text such as "
        "'NOT AVAILABLE', 'N/A' or 'unknown' into a field -- an omitted field already "
        "means the answer is missing.\n"
        "Record answers in the candidate's own terms. When an answer is a range or an "
        "approximation -- '30 to 45 days', 'about four years', 'depends on the offer' -- "
        "keep it as they said it. Never drop an answer just because it does not fit a "
        "suggested option or a numeric format; a partial answer is far more useful than "
        "an empty field.\n"
        "For the `interested` field, use the candidate's own stated intent about moving "
        "forward with this role."
    )

    return {
        "name": f"Screening - {job.title}"[:64],
        "language": job.language or "ENGLISH",
        "voice_persona": job.voice_persona or "NEHA",
        "agent_prompt": agent_prompt,
        "objective": (
            f"Screen candidates for the {job.title} role by collecting answers to the "
            "screening questions, and gauge whether they want to move forward."
        ),
        "introduction": (
            f"Hi {{callee_name}}, this is a hiring assistant calling about the "
            f"{job.title} role. Is now a good time to talk for a couple of minutes?"
        ),
        "result_prompt": result_prompt,
        "result_schema": build_result_schema(questions),
    }


async def ensure_agent(db: AsyncSession, job: Job) -> str:
    """Return the job's Hunar agent id, provisioning it on first use."""
    if job.hunar_agent_id:
        return job.hunar_agent_id

    client = HunarClient()
    created = await client.create_agent(build_agent_payload(job))
    agent_id = _extract_id(created)
    if not agent_id:
        raise RuntimeError(f"Hunar did not return an agent id (got: {created!r})")

    job.hunar_agent_id = agent_id
    await db.commit()
    logger.info("Provisioned Hunar agent %s for job %s", agent_id, job.id)
    return agent_id


async def sync_agent(db: AsyncSession, job: Job) -> None:
    """Push an edited job's questions to its existing agent.

    Best-effort: a failure here must not block editing a job locally, so the
    caller logs and carries on. Nothing is provisioned if the job has never
    placed a call.
    """
    if not job.hunar_agent_id:
        return

    client = HunarClient()
    payload = build_agent_payload(job)

    # Hunar rejects an update carrying `voice_persona` or `language` unless
    # `persona_name` comes with it. We never set a persona name ourselves, so
    # carry over whatever the agent already has.
    current = await client.get_agent(job.hunar_agent_id)
    persona_name = current.get("persona_name") or current.get("voice_name")
    if persona_name:
        payload["persona_name"] = persona_name
    else:
        # Nothing to preserve, so leave the voice settings alone entirely
        # rather than trip the same validation rule.
        payload.pop("voice_persona", None)
        payload.pop("language", None)

    await client.update_agent(job.hunar_agent_id, payload)
    logger.info("Synced Hunar agent %s for job %s", job.hunar_agent_id, job.id)


# --------------------------------------------------------------------------
# Placing a call
# --------------------------------------------------------------------------


def assert_number_allowed(phone: str) -> None:
    """Decide whether this number may be dialled.

    A candidate with no phone number simply cannot be called -- that is the one
    hard rule. Beyond it, the restriction list is opt-in: leave
    `ALLOWED_TEST_NUMBERS` empty and any candidate can be called, which is the
    normal mode for screening people who applied. Fill it in and only those
    numbers are reachable, which is useful while testing so a mistyped number
    cannot ring a stranger.

    Dry-run mode remains the way to exercise the flow with no call at all.
    """
    if not phone or not phone.strip():
        raise CallNotAllowed("This candidate has no phone number, so there is nobody to call.")

    allowed = settings.allowed_test_number_list
    if allowed and phone not in allowed:
        raise CallNotAllowed(
            f"Calling is currently restricted to an approved list of numbers, and {phone} "
            "is not on it."
        )


def build_call_payload(call: Call, candidate: Candidate, job: Job, agent_id: str) -> dict:
    """The body for POST /calls/.

    All four callbacks point at one endpoint; the payload's `event_type` says
    which one it is. `request_id` is our own correlation handle -- Hunar echoes
    it on every webhook, so an inbound event finds its row without depending on
    having already stored the vendor's call id.
    """
    base = settings.public_base_url.rstrip("/")
    webhook_url = f"{base}{WEBHOOK_PATH}"

    return {
        "agent_id": agent_id,
        "callee_name": candidate.name,
        "mobile_number": candidate.phone,
        "request_id": call.request_id,
        "custom_data": {
            "job_title": job.title,
            "job_location": job.location or "",
            "candidate_name": candidate.name,
        },
        "callback_config": {
            "call_status_callback_url": webhook_url,
            "call_recording_callback_url": webhook_url,
            "call_result_callback_url": webhook_url,
            "call_summary_callback_url": webhook_url,
        },
    }


async def start_screening_call(db: AsyncSession, candidate: Candidate, job: Job) -> Call:
    """Create the local Call row and place (or simulate) the outbound call."""
    # Check the guard before writing anything: a refused call should leave no
    # trace, not a row stuck in PENDING that the UI reads as "in progress".
    if not settings.dry_run_calls:
        assert_number_allowed(candidate.phone)

    call = Call(
        candidate_id=candidate.id,
        job_id=job.id,
        purpose=CallPurpose.SCREENING,
        status=CallStatus.PENDING,
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    if settings.dry_run_calls:
        call.status = CallStatus.SIMULATED
        await db.commit()
        # Fill the result a few seconds later so the UI's polling and the
        # pending -> done transition are exercised exactly as in a live run.
        asyncio.create_task(_simulate_result(call.id, list(job.questions or [])))
        logger.info("DRY RUN: simulated screening call %s for %s", call.id, candidate.phone)
        return call

    # Provisioning is inside the try as well: an agent-creation failure is just
    # as much a failed call, and leaving the row PENDING would show in the UI as
    # a call still in progress that never resolves.
    try:
        agent_id = await ensure_agent(db, job)
        client = HunarClient()
        response = await client.create_call(build_call_payload(call, candidate, job, agent_id))
    except Exception as exc:
        call.status = CallStatus.FAILED
        call.error_message = str(exc)[:1000]
        await db.commit()
        raise

    call.hunar_call_id = _extract_id(response)
    call.status = _coerce_status(_field(response, "status")) or CallStatus.INITIATED
    await db.commit()
    await db.refresh(call)
    logger.info("Placed screening call %s (hunar id %s)", call.id, call.hunar_call_id)
    return call


async def refresh_call_status(db: AsyncSession, call: Call) -> Call:
    """Pull the latest state from Hunar.

    Webhooks are the primary path; this is the fallback for when the backend is
    not publicly reachable (no tunnel running) or a webhook was missed.
    """
    if not call.hunar_call_id or call.status == CallStatus.SIMULATED:
        return call

    client = HunarClient()
    data = await client.get_call(call.hunar_call_id)
    apply_call_fields(call, data)
    await db.commit()
    await db.refresh(call)
    return call


# --------------------------------------------------------------------------
# Applying vendor payloads to a Call row
# --------------------------------------------------------------------------


def apply_call_fields(call: Call, data: dict) -> None:
    """Copy whatever this payload carries onto the row.

    Shared by the webhook receiver and the polling fallback, and written to be
    partial-safe: Hunar's four webhook types each carry a different subset of
    fields, so anything absent is left untouched rather than nulled out.
    """
    if not isinstance(data, dict):
        return

    status = _coerce_status(data.get("status"))
    if status:
        call.status = status

    for field, attr in (
        ("recording_url", "recording_url"),
        ("engagement_status", "engagement_status"),
        ("answered_by", "answered_by"),
        ("call_ended_by", "call_ended_by"),
    ):
        value = data.get(field)
        if value is not None:
            setattr(call, attr, value)

    result = data.get("result")
    if isinstance(result, dict) and result:
        call.result = result

    duration = data.get("duration_seconds")
    if duration is not None:
        try:
            call.duration_seconds = float(duration)
        except (TypeError, ValueError):
            pass

    retry_count = data.get("retry_count")
    if isinstance(retry_count, int):
        call.retry_count = retry_count

    for field, attr in (("started_at", "started_at"), ("ended_at", "ended_at")):
        parsed = _parse_dt(data.get(field))
        if parsed:
            setattr(call, attr, parsed)

    call_id = data.get("call_id") or data.get("id")
    if call_id and not call.hunar_call_id:
        call.hunar_call_id = str(call_id)


# --------------------------------------------------------------------------
# Dry-run simulation
# --------------------------------------------------------------------------

_SAMPLE_TEXT = [
    "Yes, about four years now, mostly in a similar role.",
    "I can start within a month of an offer.",
    "That works for me.",
]


async def _simulate_result(call_id: str, questions: list[dict]) -> None:
    """Populate a simulated call with a plausible result after a short delay.

    Dry-run mode exists so a reviewer can walk the whole flow -- job, candidate,
    call, structured answers on the dashboard -- without a real phone ever
    ringing. Results are clearly marked so simulated rows are never mistaken
    for real ones.
    """
    from app.db import SessionLocal

    await asyncio.sleep(6)
    try:
        async with SessionLocal() as db:
            call = await db.get(Call, call_id)
            if call is None:
                return
            result: dict[str, Any] = {}
            for q in questions:
                key = q.get("key")
                if not key:
                    continue
                qtype = q.get("type", "text")
                if qtype == "boolean":
                    result[key] = True
                elif qtype == "number":
                    result[key] = random.choice([2, 3, 4, 5])
                elif qtype == "choice" and q.get("options"):
                    result[key] = q["options"][0]
                else:
                    result[key] = random.choice(_SAMPLE_TEXT)
            result["interested"] = True
            result["summary"] = "Example answers from a practice run. No call was placed."
            result["_simulated"] = True

            call.result = result
            call.duration_seconds = round(random.uniform(75, 160), 1)
            call.engagement_status = "ENGAGED"
            call.answered_by = "HUMAN"
            call.call_ended_by = "AGENT"
            call.ended_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception:  # background task: never let it die silently
        logger.exception("Simulated result generation failed for call %s", call_id)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _field(payload: Any, name: str) -> Any:
    """Read a field from a response that may or may not be wrapped in `data`."""
    if not isinstance(payload, dict):
        return None
    if name in payload:
        return payload[name]
    data = payload.get("data")
    if isinstance(data, dict):
        return data.get(name)
    return None


def _extract_id(payload: Any) -> str | None:
    value = _field(payload, "id") or _field(payload, "agent_id") or _field(payload, "call_id")
    return str(value) if value else None


def _coerce_status(value: Any) -> CallStatus | None:
    if not value:
        return None
    try:
        return CallStatus(str(value).upper())
    except ValueError:
        logger.warning("Unknown call status from Hunar: %r", value)
        return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
