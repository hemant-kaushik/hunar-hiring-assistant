"""Async database engine and session management."""

import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create tables if they do not exist, then run any data backfills.

    Deliberately using create_all rather than Alembic: the schema is young and
    this is a time-boxed build. Migrations would be the first thing to add for
    a production deployment.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _backfill_agent_bindings()


async def _backfill_agent_bindings() -> None:
    """Move pre-existing screening agents into `agent_bindings`.

    Agents used to live on `jobs.hunar_agent_id`, before a role needed a
    different agent per call purpose. Idempotent, and cheap enough to run on
    every boot: without it, a database created before that change would
    re-provision agents it already has.
    """
    from sqlalchemy import select

    from app.models import AgentBinding, CallPurpose, Job

    async with SessionLocal() as session:
        jobs = (
            await session.scalars(select(Job).where(Job.hunar_agent_id.is_not(None)))
        ).all()
        if not jobs:
            return

        bound = set(
            (
                await session.scalars(
                    select(AgentBinding.job_id).where(
                        AgentBinding.purpose == CallPurpose.SCREENING
                    )
                )
            ).all()
        )
        added = 0
        for job in jobs:
            if job.id in bound:
                continue
            session.add(
                AgentBinding(
                    job_id=job.id,
                    purpose=CallPurpose.SCREENING,
                    hunar_agent_id=job.hunar_agent_id,
                )
            )
            added += 1
        if added:
            await session.commit()
            logger.info("Backfilled %d screening agent binding(s)", added)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session per request."""
    async with SessionLocal() as session:
        yield session
