"""GrowthClaw configuration — loads settings from workspace .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


def _find_env_file() -> str:
    """Find .env file: ~/.growthclaw/.env first, then cwd/.env."""
    home_env = Path.home() / ".growthclaw" / ".env"
    if home_env.exists():
        return str(home_env)
    return ".env"


class Settings(BaseSettings):
    """All GrowthClaw settings, loaded from workspace .env file."""

    # Database URLs
    customer_database_url: str = Field(alias="CUSTOMER_DATABASE_URL")
    growthclaw_database_url: str = Field(alias="GROWTHCLAW_DATABASE_URL")

    # LLM providers (at least one required)
    nvidia_api_key: str | None = Field(default=None, alias="NVIDIA_API_KEY")
    nvidia_nim_url: str | None = Field(default=None, alias="NVIDIA_NIM_URL")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # Twilio SMS
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str | None = Field(default=None, alias="TWILIO_FROM_NUMBER")

    # Email provider ("resend" or "sendgrid")
    email_provider: str = Field(default="resend", alias="GROWTHCLAW_EMAIL_PROVIDER")
    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")
    sendgrid_api_key: str | None = Field(default=None, alias="SENDGRID_API_KEY")
    from_email: str | None = Field(default=None, alias="GROWTHCLAW_FROM_EMAIL")
    from_name: str | None = Field(default=None, alias="GROWTHCLAW_FROM_NAME")

    # Business context (optional, helps LLM)
    business_name: str = Field(default="", alias="GROWTHCLAW_BUSINESS_NAME")
    business_description: str = Field(default="", alias="GROWTHCLAW_BUSINESS_DESCRIPTION")
    cta_url: str = Field(default="https://app.example.com", alias="GROWTHCLAW_CTA_URL")

    # Trigger settings
    max_fires_per_trigger: int = Field(default=3, alias="GROWTHCLAW_MAX_FIRES_PER_TRIGGER")
    cooldown_hours: int = Field(default=24, alias="GROWTHCLAW_COOLDOWN_HOURS")
    quiet_hours_start: int = Field(default=21, alias="GROWTHCLAW_QUIET_HOURS_START")
    quiet_hours_end: int = Field(default=8, alias="GROWTHCLAW_QUIET_HOURS_END")

    # Global frequency caps (cross-trigger)
    max_sms_per_day: int = Field(default=2, alias="GROWTHCLAW_MAX_SMS_PER_DAY")
    max_sms_per_week: int = Field(default=5, alias="GROWTHCLAW_MAX_SMS_PER_WEEK")
    max_email_per_day: int = Field(default=2, alias="GROWTHCLAW_MAX_EMAIL_PER_DAY")
    max_email_per_week: int = Field(default=7, alias="GROWTHCLAW_MAX_EMAIL_PER_WEEK")

    # Memory system
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    memory_db_path: str = Field(default="data/memory", alias="GROWTHCLAW_MEMORY_PATH")

    # System settings
    dry_run: bool = Field(default=True, alias="GROWTHCLAW_DRY_RUN")
    sample_rows: int = Field(default=500, alias="GROWTHCLAW_SAMPLE_ROWS")

    model_config = {
        "env_file": _find_env_file(),
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def validate_llm_keys(self) -> Settings:
        if not self.nvidia_api_key and not self.anthropic_api_key:
            raise ValueError("At least one LLM API key is required (NVIDIA_API_KEY or ANTHROPIC_API_KEY)")
        return self

    @property
    def llm_provider(self) -> str:
        """Return which LLM provider to use."""
        return "nvidia" if self.nvidia_api_key else "anthropic"


def get_settings() -> Settings:
    """Create and return settings instance."""
    return Settings()  # type: ignore[call-arg]
