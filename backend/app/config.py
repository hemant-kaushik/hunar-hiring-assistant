"""Application settings, loaded from environment variables.

Secrets are never hard-coded. Locally they come from backend/.env (gitignored);
in production they come from the host's environment variable settings.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- Hunar Voice AI ----
    hunar_api_key: str = ""
    hunar_api_base_url: str = "https://api.voice.hunar.ai"

    # ---- Database ----
    database_url: str = "sqlite+aiosqlite:///./hiring_assistant.db"

    # ---- Networking ----
    # Public URL of this backend; Hunar posts webhooks to it.
    public_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173"

    # ---- Call safety ----
    dry_run_calls: bool = False
    # Opt-in restriction. Empty means any candidate's number can be called;
    # fill it in and only those numbers are reachable.
    allowed_test_numbers: str = ""

    # Assumed when someone types a number without a country code.
    default_country_code: str = "+91"

    # ---- Calling hours ----
    # Calls outside this window are queued by the provider for the next
    # permitted slot rather than dialled, which is why a late-evening call sits
    # at SCHEDULED. Sent explicitly so the behaviour is ours and predictable
    # instead of an invisible provider default. Widen to 00:00-23:59 only when
    # testing against your own phone.
    call_timezone: str = "Asia/Kolkata"
    earliest_call_time: str = "09:00"
    latest_call_time: str = "20:00"
    # Hunar requires all three guardrail fields together, so days are always
    # sent. All seven by default -- restricting to weekdays is a policy choice,
    # not something to impose silently.
    call_allowed_days: str = "MON,TUE,WED,THU,FRI,SAT,SUN"

    # ---- Webhooks ----
    # Reject inbound webhooks whose HMAC signature does not verify. Only turn
    # this off to debug delivery locally -- never in a deployed environment.
    webhook_signature_required: bool = True

    # ---- People search (Task 2) ----
    pdl_api_key: str = ""
    # "auto" uses People Data Labs when a key is set and falls back to the
    # bundled sample dataset otherwise. "pdl" or "sample" force one.
    people_search_provider: str = "auto"

    # The number the demo dataset's contactable profiles carry.
    #
    # Sample profiles deliberately ship with no phone number of their own:
    # inventing plausible ones would put real strangers behind a "Reach out"
    # button. Point this at a phone you control and those profiles become
    # callable for a demo. Left empty, they show as "number withheld", which is
    # also what a real provider returns on a free plan.
    sample_contact_phone: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_test_number_list(self) -> list[str]:
        return [n.strip() for n in self.allowed_test_numbers.split(",") if n.strip()]

    @property
    def call_allowed_day_list(self) -> list[str]:
        return [d.strip().upper() for d in self.call_allowed_days.split(",") if d.strip()]

    @property
    def hunar_configured(self) -> bool:
        return bool(self.hunar_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
