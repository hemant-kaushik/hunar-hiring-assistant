"""Provider selection, with a fallback that keeps the app demonstrable.

People Data Labs is used when a key is configured. If it is missing, out of
credits, rate-limited or simply down, the search falls back to the bundled
sample dataset rather than showing an error page -- but the response always
says which source answered, so nobody mistakes sample profiles for live data.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.integrations.people_search.base import (
    PeopleSearchProvider,
    PersonResult,
    SearchFilters,
    SearchOutcome,
)
from app.integrations.people_search.pdl import PDLProvider, PeopleSearchError
from app.integrations.people_search.sample import SampleProvider

logger = logging.getLogger(__name__)

__all__ = [
    "PeopleSearchError",
    "PeopleSearchProvider",
    "PersonResult",
    "SearchFilters",
    "SearchOutcome",
    "search_people",
]


def _provider() -> PeopleSearchProvider:
    choice = (settings.people_search_provider or "auto").lower()
    if choice == "sample":
        return SampleProvider()
    if choice == "pdl" or (choice == "auto" and settings.pdl_api_key):
        return PDLProvider()
    return SampleProvider()


async def search_people(filters: SearchFilters) -> SearchOutcome:
    provider = _provider()

    if isinstance(provider, SampleProvider):
        return SearchOutcome(
            results=await provider.search(filters),
            source=provider.name,
            provider_label=provider.label,
            notice=(
                "Showing sample profiles. Add a People Data Labs API key to search "
                "real profiles."
            ),
        )

    try:
        results = await provider.search(filters)
    except PeopleSearchError as exc:
        logger.warning("Falling back to sample data: %s", exc.message)
        fallback = SampleProvider()
        notice = (
            "The people-search service is out of credits for this month, so these are "
            "sample profiles."
            if exc.is_quota_error
            else f"Couldn't reach the people-search service ({exc.message}), so these "
            "are sample profiles."
        )
        return SearchOutcome(
            results=await fallback.search(filters),
            source=fallback.name,
            provider_label=fallback.label,
            notice=notice,
        )

    notice = None
    if results and not any(r.phone for r in results):
        # The characteristic free-tier response: profiles are real, contact
        # details are withheld. Better said out loud than discovered at the
        # moment someone presses Call.
        notice = (
            "These profiles are real, but the data provider does not release phone "
            "numbers on this plan. Add a number yourself to reach anyone."
        )

    return SearchOutcome(
        results=results,
        source=provider.name,
        provider_label=provider.label,
        notice=notice,
    )
