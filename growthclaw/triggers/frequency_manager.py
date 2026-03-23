"""Cross-trigger frequency capping — prevents over-messaging customers."""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger("growthclaw.triggers.frequency_manager")


async def check_global_frequency(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    user_id: str,
    channel: str,
    max_per_day: int = 2,
    max_per_week: int = 5,
) -> bool:
    """Return True if user is WITHIN frequency limits (OK to send)."""
    day_count = await conn.fetchval(
        "SELECT COUNT(*) FROM growthclaw.global_frequency "
        "WHERE user_id = $1 AND channel = $2 AND sent_at > NOW() - INTERVAL '24 hours'",
        user_id,
        channel,
    )
    if day_count >= max_per_day:
        logger.info("Frequency: daily cap hit (%d/%d, user=%s, channel=%s)", day_count, max_per_day, user_id, channel)
        return False

    week_count = await conn.fetchval(
        "SELECT COUNT(*) FROM growthclaw.global_frequency "
        "WHERE user_id = $1 AND channel = $2 AND sent_at > NOW() - INTERVAL '7 days'",
        user_id,
        channel,
    )
    if week_count >= max_per_week:
        logger.info(
            "Frequency: weekly cap hit (%d/%d, user=%s, channel=%s)", week_count, max_per_week, user_id, channel
        )
        return False

    return True


async def record_send(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    user_id: str,
    channel: str,
) -> None:
    """Record a send for frequency tracking."""
    await conn.execute(
        "INSERT INTO growthclaw.global_frequency (user_id, channel, sent_at) VALUES ($1, $2, NOW())",
        user_id,
        channel,
    )
