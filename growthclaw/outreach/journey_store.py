"""Journey store — logs all outreach events to growthclaw.journeys."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import asyncpg

from growthclaw.models.journey import Journey

logger = logging.getLogger("growthclaw.outreach.journey_store")


async def create(conn: asyncpg.Connection, journey: Journey) -> UUID:  # type: ignore[type-arg]
    """Create a new journey record."""
    await conn.execute(
        """
        INSERT INTO growthclaw.journeys
            (id, user_id, trigger_id, event_id, channel, contact_info, message_body,
             status, experiment_id, experiment_arm, llm_reasoning, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """,
        journey.id,
        journey.user_id,
        journey.trigger_id,
        journey.event_id,
        journey.channel,
        journey.contact_info,
        journey.message_body,
        journey.status,
        journey.experiment_id,
        journey.experiment_arm,
        journey.llm_reasoning,
        journey.created_at,
    )
    logger.info("Journey created: %s (user=%s, trigger=%s)", journey.id, journey.user_id, journey.trigger_id)
    return journey.id


async def update_sent(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    journey_id: UUID,
    provider_id: str | None,
    status: Literal["sent", "failed"] = "sent",
) -> None:
    """Update a journey after attempting to send."""
    await conn.execute(
        """
        UPDATE growthclaw.journeys
        SET provider_id = $1, status = $2, sent_at = $3
        WHERE id = $4
        """,
        provider_id,
        status,
        datetime.now(UTC) if status == "sent" else None,
        journey_id,
    )


async def update_outcome(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    journey_id: UUID,
    outcome: Literal["converted", "ignored", "unsubscribed"],
) -> None:
    """Record the outcome of a journey."""
    await conn.execute(
        """
        UPDATE growthclaw.journeys
        SET outcome = $1, outcome_at = $2
        WHERE id = $3
        """,
        outcome,
        datetime.now(UTC),
        journey_id,
    )


async def get_pending_outcomes(conn: asyncpg.Connection) -> list[Journey]:  # type: ignore[type-arg]
    """Get all journeys that were sent but don't have an outcome yet."""
    rows = await conn.fetch(
        """
        SELECT * FROM growthclaw.journeys
        WHERE outcome IS NULL AND sent_at IS NOT NULL AND status = 'sent'
        ORDER BY sent_at
        """
    )
    return [_row_to_journey(row) for row in rows]


async def get_recent(conn: asyncpg.Connection, limit: int = 50) -> list[Journey]:  # type: ignore[type-arg]
    """Get recent journeys."""
    rows = await conn.fetch(
        "SELECT * FROM growthclaw.journeys ORDER BY created_at DESC LIMIT $1",
        limit,
    )
    return [_row_to_journey(row) for row in rows]


def _row_to_journey(row: asyncpg.Record) -> Journey:  # type: ignore[type-arg]
    """Convert a database row to a Journey model."""
    return Journey(
        id=row["id"],
        user_id=row["user_id"],
        trigger_id=row["trigger_id"],
        event_id=row["event_id"],
        channel=row["channel"],
        contact_info=row["contact_info"],
        message_body=row["message_body"],
        provider_id=row["provider_id"],
        status=row["status"],
        experiment_id=row["experiment_id"],
        experiment_arm=row["experiment_arm"],
        llm_reasoning=row["llm_reasoning"],
        created_at=row["created_at"],
        sent_at=row["sent_at"],
        outcome=row["outcome"],
        outcome_at=row["outcome_at"],
    )
