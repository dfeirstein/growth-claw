"""Email sender — delegates to the configured email provider (Resend or SendGrid)."""

from __future__ import annotations

import logging

from growthclaw.config import Settings
from growthclaw.outreach.email_providers import create_email_provider
from growthclaw.outreach.email_providers.base import EmailProvider

logger = logging.getLogger("growthclaw.outreach.email_sender")


class EmailSender:
    """Sends emails via the configured provider. Respects DRY_RUN mode."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._provider: EmailProvider | None = None

    @property
    def provider(self) -> EmailProvider:
        if self._provider is None:
            self._provider = create_email_provider(self.settings)
        return self._provider

    async def send(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text: str | None = None,
    ) -> str | None:
        """Send an email. Returns provider message ID on success, None on dry run."""
        if self.settings.dry_run:
            logger.info("[DRY RUN] Email to %s | Subject: %s | Body: %d chars", to_email, subject, len(html_body))
            return None

        try:
            message_id = await self.provider.send(to_email, subject, html_body, plain_text)
            logger.info("Email sent to %s (id=%s, provider=%s)", to_email, message_id, self.settings.email_provider)
            return message_id
        except Exception:
            logger.exception("Failed to send email to %s", to_email)
            raise
