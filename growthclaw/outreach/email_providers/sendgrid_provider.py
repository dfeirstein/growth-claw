"""SendGrid email provider — optional alternative for enterprise customers."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("growthclaw.outreach.email.sendgrid")


class SendGridProvider:
    """Sends emails via SendGrid API."""

    def __init__(self, api_key: str, from_email: str, from_name: str = "") -> None:
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self._client = None

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            from sendgrid import SendGridAPIClient

            self._client = SendGridAPIClient(api_key=self.api_key)
        return self._client

    async def send(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text: str | None = None,
    ) -> str:
        """Send an email via SendGrid. Returns the SendGrid message ID."""
        from sendgrid.helpers.mail import Content, Email, Mail, To

        message = Mail(
            from_email=Email(self.from_email, self.from_name),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_body),
        )
        if plain_text:
            message.add_content(Content("text/plain", plain_text))

        def _send():  # type: ignore[no-untyped-def]
            response = self._get_client().send(message)
            return response.headers.get("X-Message-Id", "unknown")

        message_id = await asyncio.to_thread(_send)
        logger.info("Email sent via SendGrid to %s (id=%s)", to_email, message_id)
        return message_id
