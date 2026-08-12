"""Pydantic request/response models.

Kept separate from `models.py` so the wire format can evolve independently of
the database schema.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import CallPurpose, CallStatus, CandidateSource
from app.phone import InvalidPhoneNumber, normalize_phone


class ApiModel(BaseModel):
    """Base for everything we serialize out of the ORM."""

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _stamp_utc(self) -> ApiModel:
        """Mark naive timestamps as UTC.

        Every timestamp is written in UTC, but SQLite has no timezone type and
        hands them back naive. Serialized without an offset, the browser would
        read them as local time and show call times hours off.
        """
        for name, value in self.__dict__.items():
            if isinstance(value, datetime) and value.tzinfo is None:
                object.__setattr__(self, name, value.replace(tzinfo=timezone.utc))
        return self

# --------------------------------------------------------------------------
# Screening questions
# --------------------------------------------------------------------------

QuestionType = Literal["text", "boolean", "number", "choice"]


class ScreeningQuestion(BaseModel):
    """One thing the voice agent must find out.

    `key` becomes the property name in the Hunar `result_schema`, so it is what
    the dashboard columns are keyed on. It must be a stable identifier.
    """

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    question: str = Field(min_length=3, max_length=500)
    type: QuestionType = "text"
    options: list[str] = Field(default_factory=list)

    @field_validator("options")
    @classmethod
    def _options_only_for_choice(cls, v: list[str], info: Any) -> list[str]:
        if v and info.data.get("type") != "choice":
            raise ValueError("options may only be set when type is 'choice'")
        return v


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = ""
    location: str = ""
    questions: list[ScreeningQuestion] = Field(default_factory=list)
    language: str = "ENGLISH"
    voice_persona: str = "NEHA"

    @field_validator("questions")
    @classmethod
    def _unique_keys(cls, v: list[ScreeningQuestion]) -> list[ScreeningQuestion]:
        keys = [q.key for q in v]
        if len(keys) != len(set(keys)):
            raise ValueError("question keys must be unique")
        return v


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    location: str | None = None
    questions: list[ScreeningQuestion] | None = None
    language: str | None = None
    voice_persona: str | None = None


class JobOut(ApiModel):
    id: str
    title: str
    description: str
    location: str
    questions: list[dict]
    hunar_agent_id: str | None
    language: str
    voice_persona: str
    created_at: datetime
    candidate_count: int = 0


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------


class CandidateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Length is checked by the normalizer, which explains itself in plain
    # language; a raw min_length error here would surface as "String should
    # have at least 8 characters".
    phone: str = Field(min_length=1, max_length=32)
    email: str | None = None
    job_id: str | None = None
    source: CandidateSource = CandidateSource.MANUAL
    source_metadata: dict = Field(default_factory=dict)

    @field_validator("phone")
    @classmethod
    def _normalize(cls, v: str) -> str:
        """Accept the number however it was typed; store it as E.164."""
        try:
            return normalize_phone(v)
        except InvalidPhoneNumber as exc:
            raise ValueError(str(exc)) from exc


class CandidateOut(ApiModel):
    id: str
    job_id: str | None
    name: str
    phone: str
    email: str | None
    source: CandidateSource
    source_metadata: dict
    created_at: datetime


# --------------------------------------------------------------------------
# Calls
# --------------------------------------------------------------------------


class CallCreate(BaseModel):
    candidate_id: str
    purpose: CallPurpose = CallPurpose.SCREENING


class CallOut(ApiModel):
    id: str
    request_id: str
    hunar_call_id: str | None
    purpose: CallPurpose
    status: CallStatus
    candidate_id: str
    job_id: str | None
    result: dict | None
    recording_url: str | None
    engagement_status: str | None
    answered_by: str | None
    call_ended_by: str | None
    duration_seconds: float | None
    retry_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    ended_at: datetime | None

    # Denormalised for the dashboard so the UI does not need three round-trips.
    candidate_name: str | None = None
    candidate_phone: str | None = None
    job_title: str | None = None


class HealthOut(BaseModel):
    status: str
    hunar_configured: bool
    dry_run_calls: bool
    public_base_url: str
    webhooks_reachable: bool
