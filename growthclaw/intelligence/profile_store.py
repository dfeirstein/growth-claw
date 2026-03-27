"""Profile store — caches customer profiles in growthclaw.profiles."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import asyncpg

from growthclaw.models.profile import CustomerProfile, IntelligenceBrief

logger = logging.getLogger("growthclaw.intelligence.profile_store")

# Default TTL for cached profiles
DEFAULT_TTL_HOURS = 24


async def save(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    user_id: str,
    raw_data: dict,
    analysis: IntelligenceBrief,
) -> None:
    """Cache a customer profile, upserting by user_id."""
    await conn.execute(
        """
        INSERT INTO growthclaw.profiles (user_id, raw_data, analysis, computed_at)
        VALUES ($1, $2::jsonb, $3::jsonb, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            raw_data = EXCLUDED.raw_data,
            analysis = EXCLUDED.analysis,
            computed_at = NOW()
        """,
        user_id,
        json.dumps(raw_data, default=str),
        json.dumps(analysis.model_dump(mode="json")),
    )
    logger.info("Cached profile for user %s", user_id)


async def load(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    user_id: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> CustomerProfile | None:
    """Load a cached profile if it exists and is within TTL."""
    row = await conn.fetchrow(
        "SELECT * FROM growthclaw.profiles WHERE user_id = $1",
        user_id,
    )
    if not row:
        return None

    # Check TTL
    computed_at = row["computed_at"]
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - computed_at > timedelta(hours=ttl_hours):
        logger.info("Profile for user %s is stale (computed %s)", user_id, computed_at)
        return None

    import json as _json

    raw = row["raw_data"]
    raw_data = _json.loads(raw) if isinstance(raw, str) else raw
    analysis_val = row["analysis"]
    analysis_data = _json.loads(analysis_val) if isinstance(analysis_val, str) else analysis_val

    return CustomerProfile(
        user_id=row["user_id"],
        raw_data=raw_data,
        analysis=IntelligenceBrief.model_validate(analysis_data),
        computed_at=computed_at,
    )
