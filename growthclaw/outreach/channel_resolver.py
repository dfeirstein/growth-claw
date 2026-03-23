"""Channel resolver — determines the best contact channel and info from discovered schema."""

from __future__ import annotations

import logging

import asyncpg

from growthclaw.models.schema_map import BusinessConcepts

logger = logging.getLogger("growthclaw.outreach.channel_resolver")


class ContactInfo:
    """Resolved contact information for a customer."""

    def __init__(self, channel: str, value: str | None, has_consent: bool = False) -> None:
        self.channel = channel
        self.value = value
        self.has_consent = has_consent

    @property
    def is_reachable(self) -> bool:
        return self.value is not None and self.has_consent


async def resolve(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    user_id: str,
    concepts: BusinessConcepts,
    preferred_channel: str = "sms",
) -> ContactInfo:
    """Resolve contact info for a customer based on discovered schema."""
    table = concepts.customer_table
    id_col = concepts.customer_id_column
    param = int(user_id) if user_id.isdigit() else user_id

    if preferred_channel == "sms" and concepts.customer_phone_column:
        # Build SELECT with phone and optional consent check
        columns = [f'"{concepts.customer_phone_column}"']
        if concepts.sms_consent_column:
            columns.append(f'"{concepts.sms_consent_column}"')

        query = f'SELECT {", ".join(columns)} FROM "{table}" WHERE "{id_col}" = $1'  # noqa: S608
        row = await conn.fetchrow(query, param)

        if row:
            phone = row[concepts.customer_phone_column]
            has_consent = True
            if concepts.sms_consent_column:
                consent_val = row[concepts.sms_consent_column]
                has_consent = consent_val is not None and consent_val is not False
            return ContactInfo(channel="sms", value=phone, has_consent=has_consent)

    elif preferred_channel == "email" and concepts.customer_email_column:
        query = f'SELECT "{concepts.customer_email_column}" FROM "{table}" WHERE "{id_col}" = $1'  # noqa: S608
        row = await conn.fetchrow(query, param)
        if row:
            email = row[concepts.customer_email_column]
            return ContactInfo(channel="email", value=email, has_consent=True)

    # Fallback: try alternate channel
    if preferred_channel == "sms" and concepts.customer_email_column:
        return await resolve(conn, user_id, concepts, preferred_channel="email")

    return ContactInfo(channel=preferred_channel, value=None, has_consent=False)


async def is_suppressed(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    user_id: str,
    channel: str,
) -> bool:
    """Check if user has opted out of this channel (unsubscribed, bounced, complained)."""
    row = await conn.fetchrow(
        "SELECT 1 FROM growthclaw.suppressions WHERE user_id = $1 AND channel = $2",
        user_id,
        channel,
    )
    return row is not None
