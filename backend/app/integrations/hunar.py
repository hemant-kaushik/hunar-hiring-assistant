"""Hunar Voice AI client and webhook signature verification.

Everything that knows about Hunar's HTTP surface lives here. Services above
this layer deal in plain dicts, so a second voice vendor could be added by
writing a sibling module with the same three verbs (create agent, place call,
read call).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Every external endpoint lives under this prefix; the OpenAPI spec at
# https://api.voice.hunar.ai/docs/external/openapi.json declares no `servers`
# entry, so it has to be applied by the client. Keeping it here rather than in
# HUNAR_API_BASE_URL means the env var stays a plain host and cannot be set to
# something that silently 404s.
API_PREFIX = "/external/v1"

# Reject webhooks whose timestamp is older than this. Bounds the window in
# which a captured request could be replayed.
WEBHOOK_MAX_AGE_SECONDS = 300

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class HunarError(RuntimeError):
    """A call to the Hunar API failed."""

    def __init__(self, message: str, status_code: int | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details

    @property
    def is_auth_error(self) -> bool:
        return self.status_code in (401, 403)

    @property
    def is_quota_error(self) -> bool:
        # 402: the org's voice minutes are exhausted.
        return self.status_code == 402


class HunarClient:
    """Thin async wrapper over the Hunar REST API.

    Auth is `X-API-Key`. Trailing slashes matter to the upstream router, so
    every path here keeps one.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key if api_key is not None else settings.hunar_api_key
        self.base_url = (base_url or settings.hunar_api_base_url).rstrip("/")

    # ---- plumbing -------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        if not self.api_key:
            raise HunarError(
                "The calling service is not configured yet, so calls cannot be placed. "
                "Please contact your administrator.",
                status_code=401,
            )

        url = f"{self.base_url}{API_PREFIX}{path}"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            try:
                resp = await client.request(
                    method, url, json=json, params=params, headers=self._headers()
                )
            except httpx.HTTPError as exc:
                raise HunarError(f"Could not reach Hunar: {exc}") from exc

        if resp.status_code >= 400:
            message, details = _parse_error(resp)
            logger.warning("Hunar %s %s -> %s: %s", method, path, resp.status_code, message)
            raise HunarError(message, status_code=resp.status_code, details=details)

        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise HunarError("Hunar returned a non-JSON response") from exc

    # ---- agents ---------------------------------------------------------

    async def create_agent(self, payload: dict) -> dict:
        return await self._request("POST", "/agents/", json=payload)

    async def get_agent(self, agent_id: str) -> dict:
        return await self._request("GET", f"/agents/{agent_id}/")

    async def update_agent(self, agent_id: str, payload: dict) -> dict:
        return await self._request("PUT", f"/agents/{agent_id}/", json=payload)

    async def list_agents(self, page: int = 1, page_size: int = 20) -> Any:
        return await self._request(
            "GET", "/agents/", params={"page": page, "page_size": page_size}
        )

    # ---- calls ----------------------------------------------------------

    async def create_call(self, payload: dict) -> dict:
        return await self._request("POST", "/calls/", json=payload)

    async def get_call(self, call_id: str) -> dict:
        return await self._request("GET", f"/calls/{call_id}/")

    async def list_calls(self, page: int = 1, page_size: int = 10, **filters: Any) -> Any:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        params.update({k: v for k, v in filters.items() if v is not None})
        return await self._request("GET", "/calls/", params=params)

    # ---- phone numbers --------------------------------------------------

    async def list_numbers(self, page: int = 1, page_size: int = 10) -> Any:
        return await self._request(
            "GET", "/numbers/", params={"page": page, "page_size": page_size}
        )


def _parse_error(resp: httpx.Response) -> tuple[str, Any]:
    """Turn Hunar's error envelope into a message plus raw details."""
    try:
        body = resp.json()
    except ValueError:
        # Gateway-level failures come back as HTML error pages; dumping the
        # markup into the UI helps nobody.
        text = (resp.text or "").strip()
        if text.startswith("<"):
            return f"HTTP {resp.status_code} from {resp.request.url}", None
        return (text or f"HTTP {resp.status_code}")[:500], None

    if isinstance(body, dict):
        message = body.get("message") or body.get("detail") or f"HTTP {resp.status_code}"
        details = body.get("details")
        if isinstance(details, list) and details:
            fields = "; ".join(
                f"{d.get('field_name')}: {d.get('error_msg')}"
                for d in details
                if isinstance(d, dict)
            )
            if fields:
                message = f"{message} ({fields})"
        return str(message), details
    return str(body)[:500], None


# --------------------------------------------------------------------------
# Webhook signature verification
# --------------------------------------------------------------------------


def compute_signature(secret: str, timestamp: str, body: bytes) -> str:
    """base64(HMAC-SHA256(secret, "<timestamp>." + raw_body))."""
    message = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def verify_webhook_signature(
    body: bytes,
    timestamp: str | None,
    signature_header: str | None,
    secret: str | None = None,
    *,
    max_age_seconds: int = WEBHOOK_MAX_AGE_SECONDS,
) -> tuple[bool, str | None]:
    """Verify an inbound Hunar webhook.

    `body` must be the raw request bytes -- re-serializing the parsed JSON
    changes key order and whitespace and would break the HMAC.

    Hunar sends a comma-separated signature list when the org has several API
    keys active, so any one match is accepted.

    Returns (is_valid, reason_if_not).
    """
    secret = secret if secret is not None else settings.hunar_api_key
    if not secret:
        return False, "no API key configured to verify against"
    if not timestamp or not signature_header:
        return False, "missing X-Hunar-Timestamp or X-Hunar-Signature header"

    try:
        sent_at = int(float(timestamp))
    except (TypeError, ValueError):
        return False, "malformed timestamp header"

    age = abs(int(time.time()) - sent_at)
    if age > max_age_seconds:
        return False, f"timestamp is {age}s old (max {max_age_seconds}s)"

    expected = compute_signature(secret, timestamp, body)
    for candidate in signature_header.split(","):
        if hmac.compare_digest(expected, candidate.strip()):
            return True, None
    return False, "signature mismatch"
