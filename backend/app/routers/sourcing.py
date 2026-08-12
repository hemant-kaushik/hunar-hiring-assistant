"""Task 2 -- job description in, people out, reachout from the same pipeline."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.integrations.people_search import SearchFilters, search_people
from app.integrations.people_search.base import PersonResult
from app.models import Candidate, CandidateSource, Job
from app.schemas import CandidateOut
from app.services.jd_parser import ParsedJD, parse_job_description

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sourcing", tags=["sourcing"])


class ParseRequest(BaseModel):
    job_description: str = Field(min_length=10, max_length=20_000)
    limit: int = Field(default=5, ge=1, le=25)


class SearchRequest(SearchFilters):
    pass


class SearchResponse(BaseModel):
    results: list[PersonResult]
    source: str
    provider_label: str
    notice: str | None = None
    filters: SearchFilters


class ImportRequest(BaseModel):
    job_id: str
    people: list[PersonResult]


@router.post("/parse", response_model=ParsedJD)
async def parse(payload: ParseRequest) -> ParsedJD:
    """Read a pasted job description into search filters.

    Returned rather than applied, so the recruiter can correct them before any
    credits are spent on a search.
    """
    return parse_job_description(payload.job_description, limit=payload.limit)


@router.post("/search", response_model=SearchResponse)
async def search(filters: SearchRequest) -> SearchResponse:
    if filters.is_empty():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Add at least a job title, a skill or a location to search for.",
        )

    outcome = await search_people(filters)
    return SearchResponse(
        results=outcome.results,
        source=outcome.source,
        provider_label=outcome.provider_label,
        notice=outcome.notice,
        filters=filters,
    )


@router.post("/import", response_model=list[CandidateOut], status_code=status.HTTP_201_CREATED)
async def import_people(
    payload: ImportRequest, db: AsyncSession = Depends(get_db)
) -> list[Candidate]:
    """Save selected search results as contacts against a role.

    The provider's whole profile is kept in `source_metadata`, so the UI can
    show why someone matched without a schema change. Phone is left blank when
    the provider withheld it -- someone has to supply a number before anyone
    can be called, which is the point.
    """
    job = await db.get(Job, payload.job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if not payload.people:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select at least one person to add.")

    existing_ids = {
        c.source_metadata.get("external_id")
        for c in (
            await db.scalars(select(Candidate).where(Candidate.job_id == payload.job_id))
        ).all()
        if isinstance(c.source_metadata, dict)
    }

    created: list[Candidate] = []
    for person in payload.people:
        if person.external_id in existing_ids:
            continue  # already added to this role
        candidate = Candidate(
            job_id=payload.job_id,
            name=person.name,
            phone=person.phone or "",
            email=person.email,
            source=CandidateSource.PDL,
            source_metadata={
                "external_id": person.external_id,
                "headline": person.headline,
                "title": person.title,
                "company": person.company,
                "location": person.location,
                "skills": person.skills,
                "linkedin_url": person.linkedin_url,
                "experience_years": person.experience_years,
                "phone_withheld": person.has_phone and not person.phone,
                "profile": person.raw,
            },
        )
        db.add(candidate)
        created.append(candidate)

    if not created:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Everyone selected has already been added to this role."
        )

    await db.commit()
    for candidate in created:
        await db.refresh(candidate)
    return created
