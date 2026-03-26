"""Webhook handler — receives email provider events (bounces, complaints, unsubscribes)."""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

logger = logging.getLogger("growthclaw.outreach.webhook_handler")


async def handle_resend_webhook(event: dict[str, Any], conn: asyncpg.Connection) -> None:  # type: ignore[type-arg]
    """Process a Resend webhook event and update suppressions.

    Event types:
    - email.bounced → suppress (reason='bounce')
    - email.complained → suppress (reason='complaint')
    - email.unsubscribed → suppress (reason='unsubscribe')
    """
    event_type = event.get("type", "")
    data = event.get("data", {})
    to_email = ""

    # Extract recipient email from event data
    if isinstance(data.get("to"), list) and data["to"]:
        to_email = data["to"][0]
    elif isinstance(data.get("to"), str):
        to_email = data["to"]
    elif data.get("email"):
        to_email = data["email"]

    if not to_email:
        logger.warning("Webhook event missing recipient email: %s", event_type)
        return

    reason_map = {
        "email.bounced": "bounce",
        "email.complained": "complaint",
        "email.unsubscribed": "unsubscribe",
    }

    reason = reason_map.get(event_type)
    if not reason:
        logger.debug("Ignoring webhook event type: %s", event_type)
        return

    # Find user_id by email (query customer table concepts would be needed)
    # For now, use the email as the user_id for suppression
    await _insert_suppression(conn, user_id=to_email, channel="email", reason=reason)
    logger.info("Suppression recorded: email=%s reason=%s", to_email, reason)


async def handle_unsubscribe_request(email: str, conn: asyncpg.Connection) -> None:  # type: ignore[type-arg]
    """Handle a direct unsubscribe request (from unsubscribe link in email)."""
    await _insert_suppression(conn, user_id=email, channel="email", reason="unsubscribe")
    logger.info("Unsubscribe recorded: email=%s", email)


async def _insert_suppression(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    user_id: str,
    channel: str,
    reason: str,
) -> None:
    """Insert a suppression record (idempotent)."""
    await conn.execute(
        """
        INSERT INTO growthclaw.suppressions (user_id, channel, reason)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, channel) DO UPDATE SET reason = $3, created_at = NOW()
        """,
        user_id,
        channel,
        reason,
    )
