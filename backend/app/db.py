"""Async database engine and session management."""

import logging
from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base

logger = logging.getLogger(__name__)

# Query params libpq understands but asyncpg rejects as connect() kwargs.
_LIBPQ_ONLY_PARAMS = ("sslmode", "channel_binding", "options", "application_name")


def normalize_database_url(url: str) -> str:
    """Accept a Postgres URL as the hosting provider hands it out.

    Every managed Postgres console gives a libpq URL: a bare `postgresql://`
    scheme and `sslmode=`/`channel_binding=` params. SQLAlchemy reads that
    scheme as "use psycopg2" and asyncpg rejects those params outright, so
    pasting one verbatim fails at startup. Editing it by hand is a reliable way
    to corrupt the password instead, so the rewrite happens here.

    SQLite (local dev) and already-correct URLs pass through untouched.
    """
    parts = urlsplit(url)
    if not parts.scheme.startswith("postgres"):
        return url

    params = dict(parse_qsl(parts.query))
    # An internal/VPC URL carries no sslmode and needs no TLS; only ask for it
    # when the provider's URL said so.
    wants_ssl = params.get("sslmode", "") not in ("", "disable", "allow")
    for key in _LIBPQ_ONLY_PARAMS:
        params.pop(key, None)
    if wants_ssl:
        params.setdefault("ssl", "require")

    normalized = urlunsplit(
        ("postgresql+asyncpg", parts.netloc, parts.path, urlencode(params), "")
    )
    if normalized != url:
        # The password lives in netloc, so log the fact, never the URL.
        logger.info("Rewrote DATABASE_URL for asyncpg (scheme and/or query params)")
    return normalized


engine = create_async_engine(
    normalize_database_url(settings.database_url),
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
