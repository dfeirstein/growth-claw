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
        """Send an email. Returns provider message ID on success, None on dry run.

        Automatically appends an unsubscribe link to every email (CAN-SPAM compliance).
        """
        # Inject unsubscribe link (safety net — even if LLM forgot to include it)
        html_body = _inject_unsubscribe(html_body, to_email)

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


UNSUBSCRIBE_HTML = (
    '<p style="font-size:11px;color:#999;margin-top:20px;">'
    "If you no longer wish to receive these emails, "
    '<a href="{url}" style="color:#999;">unsubscribe here</a>.</p>'
)


def _inject_unsubscribe(html_body: str, to_email: str) -> str:
    """Append unsubscribe link to email HTML if not already present."""
    if "unsubscribe" in html_body.lower():
        return html_body  # LLM already included it

    # Generate a simple unsubscribe URL (webhook handler processes it)
    import urllib.parse

    unsubscribe_url = f"/unsubscribe?email={urllib.parse.quote(to_email)}"
    footer = UNSUBSCRIBE_HTML.format(url=unsubscribe_url)

    # Insert before closing </body> or append at end
    if "</body>" in html_body.lower():
        return html_body.replace("</body>", f"{footer}</body>")
    return html_body + footer
