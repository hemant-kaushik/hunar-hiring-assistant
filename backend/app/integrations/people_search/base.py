"""The shape of a people-search provider.

Providers differ wildly in query language and response format, so everything
above this layer deals only in `SearchFilters` and `PersonResult`. Swapping
People Data Labs for Apollo means writing one adapter, not touching the UI.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    """What we are looking for, in provider-neutral terms.

    Derived from a job description, then shown to the recruiter to edit --
    an automatically-derived filter that cannot be corrected is worse than
    no automation.
    """

    titles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    company_size: str | None = None
    limit: int = Field(default=5, ge=1, le=25)

    def is_empty(self) -> bool:
        return not (self.titles or self.skills or self.locations or self.seniority)


class PersonResult(BaseModel):
    """One person a provider returned.

    `phone` may be absent while `has_phone` is true: on People Data Labs' free
    tier, contact fields come back as booleans saying the data exists without
    revealing it. Modelling that explicitly is what lets the UI explain why
    someone cannot be called, instead of silently showing a blank.
    """

    external_id: str
    name: str
    headline: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    skills: list[str] = Field(default_factory=list)
    linkedin_url: str | None = None
    experience_years: float | None = None

    phone: str | None = None
    email: str | None = None
    has_phone: bool = False
    has_email: bool = False

    # The provider's untouched payload, stored on the candidate so a richer
    # profile view never needs a schema change.
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_callable(self) -> bool:
        return bool(self.phone)


class SearchOutcome(BaseModel):
    """Results plus how they were obtained.

    The UI states which source answered, because a demo silently backed by
    sample data would be misleading.
    """

    results: list[PersonResult]
    source: str  # "pdl" | "sample"
    provider_label: str
    notice: str | None = None


class PeopleSearchProvider(Protocol):
    name: str
    label: str

    async def search(self, filters: SearchFilters) -> list[PersonResult]: ...
