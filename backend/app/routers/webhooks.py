"""Inbound Hunar webhooks.

All four Hunar callbacks (status, recording, result, summary) point at this one
endpoint; `event_type` in the body says which arrived. Every delivery is logged
to `webhook_events` before it is processed -- including ones that fail
verification -- so a failed demo can be debugged after the fact and there is an
audit trail of what the vendor actually sent.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.integrations.hunar import verify_webhook_signature
from app.models import Call, CallPurpose, WebhookEvent
from app.services import screening

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/hunar")
async def hunar_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    # The raw bytes are the signed payload -- re-serializing parsed JSON would
    # change key order and whitespace and break the HMAC.
    raw = await request.body()

    valid, reason = verify_webhook_signature(
        raw,
        request.headers.get("X-Hunar-Timestamp"),
        request.headers.get("X-Hunar-Signature"),
    )

    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {"raw": str(payload)[:2000]}

    event = WebhookEvent(
        event_type=str(payload.get("event_type") or "unknown"),
        request_id=payload.get("request_id"),
        hunar_call_id=payload.get("call_id"),
        payload=payload,
        signature_valid=valid,
    )
    db.add(event)

    if not valid:
        logger.warning("Rejected Hunar webhook: %s", reason)
        event.processing_error = f"signature rejected: {reason}"
        if settings.webhook_signature_required:
            await db.commit()
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)
        # Escape hatch for local debugging only -- see .env.example.
        logger.warning("Processing unverified webhook (WEBHOOK_SIGNATURE_REQUIRED=false)")

    try:
        matched = await _dispatch(db, payload)
        if not matched:
            event.processing_error = "no matching call row"
    except Exception as exc:  # never 500 at the vendor; it would retry forever
        logger.exception("Failed to process Hunar webhook")
        event.processing_error = str(exc)[:1000]

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _dispatch(db: AsyncSession, payload: dict) -> bool:
    """Route the event to the module that owns the call. Returns False if the
    call is unknown to us."""
    call = await _find_call(db, payload)
    if call is None:
        logger.warning(
            "Webhook for unknown call (request_id=%r call_id=%r)",
            payload.get("request_id"),
            payload.get("call_id"),
        )
        return False

    # The discriminator that keeps this receiver shared across modules: the
    # plumbing is identical, only the post-processing differs per purpose.
    if call.purpose is CallPurpose.SCREENING:
        screening.apply_call_fields(call, payload)
    else:
        # OUTREACH / ATTENDANCE_CHECKIN reuse the same field mapping until they
        # need their own post-processing.
        screening.apply_call_fields(call, payload)

    logger.info(
        "Webhook %s applied to call %s (status=%s)",
        payload.get("event_type"),
        call.id,
        call.status.value,
    )
    return True


async def _find_call(db: AsyncSession, payload: dict) -> Call | None:
    """Prefer our own `request_id` over the vendor's call id.

    We generate `request_id` and Hunar echoes it on every webhook, so a result
    that arrives before the POST /calls/ response was even stored still finds
    its row.
    """
    request_id = payload.get("request_id")
    if request_id:
        call = await db.scalar(select(Call).where(Call.request_id == str(request_id)))
        if call:
            return call

    call_id = payload.get("call_id") or payload.get("id")
    if call_id:
        return await db.scalar(select(Call).where(Call.hunar_call_id == str(call_id)))
    return None
