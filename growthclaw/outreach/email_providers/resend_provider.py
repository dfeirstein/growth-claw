"""Resend email provider — default provider for GrowthClaw."""

from __future__ import annotations

import asyncio
import logging

import resend

logger = logging.getLogger("growthclaw.outreach.email.resend")


class ResendProvider:
    """Sends emails via Resend API."""

    def __init__(self, api_key: str, from_email: str, from_name: str = "") -> None:
        self.from_email = from_email
        self.from_name = from_name
        resend.api_key = api_key

    async def send(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text: str | None = None,
    ) -> str:
        """Send an email via Resend. Returns the Resend email ID."""
        from_str = f"{self.from_name} <{self.from_email}>" if self.from_name else self.from_email

        params: dict = {
            "from": from_str,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
        if plain_text:
            params["text"] = plain_text

        # resend.Emails.send() is synchronous — wrap for async compatibility
        result = await asyncio.to_thread(resend.Emails.send, params)
        email_id = result.get("id", "unknown") if isinstance(result, dict) else str(result)
        logger.info("Email sent via Resend to %s (id=%s)", to_email, email_id)
        return email_id
