"""The generic voice-call pipeline, shared by every module.

Nothing here knows what a call is *for*. Screening and outreach each supply an
agent and a set of questions; placing the call, tracking its status, applying
webhook payloads and simulating a dry run are identical either way, and a Task 3
attendance module would reuse this untouched.

This used to live inside `screening.py`, which made "the pipeline is generic"
true only in intent. Now it is true in the imports.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.hunar import HunarClient
from app.models import Call, CallPurpose, CallStatus, Candidate, Job

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/api/webhooks/hunar"

# Hunar enforces its own calling-hours floor and ceiling and rejects the whole
# call if you ask for anything outside them ("Minimum allowed earliest_call_time
# is 08:00", "Maximum allowed last_call_time is 21:00"). Verified against the
# live API; not documented in the OpenAPI spec. Clamping here means a
# misconfigured window narrows the hours rather than breaking every call.
PROVIDER_EARLIEST_CALL_TIME = "08:00"
PROVIDER_LATEST_CALL_TIME = "21:00"

AgentProvisioner = Callable[[AsyncSession, Job], Awaitable[str]]


class CallNotAllowed(RuntimeError):
    """A safety guard refused to place this call."""


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------


def assert_number_allowed(phone: str | None) -> None:
    """Decide whether this number may be dialled.

    A contact with no phone number simply cannot be called -- that is the one
    hard rule, and it is a routine state for someone found through a people
    search rather than an error. Beyond it, the restriction list is opt-in:
    leave `ALLOWED_TEST_NUMBERS` empty and anyone can be called; fill it in and
    only those numbers are reachable, which is useful while testing so a
    mistyped number cannot ring a stranger.
    """
    if not phone or not phone.strip():
        raise CallNotAllowed(
            "This person has no phone number on file, so there is nobody to call. "
            "Add a number to reach them."
        )

    allowed = settings.allowed_test_number_list
    if allowed and phone not in allowed:
        raise CallNotAllowed(
            f"Calling is currently restricted to an approved list of numbers, and {phone} "
            "is not on it."
        )


# --------------------------------------------------------------------------
# Placing a call
# --------------------------------------------------------------------------


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
        "timezone": settings.call_timezone,
        # Sent explicitly rather than relying on the provider's default. Without
        # this, a call placed at 10pm is silently queued for the morning and the
        # dashboard just shows SCHEDULED with no reason attached.
        # All three fields are required together -- omitting `allowed_days`
        # fails validation rather than defaulting to every day.
        "guardrails": calling_window(),
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


def calling_window() -> dict:
    """The guardrails block, kept inside what the provider will accept.

    All three fields are required together -- omitting `allowed_days` fails
    validation rather than defaulting to every day.
    """
    earliest = max(settings.earliest_call_time, PROVIDER_EARLIEST_CALL_TIME)
    latest = min(settings.latest_call_time, PROVIDER_LATEST_CALL_TIME)

    if earliest != settings.earliest_call_time or latest != settings.latest_call_time:
        logger.info(
            "Calling window %s-%s narrowed to %s-%s to stay within the provider's limits",
            settings.earliest_call_time,
            settings.latest_call_time,
            earliest,
            latest,
        )

    return {
        "allowed_days": settings.call_allowed_day_list,
        "earliest_call_time": earliest,
        "last_call_time": latest,
    }


async def place_call(
    db: AsyncSession,
    candidate: Candidate,
    job: Job,
    purpose: CallPurpose,
    ensure_agent: AgentProvisioner,
    *,
    simulate_extra: dict | None = None,
) -> Call:
    """Create the Call row and place (or simulate) the outbound call."""
    # Check the guard before writing anything: a refused call should leave no
    # trace, not a row stuck in PENDING that the UI reads as "in progress".
    if not settings.dry_run_calls:
        assert_number_allowed(candidate.phone)

    call = Call(
        candidate_id=candidate.id,
        job_id=job.id,
        purpose=purpose,
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
        asyncio.create_task(
            simulate_result(call.id, list(job.questions or []), extra=simulate_extra)
        )
        logger.info("DRY RUN: simulated %s call %s", purpose.value, call.id)
        return call

    # Provisioning is inside the try as well: an agent-creation failure is just
    # as much a failed call, and leaving the row PENDING would show in the UI as
    # a call still in progress that never resolves.
    try:
        agent_id = await ensure_agent(db, job)
        response = await HunarClient().create_call(
            build_call_payload(call, candidate, job, agent_id)
        )
    except Exception as exc:
        call.status = CallStatus.FAILED
        call.error_message = str(exc)[:1000]
        await db.commit()
        raise

    call.hunar_call_id = extract_id(response)
    call.status = coerce_status(field_value(response, "status")) or CallStatus.INITIATED
    await db.commit()
    await db.refresh(call)
    logger.info("Placed %s call %s (hunar id %s)", purpose.value, call.id, call.hunar_call_id)
    return call


async def refresh_call_status(db: AsyncSession, call: Call) -> Call:
    """Pull the latest state from Hunar.

    Webhooks are the primary path; this is the fallback for when the backend is
    not publicly reachable (no tunnel running) or a webhook was missed.
    """
    if not call.hunar_call_id or call.status == CallStatus.SIMULATED:
        return call

    data = await HunarClient().get_call(call.hunar_call_id)
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

    status = coerce_status(data.get("status"))
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
        parsed = parse_dt(data.get(field))
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


async def simulate_result(
    call_id: str, questions: list[dict], *, extra: dict | None = None
) -> None:
    """Populate a simulated call with a plausible result after a short delay.

    Dry-run mode exists so a reviewer can walk the whole flow -- role, contact,
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

            result.update(extra or {})
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
# Reading vendor responses
# --------------------------------------------------------------------------


def field_value(payload: Any, name: str) -> Any:
    """Read a field from a response that may or may not be wrapped in `data`."""
    if not isinstance(payload, dict):
        return None
    if name in payload:
        return payload[name]
    data = payload.get("data")
    if isinstance(data, dict):
        return data.get(name)
    return None


def extract_id(payload: Any) -> str | None:
    value = (
        field_value(payload, "id")
        or field_value(payload, "agent_id")
        or field_value(payload, "call_id")
    )
    return str(value) if value else None


def coerce_status(value: Any) -> CallStatus | None:
    if not value:
        return None
    try:
        return CallStatus(str(value).upper())
    except ValueError:
        logger.warning("Unknown call status from Hunar: %r", value)
        return None


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
