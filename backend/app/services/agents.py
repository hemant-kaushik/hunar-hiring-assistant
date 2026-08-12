"""Provisioning and updating the Hunar agent behind a (job, purpose) pair.

Screening and outreach are different conversations for the same role, so each
gets its own agent. Everything about *managing* those agents is identical
though, so it lives here and each module only supplies the payload that
describes how its agent should behave.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.hunar import HunarClient
from app.models import AgentBinding, CallPurpose, Job

logger = logging.getLogger(__name__)

PayloadBuilder = Callable[[Job], dict]


async def get_agent_id(db: AsyncSession, job_id: str, purpose: CallPurpose) -> str | None:
    return await db.scalar(
        select(AgentBinding.hunar_agent_id).where(
            AgentBinding.job_id == job_id, AgentBinding.purpose == purpose
        )
    )


async def ensure_agent(
    db: AsyncSession, job: Job, purpose: CallPurpose, build_payload: PayloadBuilder
) -> str:
    """Return the agent for this job and purpose, provisioning it on first use.

    Lazy on purpose: drafting a role or running a search should not create
    anything upstream.
    """
    existing = await get_agent_id(db, job.id, purpose)
    if existing:
        return existing

    created = await HunarClient().create_agent(build_payload(job))
    agent_id = _extract_id(created)
    if not agent_id:
        raise RuntimeError(f"Hunar did not return an agent id (got: {created!r})")

    db.add(AgentBinding(job_id=job.id, purpose=purpose, hunar_agent_id=agent_id))
    # Kept in step for the screening agent, which predates this table.
    if purpose is CallPurpose.SCREENING:
        job.hunar_agent_id = agent_id
    await db.commit()

    logger.info("Provisioned %s agent %s for job %s", purpose.value, agent_id, job.id)
    return agent_id


async def sync_agent(
    db: AsyncSession, job: Job, purpose: CallPurpose, build_payload: PayloadBuilder
) -> None:
    """Push an edited job's questions to an already-provisioned agent.

    Does nothing if this job never provisioned one for that purpose -- there is
    nothing upstream to keep in step yet.
    """
    agent_id = await get_agent_id(db, job.id, purpose)
    if not agent_id:
        return

    client = HunarClient()
    payload = build_payload(job)

    # Hunar rejects an update carrying `voice_persona` or `language` unless
    # `persona_name` comes with it. We never set a persona name ourselves, so
    # carry over whatever the agent already has.
    current = await client.get_agent(agent_id)
    persona_name = current.get("persona_name") or current.get("voice_name")
    if persona_name:
        payload["persona_name"] = persona_name
    else:
        # Nothing to preserve, so leave the voice settings alone entirely
        # rather than trip the same validation rule.
        payload.pop("voice_persona", None)
        payload.pop("language", None)

    await client.update_agent(agent_id, payload)
    logger.info("Synced %s agent %s for job %s", purpose.value, agent_id, job.id)


def _extract_id(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("id") or payload.get("agent_id")
    if not value and isinstance(payload.get("data"), dict):
        value = payload["data"].get("id") or payload["data"].get("agent_id")
    return str(value) if value else None
