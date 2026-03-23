"""Email provider factory — swap between Resend and SendGrid via config."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from growthclaw.config import Settings
    from growthclaw.outreach.email_providers.base import EmailProvider


def create_email_provider(settings: Settings) -> EmailProvider:
    """Create the configured email provider."""
    provider = settings.email_provider

    if provider == "sendgrid":
        from growthclaw.outreach.email_providers.sendgrid_provider import SendGridProvider

        if not settings.sendgrid_api_key:
            raise ValueError("SENDGRID_API_KEY is required when email_provider='sendgrid'")
        return SendGridProvider(
            api_key=settings.sendgrid_api_key,
            from_email=settings.from_email or "",
            from_name=settings.from_name or settings.business_name,
        )
    else:
        from growthclaw.outreach.email_providers.resend_provider import ResendProvider

        if not settings.resend_api_key:
            raise ValueError("RESEND_API_KEY is required when email_provider='resend'")
        return ResendProvider(
            api_key=settings.resend_api_key,
            from_email=settings.from_email or "",
            from_name=settings.from_name or settings.business_name,
        )
