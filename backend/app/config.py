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

    # ---- Webhooks ----
    # Reject inbound webhooks whose HMAC signature does not verify. Only turn
    # this off to debug delivery locally -- never in a deployed environment.
    webhook_signature_required: bool = True

    # ---- Task 2 ----
    pdl_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_test_number_list(self) -> list[str]:
        return [n.strip() for n in self.allowed_test_numbers.split(",") if n.strip()]

    @property
    def hunar_configured(self) -> bool:
        return bool(self.hunar_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
