"""Job CRUD -- a role plus the questions its voice agent must ask."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Candidate, Job
from app.schemas import JobCreate, JobOut, JobUpdate
from app.services import screening

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])


async def _to_out(db: AsyncSession, job: Job) -> JobOut:
    count = await db.scalar(
        select(func.count()).select_from(Candidate).where(Candidate.job_id == job.id)
    )
    out = JobOut.model_validate(job)
    out.candidate_count = count or 0
    return out


async def _get_or_404(db: AsyncSession, job_id: str) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.get("/", response_model=list[JobOut])
async def list_jobs(db: AsyncSession = Depends(get_db)) -> list[JobOut]:
    jobs = (await db.scalars(select(Job).order_by(Job.created_at.desc()))).all()
    return [await _to_out(db, job) for job in jobs]


@router.post("/", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(payload: JobCreate, db: AsyncSession = Depends(get_db)) -> JobOut:
    job = Job(
        title=payload.title,
        description=payload.description,
        location=payload.location,
        questions=[q.model_dump() for q in payload.questions],
        language=payload.language,
        voice_persona=payload.voice_persona,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return await _to_out(db, job)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)) -> JobOut:
    return await _to_out(db, await _get_or_404(db, job_id))


@router.patch("/{job_id}", response_model=JobOut)
async def update_job(
    job_id: str, payload: JobUpdate, db: AsyncSession = Depends(get_db)
) -> JobOut:
    job = await _get_or_404(db, job_id)
    data = payload.model_dump(exclude_unset=True)
    if "questions" in data and data["questions"] is not None:
        data["questions"] = [dict(q) for q in data["questions"]]

    for field, value in data.items():
        if value is not None:
            setattr(job, field, value)
    await db.commit()
    await db.refresh(job)

    # Keep the provisioned agent in step with the edited questions. Best-effort:
    # editing a job locally must not fail because the vendor is unreachable.
    try:
        await screening.sync_agent(db, job)
    except Exception as exc:
        logger.warning("Could not sync Hunar agent for job %s: %s", job.id, exc)

    return await _to_out(db, job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)) -> None:
    job = await _get_or_404(db, job_id)
    await db.delete(job)
    await db.commit()
