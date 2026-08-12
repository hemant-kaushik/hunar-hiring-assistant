"""People Data Labs adapter.

Docs: https://docs.peopledatalabs.com/docs/reference-person-search-api

Two things about this provider drive the code below:

1. Search takes an Elasticsearch-style query, so `SearchFilters` has to be
   compiled into one.
2. On the free tier, contact fields come back as booleans -- `"mobile_phone": true`
   means "we have a number, but not on your plan". Each returned record costs a
   credit (100/month free), so `limit` is kept deliberately small.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.integrations.people_search.base import PersonResult, SearchFilters

logger = logging.getLogger(__name__)

PDL_SEARCH_URL = "https://api.peopledatalabs.com/v5/person/search"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class PeopleSearchError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    @property
    def is_quota_error(self) -> bool:
        # 402: out of credits. 429: rate limited (10 req/min on free).
        return self.status_code in (402, 429)


class PDLProvider:
    name = "pdl"
    label = "People Data Labs"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else settings.pdl_api_key

    async def search(self, filters: SearchFilters) -> list[PersonResult]:
        if not self.api_key:
            raise PeopleSearchError("No People Data Labs API key configured", status_code=401)

        params = {
            "query": _dumps(build_query(filters)),
            "size": filters.limit,
            "titlecase": "true",
        }
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                resp = await client.get(
                    PDL_SEARCH_URL, params=params, headers={"X-Api-Key": self.api_key}
                )
            except httpx.HTTPError as exc:
                raise PeopleSearchError(f"Could not reach People Data Labs: {exc}") from exc

        if resp.status_code >= 400:
            message = _error_message(resp)
            logger.warning("PDL search failed (%s): %s", resp.status_code, message)
            raise PeopleSearchError(message, status_code=resp.status_code)

        body = resp.json()
        return [map_person(record) for record in (body.get("data") or [])]


def build_query(filters: SearchFilters) -> dict:
    """Compile provider-neutral filters into PDL's Elasticsearch query.

    Titles and skills are `should` clauses -- requiring every skill to match
    returns almost nobody, which reads as "the search is broken". Location is a
    `must`, because a candidate in the wrong country is simply wrong.
    """
    should: list[dict[str, Any]] = []
    must: list[dict[str, Any]] = []

    for title in filters.titles:
        should.append({"match": {"job_title": title}})
    for skill in filters.skills:
        should.append({"term": {"skills": skill.lower()}})

    if filters.locations:
        must.append(
            {
                "bool": {
                    "should": [
                        {"match": {"location_name": loc}} for loc in filters.locations
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    if filters.seniority:
        must.append({"terms": {"job_title_levels": [s.lower() for s in filters.seniority]}})

    bool_query: dict[str, Any] = {}
    if must:
        bool_query["must"] = must
    if should:
        bool_query["should"] = should
        bool_query["minimum_should_match"] = 1

    return {"query": {"bool": bool_query}} if bool_query else {"query": {"match_all": {}}}


def map_person(record: dict) -> PersonResult:
    """Map a PDL record, treating redacted contact fields as "exists, hidden"."""
    phone, has_phone = _contact(record, "mobile_phone", "phone_numbers")
    email, has_email = _contact(record, "work_email", "emails", "personal_emails")

    experience = record.get("inferred_years_experience")
    try:
        experience = float(experience) if experience is not None else None
    except (TypeError, ValueError):
        experience = None

    return PersonResult(
        external_id=str(record.get("id") or record.get("pdl_id") or record.get("full_name")),
        name=(record.get("full_name") or "Unknown").strip(),
        headline=record.get("headline") or "",
        title=record.get("job_title") or "",
        company=record.get("job_company_name") or "",
        location=record.get("location_name") or "",
        skills=[s for s in (record.get("skills") or []) if isinstance(s, str)][:12],
        linkedin_url=_linkedin(record),
        experience_years=experience,
        phone=phone,
        email=email,
        has_phone=has_phone,
        has_email=has_email,
        raw=record,
    )


def _contact(record: dict, *fields: str) -> tuple[str | None, bool]:
    """Read a contact field that may be a value, a list, or a redaction flag.

    Returns (value_or_None, exists). `True` means the provider has the data but
    will not release it on this plan -- which is not the same as having none,
    and the UI says so.
    """
    exists = False
    for field in fields:
        value = record.get(field)
        if value is None:
            continue
        if value is True:
            exists = True
            continue
        if isinstance(value, str) and value.strip():
            return value.strip(), True
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip(), True
                if isinstance(item, dict):
                    inner = item.get("number") or item.get("address")
                    if isinstance(inner, str) and inner.strip():
                        return inner.strip(), True
            exists = exists or bool(value)
    return None, exists


def _linkedin(record: dict) -> str | None:
    url = record.get("linkedin_url") or record.get("linkedin_username")
    if not url:
        return None
    url = str(url)
    return url if url.startswith("http") else f"https://www.linkedin.com/in/{url}"


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return f"People Data Labs returned HTTP {resp.status_code}"
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, list):
            message = "; ".join(str(m) for m in message)
        if message:
            return str(message)
    return f"People Data Labs returned HTTP {resp.status_code}"


def _dumps(query: dict) -> str:
    import json

    return json.dumps(query)
