"""Candidate CRUD.

`job_id` is optional here because Task 2 stores people sourced from a search
before they are attached to a role.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Candidate, CandidateSource, Job
from app.schemas import CandidateCreate, CandidateOut

router = APIRouter(prefix="/api/candidates", tags=["candidates"])

MAX_CSV_BYTES = 1_000_000


async def _assert_job_exists(db: AsyncSession, job_id: str | None) -> None:
    if job_id and await db.get(Job, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")


@router.get("/", response_model=list[CandidateOut])
async def list_candidates(
    job_id: str | None = None, db: AsyncSession = Depends(get_db)
) -> list[Candidate]:
    stmt = select(Candidate).order_by(Candidate.created_at.desc())
    if job_id:
        stmt = stmt.where(Candidate.job_id == job_id)
    return list((await db.scalars(stmt)).all())


@router.post("/", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    payload: CandidateCreate, db: AsyncSession = Depends(get_db)
) -> Candidate:
    await _assert_job_exists(db, payload.job_id)
    candidate = Candidate(**payload.model_dump())
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.post("/upload", response_model=list[CandidateOut], status_code=status.HTTP_201_CREATED)
async def upload_candidates(
    job_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> list[Candidate]:
    """Bulk-add candidates from a CSV with `name`, `phone` and optional `email`."""
    await _assert_job_exists(db, job_id)

    raw = await file.read()
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "CSV is too large")

    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not parse CSV: {exc}") from exc

    created: list[Candidate] = []
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        lower = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            payload = CandidateCreate(
                name=lower.get("name", ""),
                phone=lower.get("phone", ""),
                email=lower.get("email") or None,
                job_id=job_id,
                source=CandidateSource.CSV,
            )
        except ValueError as exc:
            errors.append(f"row {i}: {exc.errors()[0]['msg'] if hasattr(exc, 'errors') else exc}")
            continue
        candidate = Candidate(**payload.model_dump())
        db.add(candidate)
        created.append(candidate)

    if not created:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No valid rows found. Expected columns: name, phone, email (optional). "
            + ("; ".join(errors[:5]) if errors else ""),
        )

    await db.commit()
    for candidate in created:
        await db.refresh(candidate)
    return created


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: str, db: AsyncSession = Depends(get_db)) -> Candidate:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    return candidate


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(candidate_id: str, db: AsyncSession = Depends(get_db)) -> None:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    await db.delete(candidate)
    await db.commit()
