"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.routers import calls, candidates, jobs, webhooks
from app.schemas import HealthOut

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if not settings.hunar_configured:
        logger.warning("HUNAR_API_KEY is not set -- live calls will fail.")
    if settings.dry_run_calls:
        logger.warning("DRY_RUN_CALLS is on -- calls are simulated, no phone will ring.")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Hiring Assistant",
        description=(
            "Voice-AI screening built on Hunar. One generic call pipeline serves "
            "screening, outreach and attendance modules, discriminated by CallPurpose."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(jobs.router)
    app.include_router(candidates.router)
    app.include_router(calls.router)
    app.include_router(webhooks.router)

    @app.get("/api/health", response_model=HealthOut, tags=["meta"])
    async def health() -> HealthOut:
        """Config visibility for the UI banner -- never returns the key itself."""
        public = settings.public_base_url
        return HealthOut(
            status="ok",
            hunar_configured=settings.hunar_configured,
            dry_run_calls=settings.dry_run_calls,
            public_base_url=public,
            # Hunar cannot reach localhost, so webhooks silently never arrive
            # without a tunnel. Surfacing it beats debugging an empty dashboard.
            webhooks_reachable=not (
                "localhost" in public or "127.0.0.1" in public or not public
            ),
        )

    return app


app = create_app()
