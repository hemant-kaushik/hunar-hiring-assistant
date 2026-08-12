"""Unit tests for the two pieces that are easy to get subtly wrong:
webhook signature verification and question -> result_schema compilation."""

from __future__ import annotations

import time

import pytest

from app.integrations.hunar import HunarClient, compute_signature, verify_webhook_signature
from app.models import Job
from app.phone import InvalidPhoneNumber, normalize_phone
from app.services.screening import CallNotAllowed, assert_number_allowed, build_result_schema

SECRET = "test-api-key"
BODY = b'{"event_type":"call_result_done","call_id":"abc","result":{"interested":true}}'


def _ts() -> str:
    return str(int(time.time()))


def test_valid_signature_accepted():
    ts = _ts()
    sig = compute_signature(SECRET, ts, BODY)
    assert verify_webhook_signature(BODY, ts, sig, SECRET) == (True, None)


def test_tampered_body_rejected():
    ts = _ts()
    sig = compute_signature(SECRET, ts, BODY)
    valid, reason = verify_webhook_signature(BODY + b" ", ts, sig, SECRET)
    assert not valid and reason == "signature mismatch"


def test_stale_timestamp_rejected():
    old = str(int(time.time()) - 3600)
    sig = compute_signature(SECRET, old, BODY)
    valid, reason = verify_webhook_signature(BODY, old, sig, SECRET)
    assert not valid and "old" in reason


def test_any_of_several_signatures_matches():
    """Hunar sends a comma-separated list when the org has multiple keys."""
    ts = _ts()
    header = f"someothersignature,{compute_signature(SECRET, ts, BODY)}"
    assert verify_webhook_signature(BODY, ts, header, SECRET)[0]


def test_missing_headers_rejected():
    assert not verify_webhook_signature(BODY, None, None, SECRET)[0]


async def test_requests_go_to_the_external_v1_prefix(monkeypatch):
    """Regression: the external API lives under /external/v1.

    Calling the bare paths returns an HTML 404 from the gateway, which looks
    like an outage rather than a wrong URL -- worth pinning down.
    """
    import httpx

    seen: dict[str, str] = {}

    async def fake_request(self, method, url, **kwargs):
        seen["url"] = str(url)
        return httpx.Response(200, json={"id": "agent-1"}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    client = HunarClient(api_key="k", base_url="https://api.voice.hunar.ai")
    await client.create_agent({"name": "x"})
    assert seen["url"] == "https://api.voice.hunar.ai/external/v1/agents/"


def test_result_schema_maps_question_types():
    schema = build_result_schema(
        [
            {"key": "years_exp", "question": "How many years?", "type": "number"},
            {"key": "can_relocate", "question": "Can you relocate?", "type": "boolean"},
            {
                "key": "notice",
                "question": "Notice period?",
                "type": "choice",
                "options": ["immediate", "30 days"],
            },
            {"key": "why", "question": "Why this role?", "type": "text"},
        ]
    )
    props = schema["properties"]
    assert schema["type"] == "object"
    assert props["can_relocate"]["type"] == "boolean"
    assert props["why"]["type"] == "string"

    # A number question accepts text too, so "4 to 5 years" is recorded rather
    # than dropped for failing to be a number.
    assert props["years_exp"]["type"] == ["number", "string"]

    # A choice question steers toward its options without an enum that would
    # discard an in-between answer like "30 to 45 days".
    assert "enum" not in props["notice"]
    assert props["notice"]["type"] == "string"
    assert "immediate, 30 days" in props["notice"]["description"]
    # Every schema also carries the dashboard's two standard fields.
    assert props["interested"]["type"] == "boolean"
    assert props["summary"]["type"] == "string"


def test_job_questions_win_over_extra_fields():
    schema = build_result_schema(
        [{"key": "summary", "question": "Summarise your background", "type": "text"}]
    )
    assert "background" in schema["properties"]["summary"]["description"]


def test_agent_payload_includes_questions_and_schema():
    from app.services.screening import build_agent_payload

    job = Job(
        title="Backend Engineer",
        description="Python and Postgres.",
        location="Bengaluru",
        questions=[{"key": "years_exp", "question": "How many years of Python?", "type": "number"}],
    )
    payload = build_agent_payload(job)
    assert "Backend Engineer" in payload["name"]
    assert "How many years of Python?" in payload["agent_prompt"]
    assert "Bengaluru" in payload["agent_prompt"]
    assert payload["result_schema"]["properties"]["years_exp"]["type"] == ["number", "string"]


class FakeSession:
    """Just enough session for the agent helpers: they only ever `scalar` the
    binding lookup and `commit`."""

    def __init__(self, agent_id: str | None):
        self._agent_id = agent_id
        self.added: list = []

    async def scalar(self, _stmt):
        return self._agent_id

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass


async def test_agent_update_carries_persona_name(monkeypatch):
    """Regression: Hunar 422s an update that sends `voice_persona` or
    `language` without `persona_name`, so the existing one must be carried
    over. Getting this wrong silently stops question edits from ever reaching
    the agent."""
    from app.integrations.hunar import HunarClient
    from app.services.screening import sync_agent

    sent: dict = {}

    async def fake_get(self, agent_id):
        return {"id": agent_id, "persona_name": "Shreya", "voice_persona": "NEHA"}

    async def fake_update(self, agent_id, payload):
        sent.update(payload)
        return {"id": agent_id}

    monkeypatch.setattr(HunarClient, "get_agent", fake_get)
    monkeypatch.setattr(HunarClient, "update_agent", fake_update)

    job = Job(id="job-1", title="Backend Engineer", questions=[])
    await sync_agent(FakeSession("agent-1"), job)

    assert sent["persona_name"] == "Shreya"
    assert sent["voice_persona"] == "NEHA"


async def test_agent_update_drops_voice_when_no_persona_to_preserve(monkeypatch):
    from app.integrations.hunar import HunarClient
    from app.services.screening import sync_agent

    sent: dict = {}

    async def fake_get(self, agent_id):
        return {"id": agent_id}

    async def fake_update(self, agent_id, payload):
        sent.update(payload)
        return {"id": agent_id}

    monkeypatch.setattr(HunarClient, "get_agent", fake_get)
    monkeypatch.setattr(HunarClient, "update_agent", fake_update)

    await sync_agent(FakeSession("agent-1"), Job(id="job-2", title="QA", questions=[]))

    assert "voice_persona" not in sent and "language" not in sent
    assert sent["result_schema"]["properties"]["interested"]["type"] == "boolean"


def test_allowlist_when_configured_blocks_other_numbers(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "allowed_test_numbers", "+919999999999")
    assert_number_allowed("+919999999999")  # allowed
    with pytest.raises(CallNotAllowed):
        assert_number_allowed("+919111111111")


def test_empty_allowlist_allows_any_candidate(monkeypatch):
    """The restriction is opt-in: unset means real candidates can be called."""
    from app.config import settings

    monkeypatch.setattr(settings, "allowed_test_numbers", "")
    assert_number_allowed("+919111111111")


def test_a_candidate_without_a_number_cannot_be_called(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "allowed_test_numbers", "")
    for missing in ("", "   "):
        with pytest.raises(CallNotAllowed):
            assert_number_allowed(missing)


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("9876543210", "+919876543210"),  # bare national number
        ("098765 43210", "+919876543210"),  # trunk prefix and spacing
        ("+91 98765-43210", "+919876543210"),  # already international
        ("919876543210", "+919876543210"),  # country code, no plus
        ("0091 9876543210", "+919876543210"),  # international access code
        ("+1 415 555 2671", "+14155552671"),  # a non-default country
    ],
)
def test_typed_numbers_normalize_to_e164(typed, expected):
    assert normalize_phone(typed, default_country_code="+91") == expected


@pytest.mark.parametrize("bad", ["", "   ", "abc", "12", "+" + "9" * 20])
def test_unusable_numbers_are_rejected(bad):
    with pytest.raises(InvalidPhoneNumber):
        normalize_phone(bad, default_country_code="+91")
