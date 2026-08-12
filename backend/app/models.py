"""Database models.

Design note (important for Tasks 2 and 3):
The voice-call pipeline is deliberately generic. `Call` is not a "screening call"
table -- it is a record of *any* Hunar conversation with *any* contact, discriminated
by `CallPurpose`. Task 1 (screening) writes rows with purpose=SCREENING; Task 2
(candidate outreach) will write purpose=OUTREACH; a Task 3 attendance system would
write purpose=ATTENDANCE_CHECKIN. The webhook receiver, the status polling, the
result storage and the dashboard queries are all shared, so adding a module means
adding a service + a router, not touching the call plumbing.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class CallPurpose(str, enum.Enum):
    """What a conversation is for. The discriminator that lets one pipeline
    serve every module of the assignment."""

    SCREENING = "SCREENING"  # Task 1: screen a candidate against a job
    OUTREACH = "OUTREACH"  # Task 2: cold outreach to a sourced person
    ATTENDANCE_CHECKIN = "ATTENDANCE_CHECKIN"  # Task 3: daily attendance roll-call


class CallStatus(str, enum.Enum):
    """Mirrors Hunar's call status values, plus local-only states."""

    # Local-only
    PENDING = "PENDING"  # created locally, not yet sent to Hunar
    SIMULATED = "SIMULATED"  # dry-run; no real call placed
    # Hunar values
    NOT_STARTED = "NOT_STARTED"
    SCHEDULED = "SCHEDULED"
    INITIATED = "INITIATED"
    RINGING = "RINGING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    NOT_CONNECTED = "NOT_CONNECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in {
            CallStatus.COMPLETED,
            CallStatus.NOT_CONNECTED,
            CallStatus.CANCELLED,
            CallStatus.FAILED,
            CallStatus.SIMULATED,
        }


class CandidateSource(str, enum.Enum):
    MANUAL = "MANUAL"  # typed into the UI
    CSV = "CSV"  # bulk upload
    PDL = "PDL"  # Task 2: People Data Labs search
    APOLLO = "APOLLO"  # Task 2: alternate provider


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


class Job(Base):
    """A role being hired for. Owns the screening questions and the Hunar agent
    that was provisioned to ask them."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(200), default="")

    # Screening questions, as a list of
    # {"key","question","type","options"?} dicts. Drives both the agent prompt
    # and the result_schema we hand to Hunar.
    questions: Mapped[list] = mapped_column(JSON, default=list)

    # The Hunar agent provisioned for this job. Created lazily on first call so
    # a job can be drafted without burning an agent slot.
    hunar_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str] = mapped_column(String(32), default="ENGLISH")
    voice_persona: Mapped[str] = mapped_column(String(32), default="NEHA")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    candidates: Mapped[list[Candidate]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    calls: Mapped[list[Call]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Candidate(Base):
    """A person we might call. Job is optional so Task 2 can store people
    sourced from a search before they are attached to a role."""

    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)  # E.164
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)

    source: Mapped[CandidateSource] = mapped_column(
        Enum(CandidateSource, native_enum=False, length=32),
        default=CandidateSource.MANUAL,
    )
    # Provider payload (PDL profile, LinkedIn URL, headline...) kept verbatim so
    # Task 2 can render rich profiles without a schema migration.
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    job: Mapped[Job | None] = relationship(back_populates="candidates")
    calls: Mapped[list[Call]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class Call(Base):
    """One Hunar conversation. Shared by every module -- see the module docstring."""

    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # `request_id` is our correlation handle: we generate it, send it to Hunar,
    # and Hunar echoes it back on every webhook. It is how an inbound webhook
    # finds its row without trusting the body's call_id alone.
    request_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=_uuid
    )
    hunar_call_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    purpose: Mapped[CallPurpose] = mapped_column(
        Enum(CallPurpose, native_enum=False, length=32), default=CallPurpose.SCREENING
    )
    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, native_enum=False, length=32), default=CallStatus.PENDING
    )

    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # ---- Outcome, filled in by webhooks ----
    # Structured answers extracted by Hunar per the agent's result_schema.
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    engagement_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    answered_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    call_ended_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    candidate: Mapped[Candidate] = relationship(back_populates="calls")
    job: Mapped[Job | None] = relationship(back_populates="calls")


class WebhookEvent(Base):
    """Append-only log of every webhook Hunar sends us.

    Kept even when signature verification fails, so a failed demo can be
    debugged after the fact and so there is an audit trail of what the vendor
    actually sent.
    """

    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(64), default="unknown", index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    hunar_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    signature_valid: Mapped[bool] = mapped_column(default=False)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
