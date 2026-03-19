"""SMS sender — delivers messages via Twilio REST API."""

from __future__ import annotations

import logging

from twilio.rest import Client as TwilioClient

from growthclaw.config import Settings

logger = logging.getLogger("growthclaw.outreach.sms_sender")


class SMSSender:
    """Sends SMS messages via Twilio. Respects DRY_RUN mode."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: TwilioClient | None = None

    @property
    def client(self) -> TwilioClient:
        if self._client is None:
            if not self.settings.twilio_account_sid or not self.settings.twilio_auth_token:
                raise ValueError("Twilio credentials not configured")
            self._client = TwilioClient(self.settings.twilio_account_sid, self.settings.twilio_auth_token)
        return self._client

    async def send(self, to: str, body: str) -> str | None:
        """Send an SMS message. Returns Twilio SID on success, None on dry run.

        In DRY_RUN mode, logs the message but does not send.
        """
        from_number = self.settings.twilio_from_number
        if not from_number:
            raise ValueError("TWILIO_FROM_NUMBER not configured")

        if self.settings.dry_run:
            logger.info("[DRY RUN] SMS to %s from %s: %s", to, from_number, body)
            return None

        try:
            message = self.client.messages.create(
                body=body,
                from_=from_number,
                to=to,
            )
            logger.info("SMS sent to %s (SID: %s)", to, message.sid)
            return message.sid
        except Exception as e:
            logger.error("Failed to send SMS to %s: %s", to, e)
            raise
