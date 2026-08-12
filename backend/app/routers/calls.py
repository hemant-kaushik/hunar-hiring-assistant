"""Trigger calls and read their results.

One router for every module: a call is discriminated by `purpose`, so Task 2's
outreach calls will list and render here without new endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.integrations.hunar import HunarError
from app.models import Call, CallPurpose, CallStatus, Candidate
from app.schemas import CallCreate, CallOut
from app.services import outreach, screening
from app.services.call_pipeline import CallNotAllowed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calls", tags=["calls"])


def _to_out(call: Call) -> CallOut:
    out = CallOut.model_validate(call)
    out.candidate_name = call.candidate.name if call.candidate else None
    out.candidate_phone = call.candidate.phone if call.candidate else None
    out.job_title = call.job.title if call.job else None
    return out


async def _load(db: AsyncSession, call_id: str) -> Call:
    call = await db.scalar(
        select(Call)
        .where(Call.id == call_id)
        .options(selectinload(Call.candidate), selectinload(Call.job))
    )
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found")
    return call


@router.get("/", response_model=list[CallOut])
async def list_calls(
    job_id: str | None = None,
    candidate_id: str | None = None,
    purpose: CallPurpose | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[CallOut]:
    stmt = (
        select(Call)
        .options(selectinload(Call.candidate), selectinload(Call.job))
        .order_by(Call.created_at.desc())
    )
    if job_id:
        stmt = stmt.where(Call.job_id == job_id)
    if candidate_id:
        stmt = stmt.where(Call.candidate_id == candidate_id)
    if purpose:
        stmt = stmt.where(Call.purpose == purpose)
    return [_to_out(c) for c in (await db.scalars(stmt)).all()]


@router.post("/", response_model=CallOut, status_code=status.HTTP_201_CREATED)
async def start_call(payload: CallCreate, db: AsyncSession = Depends(get_db)) -> CallOut:
    """Place an outbound call. Task 1 screens; other purposes land here later."""
    candidate = await db.scalar(
        select(Candidate)
        .where(Candidate.id == payload.candidate_id)
        .options(selectinload(Candidate.job))
    )
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")

    if payload.purpose is CallPurpose.ATTENDANCE_CHECKIN:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "Attendance check-in calls are not available yet.",
        )
    if candidate.job is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This person is not attached to a role, so there is nothing to call about.",
        )

    # Same pipeline either way; only the agent and the conversation differ.
    start = (
        outreach.start_outreach_call
        if payload.purpose is CallPurpose.OUTREACH
        else screening.start_screening_call
    )

    try:
        call = await start(db, candidate, candidate.job)
    except CallNotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except HunarError as exc:
        # 402 means the voice minutes are exhausted -- worth its own message,
        # it is the likeliest failure on a trial account and "try again later"
        # would be misleading advice.
        if exc.is_quota_error:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                "The calling account has run out of voice minutes, so no more calls "
                "can be placed until it is topped up.",
            ) from exc
        logger.warning("Hunar refused call for candidate %s: %s", candidate.id, exc.message)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"The call could not be placed. {exc.message}",
        ) from exc

    return _to_out(await _load(db, call.id))


@router.get("/{call_id}", response_model=CallOut)
async def get_call(call_id: str, db: AsyncSession = Depends(get_db)) -> CallOut:
    return _to_out(await _load(db, call_id))


@router.post("/{call_id}/refresh", response_model=CallOut)
async def refresh_call(call_id: str, db: AsyncSession = Depends(get_db)) -> CallOut:
    """Poll Hunar for this call's current state.

    Webhooks are the primary path; this exists for when the backend is not
    publicly reachable (no tunnel) or a webhook was missed.
    """
    call = await _load(db, call_id)
    if call.status is CallStatus.SIMULATED:
        return _to_out(call)
    if not call.hunar_call_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This call was never placed with Hunar")

    try:
        await screening.refresh_call_status(db, call)
    except HunarError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    return _to_out(await _load(db, call_id))
