"""Task 2 -- reaching out to someone who did not apply.

Deliberately a different conversation from screening. A screening call assumes
the person applied and expects to be assessed; an outreach call reaches someone
mid-day who has never heard of the company. So the agent leads with who it is
and why it is calling, asks permission to continue, and treats "not interested"
as a perfectly good outcome to record and end on.

Everything below the conversation is shared with screening: same call creation,
same webhooks, same result storage, same dashboard. Only the prompt, the
questions and the purpose differ.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Call, CallPurpose, Candidate, Job
from app.services import agents, call_pipeline, screening

logger = logging.getLogger(__name__)

# Asked on every outreach call, whatever the role. Interest and a callback time
# are the only things a first contact really needs to establish.
BASE_OUTREACH_FIELDS = {
    "interested": {
        "type": "boolean",
        "description": (
            "true if the person wants to hear more or take a next step, false if they "
            "declined or are not open to a move right now"
        ),
    },
    "current_role": {
        "type": "string",
        "description": "What the person says they currently do, in their own words",
    },
    "open_to_opportunity": {
        "type": "string",
        "description": (
            "What they said about being open to a new role -- including conditions such "
            "as 'only fully remote' or 'not before March'"
        ),
    },
    "best_time_to_talk": {
        "type": "string",
        "description": "When they asked to be contacted again, if they said anything",
    },
    "summary": {
        "type": "string",
        "description": "Two or three sentences summarising how the conversation went",
    },
}


def build_result_schema(job: Job) -> dict:
    """Outreach's own fields, plus any role-specific questions the job defines."""
    schema = screening.build_result_schema(list(job.questions or []))
    properties = dict(schema.get("properties") or {})
    for key, prop in BASE_OUTREACH_FIELDS.items():
        properties.setdefault(key, dict(prop))
    return {"type": "object", "properties": properties}


def build_agent_payload(job: Job) -> dict:
    """The Hunar agent that makes first contact for this role."""
    questions = list(job.questions or [])
    role_questions = "\n".join(
        f"- {q.get('question', '')}" for q in questions if q.get("question")
    )

    location_line = f" The role is based in {job.location}." if job.location else ""
    description_block = (
        f"\n\nAbout the role:\n{job.description.strip()}" if job.description else ""
    )
    optional_questions = (
        f"\n\nOnly if they are interested, and only as many as the conversation "
        f"comfortably allows:\n{role_questions}"
        if role_questions
        else ""
    )

    agent_prompt = (
        "You are a recruiter's assistant making a first approach to someone who has NOT "
        f"applied for anything. You are calling about a {job.title} role."
        f"{location_line}{description_block}\n\n"
        "How to run the conversation:\n"
        "- Open by saying who you are and that you are calling about a job opportunity. "
        "Be upfront that this is an unsolicited call.\n"
        "- Ask straight away whether it is a good time to talk for two minutes. If it is "
        "not, offer to call back, ask when suits them, and end the call politely.\n"
        "- Briefly describe the role in a sentence or two. Do not read a script at them.\n"
        "- Ask whether they are open to hearing more. Their answer decides the call:\n"
        "  * Not interested: thank them warmly, confirm you will not call again, end. Do "
        "not attempt to persuade them.\n"
        "  * Interested: ask about their current role and what they would want in a move.\n"
        "- Never pressure anyone, never imply they applied, and never claim a mutual "
        "connection or referral you were not told about.\n"
        "- If they ask how you got their number, say their professional profile is "
        "publicly listed and offer to remove them from the list.\n"
        "- Never invent salary figures, benefits or interview details. Say a recruiter "
        "will follow up with specifics.\n"
        "- Keep it short. A good outreach call is two or three minutes."
        f"{optional_questions}"
    )

    return {
        "name": f"Outreach - {job.title}"[:64],
        "language": job.language or "ENGLISH",
        "voice_persona": job.voice_persona or "NEHA",
        "agent_prompt": agent_prompt,
        "objective": (
            f"Introduce the {job.title} role to a potential candidate who has not applied, "
            "find out whether they are open to it, and agree a next step if they are."
        ),
        "introduction": (
            f"Hi {{callee_name}}, I'm calling from a hiring team about a {job.title} "
            "opening. I know this is out of the blue -- is now a good moment for a quick two "
            "minutes?"
        ),
        "result_prompt": (
            "From the conversation transcript, extract the person's responses into the "
            "provided schema. Use only what they actually said -- never guess. If a "
            "question was not asked or not answered, omit that field entirely rather than "
            "writing placeholder text like 'NOT AVAILABLE'. Record answers in their own "
            "terms, keeping ranges and conditions as stated. For `interested`, use their "
            "own stated position on hearing more about the role."
        ),
        "result_schema": build_result_schema(job),
    }


async def ensure_agent(db: AsyncSession, job: Job) -> str:
    return await agents.ensure_agent(db, job, CallPurpose.OUTREACH, build_agent_payload)


async def start_outreach_call(db: AsyncSession, candidate: Candidate, job: Job) -> Call:
    """Place (or simulate) a first-contact call.

    Sourced profiles frequently arrive without a usable phone number, so the
    absence of one is a normal, explainable state rather than an error --
    the pipeline's guard says so in as many words.
    """
    return await call_pipeline.place_call(
        db,
        candidate,
        job,
        CallPurpose.OUTREACH,
        ensure_agent,
        simulate_extra={
            "current_role": "Senior engineer at a product company.",
            "open_to_opportunity": "Open to hearing more, prefers hybrid over fully remote.",
            "best_time_to_talk": "Weekday evenings after 6pm.",
        },
    )
