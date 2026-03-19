"""GrowthClaw configuration — loads and validates all environment variables."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All GrowthClaw settings, loaded from environment variables and .env file."""

    # Database URLs
    customer_database_url: str = Field(alias="CUSTOMER_DATABASE_URL")
    growthclaw_database_url: str = Field(alias="GROWTHCLAW_DATABASE_URL")

    # LLM providers (at least one required)
    nvidia_api_key: str | None = Field(default=None, alias="NVIDIA_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # Twilio SMS
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str | None = Field(default=None, alias="TWILIO_FROM_NUMBER")

    # Business context (optional, helps LLM)
    business_name: str = Field(default="", alias="GROWTHCLAW_BUSINESS_NAME")
    business_description: str = Field(default="", alias="GROWTHCLAW_BUSINESS_DESCRIPTION")
    card_link_url: str = Field(default="https://app.example.com", alias="GROWTHCLAW_CARD_LINK_URL")

    # Trigger settings
    max_fires_per_trigger: int = Field(default=3, alias="GROWTHCLAW_MAX_FIRES_PER_TRIGGER")
    cooldown_hours: int = Field(default=24, alias="GROWTHCLAW_COOLDOWN_HOURS")
    quiet_hours_start: int = Field(default=21, alias="GROWTHCLAW_QUIET_HOURS_START")
    quiet_hours_end: int = Field(default=8, alias="GROWTHCLAW_QUIET_HOURS_END")

    # System settings
    dry_run: bool = Field(default=True, alias="GROWTHCLAW_DRY_RUN")
    sample_rows: int = Field(default=500, alias="GROWTHCLAW_SAMPLE_ROWS")

    model_config = {
        "env_file": ".env",
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
