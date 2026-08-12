"""Task 1 -- screening a candidate who applied for a role.

What is specific to screening lives here: the questions become an
`agent_prompt` telling the agent how to run the conversation, and a
`result_schema` telling it exactly what JSON to hand back. Hunar does the
extraction, so there is no second LLM in this path.

Placing the call, tracking it and storing its result are not specific to
screening at all -- those live in `call_pipeline`.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Call, CallPurpose, Candidate, Job
from app.services import agents, call_pipeline
from app.services.call_pipeline import (  # re-exported: callers treat these as screening's API
    CallNotAllowed,
    apply_call_fields,
    assert_number_allowed,
    build_call_payload,
    refresh_call_status,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CallNotAllowed",
    "apply_call_fields",
    "assert_number_allowed",
    "build_agent_payload",
    "build_call_payload",
    "build_result_schema",
    "ensure_agent",
    "refresh_call_status",
    "start_screening_call",
    "sync_agent",
]

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
    """Return this job's screening agent, provisioning it on first use."""
    return await agents.ensure_agent(db, job, CallPurpose.SCREENING, build_agent_payload)


async def sync_agent(db: AsyncSession, job: Job) -> None:
    """Push an edited job's questions to its existing screening agent.

    Best-effort: a failure here must not block editing a job locally, so the
    caller logs and carries on.
    """
    await agents.sync_agent(db, job, CallPurpose.SCREENING, build_agent_payload)


async def start_screening_call(db: AsyncSession, candidate: Candidate, job: Job) -> Call:
    return await call_pipeline.place_call(
        db, candidate, job, CallPurpose.SCREENING, ensure_agent
    )
