"""Email provider protocol — defines the interface all providers must implement."""

from __future__ import annotations

from typing import Protocol


class EmailProvider(Protocol):
    """Protocol for email delivery providers (Resend, SendGrid, etc.)."""

    async def send(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text: str | None = None,
    ) -> str:
        """Send an email. Returns the provider's message ID."""
        ...
