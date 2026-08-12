"""Tests for Task 2: JD parsing, provider adapters, and outreach."""

from __future__ import annotations

import pytest

from app.integrations.people_search import search_people
from app.integrations.people_search.base import SearchFilters
from app.integrations.people_search.pdl import PDLProvider, build_query, map_person
from app.integrations.people_search.sample import SampleProvider
from app.models import Job
from app.services.jd_parser import parse_job_description
from app.services.outreach import build_agent_payload as build_outreach_payload
from app.services.screening import build_agent_payload as build_screening_payload

SAMPLE_JD = """
Senior Backend Engineer

We are hiring a Senior Backend Engineer to join our platform team in Bengaluru.

You will work with Python, FastAPI and PostgreSQL, deploying to AWS with Docker.
Experience with Kubernetes is a plus. 5+ years of experience required.
"""


# --------------------------------------------------------------------------
# JD parsing
# --------------------------------------------------------------------------


def test_parses_title_skills_location_and_seniority():
    parsed = parse_job_description(SAMPLE_JD)
    assert "backend engineer" in parsed.titles
    assert {"python", "fastapi", "postgresql", "aws", "docker"} <= set(parsed.skills)
    assert parsed.locations == ["bengaluru"]
    assert parsed.seniority == ["senior"]


def test_multi_word_skills_are_not_split():
    """'machine learning' must not be reported as a bare 'learning' match, and
    'node.js' must not also match as something else."""
    parsed = parse_job_description("ML role using machine learning and node.js daily.")
    assert "machine learning" in parsed.skills
    assert "node.js" in parsed.skills


def test_regex_characters_in_skills_do_not_crash():
    """'c++' and 'ci/cd' are regex-significant; they must be escaped."""
    parsed = parse_job_description("Systems role: c++ required, plus ci/cd ownership.")
    assert "c++" in parsed.skills
    assert "ci/cd" in parsed.skills


def test_historical_city_names_are_canonicalised():
    """Providers index the current spelling, so searching 'Bangalore' must
    still find people listed under 'Bengaluru'."""
    assert parse_job_description("Backend role in Bangalore").locations == ["bengaluru"]
    assert parse_job_description("Sales role in Gurgaon").locations == ["gurugram"]


def test_unknown_role_falls_back_to_the_first_line():
    parsed = parse_job_description("Chief Vibes Officer\n\nSomething unusual.")
    assert parsed.titles == ["Chief Vibes Officer"]


def test_seniority_takes_the_most_senior_match():
    parsed = parse_job_description("Engineering Manager leading senior engineers")
    assert parsed.seniority == ["manager"]


# --------------------------------------------------------------------------
# PDL adapter
# --------------------------------------------------------------------------


def test_query_requires_location_but_only_prefers_skills():
    """Requiring every skill returns nobody, which reads as a broken search;
    the wrong country is simply wrong."""
    query = build_query(
        SearchFilters(titles=["backend engineer"], skills=["python", "aws"], locations=["pune"])
    )
    bool_query = query["query"]["bool"]
    assert bool_query["minimum_should_match"] == 1
    assert len(bool_query["should"]) == 3  # 1 title + 2 skills
    assert bool_query["must"]  # location is required


def test_empty_filters_produce_a_valid_query():
    assert build_query(SearchFilters()) == {"query": {"match_all": {}}}


def test_redacted_contacts_are_reported_as_existing_but_hidden():
    """PDL's free tier returns `true` instead of a number. That is not the same
    as having no number, and the UI needs to tell them apart."""
    person = map_person(
        {"id": "x", "full_name": "Asha Rao", "mobile_phone": True, "work_email": True}
    )
    assert person.phone is None and person.has_phone is True
    assert person.email is None and person.has_email is True
    assert person.is_callable is False


def test_real_contacts_are_read_from_strings_lists_and_objects():
    person = map_person(
        {
            "id": "y",
            "full_name": "Ravi K",
            "phone_numbers": [{"number": "+919812345678"}],
            "emails": ["ravi@example.com"],
        }
    )
    assert person.phone == "+919812345678" and person.is_callable
    assert person.email == "ravi@example.com"


def test_missing_contacts_are_neither_present_nor_hidden():
    person = map_person({"id": "z", "full_name": "No Contact"})
    assert person.phone is None and person.has_phone is False


# --------------------------------------------------------------------------
# Sample provider
# --------------------------------------------------------------------------


async def test_sample_provider_filters_by_location_and_skill():
    results = await SampleProvider().search(
        SearchFilters(titles=["backend engineer"], skills=["python"], locations=["bengaluru"])
    )
    assert results
    assert all("bengaluru" in r.location.lower() for r in results)


async def test_sample_provider_respects_the_limit():
    results = await SampleProvider().search(SearchFilters(skills=["python"], limit=2))
    assert len(results) == 2


async def test_no_sample_profile_has_a_hardcoded_number(monkeypatch):
    """Inventing phone numbers risks putting a real stranger behind a Reach out
    button, so no profile carries one of its own."""
    from app.config import settings

    monkeypatch.setattr(settings, "sample_contact_phone", "")
    results = await SampleProvider().search(SearchFilters(limit=25))
    assert results
    assert all(r.phone is None for r in results)


async def test_demo_number_is_attached_only_to_contactable_profiles(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sample_contact_phone", "+919876543210")
    results = await SampleProvider().search(SearchFilters(limit=25))

    withheld = [r for r in results if not r.has_phone]
    callable_people = [r for r in results if r.phone]

    assert len(results) == 20
    # Five deliberately have no number, so the "add a number first" path is
    # always reachable in a demo.
    assert len(withheld) == 5
    assert len(callable_people) == 15
    assert all(r.phone == "+919876543210" for r in callable_people)


async def test_profiles_without_a_number_cannot_be_called(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sample_contact_phone", "+919876543210")
    results = await SampleProvider().search(SearchFilters(limit=25))
    assert all(not r.is_callable for r in results if not r.has_phone)


async def test_search_falls_back_to_sample_data_without_a_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "pdl_api_key", "")
    monkeypatch.setattr(settings, "people_search_provider", "auto")

    outcome = await search_people(SearchFilters(skills=["python"]))
    assert outcome.source == "sample"
    assert outcome.notice and "sample" in outcome.notice.lower()


async def test_quota_exhaustion_falls_back_instead_of_failing(monkeypatch):
    """Running out of credits mid-demo should degrade, not 500."""
    from app.config import settings
    from app.integrations.people_search.pdl import PeopleSearchError

    monkeypatch.setattr(settings, "pdl_api_key", "key")
    monkeypatch.setattr(settings, "people_search_provider", "pdl")

    async def boom(self, filters):
        raise PeopleSearchError("Out of credits", status_code=402)

    monkeypatch.setattr(PDLProvider, "search", boom)

    outcome = await search_people(SearchFilters(skills=["python"]))
    assert outcome.source == "sample"
    assert "credits" in outcome.notice


# --------------------------------------------------------------------------
# Call payload
# --------------------------------------------------------------------------


def test_guardrails_carry_every_required_field():
    """Regression: Hunar rejects `guardrails` unless allowed_days,
    earliest_call_time and last_call_time are all present. Sending a partial
    object fails validation rather than defaulting the rest."""
    from app.models import Call, Candidate
    from app.services.call_pipeline import build_call_payload

    payload = build_call_payload(
        Call(request_id="req-1"),
        Candidate(name="Asha", phone="+919876543210"),
        Job(title="Backend Engineer", location="Pune", questions=[]),
        "agent-1",
    )
    guardrails = payload["guardrails"]
    assert set(guardrails) == {"allowed_days", "earliest_call_time", "last_call_time"}
    assert guardrails["allowed_days"]  # never empty
    assert set(guardrails["allowed_days"]) <= {
        "MON",
        "TUE",
        "WED",
        "THU",
        "FRI",
        "SAT",
        "SUN",
    }
    assert payload["timezone"]


def test_calling_window_is_clamped_to_what_the_provider_accepts(monkeypatch):
    """Regression: Hunar rejects the whole call for a window outside
    08:00-21:00 ("Minimum allowed earliest_call_time is 08:00"). A too-wide
    setting must narrow the hours, not break every call."""
    from app.config import settings
    from app.services.call_pipeline import calling_window

    monkeypatch.setattr(settings, "earliest_call_time", "00:00")
    monkeypatch.setattr(settings, "latest_call_time", "23:59")

    window = calling_window()
    assert window["earliest_call_time"] == "08:00"
    assert window["last_call_time"] == "21:00"


def test_a_narrower_window_than_the_providers_is_respected(monkeypatch):
    """Clamping must not widen a deliberately conservative policy."""
    from app.config import settings
    from app.services.call_pipeline import calling_window

    monkeypatch.setattr(settings, "earliest_call_time", "10:00")
    monkeypatch.setattr(settings, "latest_call_time", "18:00")

    window = calling_window()
    assert window["earliest_call_time"] == "10:00"
    assert window["last_call_time"] == "18:00"


# --------------------------------------------------------------------------
# Outreach
# --------------------------------------------------------------------------


def test_outreach_prompt_differs_from_screening():
    """The two conversations must not be interchangeable: one assumes the
    person applied, the other is a cold call."""
    job = Job(title="Backend Engineer", description="Python.", location="Pune", questions=[])
    outreach = build_outreach_payload(job)
    screening = build_screening_payload(job)

    assert outreach["agent_prompt"] != screening["agent_prompt"]
    assert "not applied" in outreach["agent_prompt"].lower()
    assert "unsolicited" in outreach["agent_prompt"].lower()
    assert outreach["name"].startswith("Outreach")


def test_outreach_schema_captures_interest_and_callback_time():
    job = Job(title="Backend Engineer", questions=[])
    props = build_outreach_payload(job)["result_schema"]["properties"]
    assert props["interested"]["type"] == "boolean"
    assert "best_time_to_talk" in props
    assert "open_to_opportunity" in props


def test_outreach_keeps_role_specific_questions():
    job = Job(
        title="Backend Engineer",
        questions=[{"key": "years_exp", "question": "Years of Python?", "type": "number"}],
    )
    payload = build_outreach_payload(job)
    assert "years_exp" in payload["result_schema"]["properties"]
    assert "Years of Python?" in payload["agent_prompt"]


@pytest.mark.parametrize("phone", ["", "   ", None])
async def test_someone_without_a_number_cannot_be_called(phone):
    """Sourced profiles routinely lack a number; that must read as an
    explainable state, not a crash."""
    from app.services.call_pipeline import CallNotAllowed, assert_number_allowed

    with pytest.raises(CallNotAllowed) as exc:
        assert_number_allowed(phone)
    assert "no phone number" in str(exc.value).lower()
