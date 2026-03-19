"""Trigger store — persists trigger configurations to growthclaw.triggers."""

from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg

from growthclaw.models.trigger import ProfileQuery, TriggerRule

logger = logging.getLogger("growthclaw.triggers.store")


async def save_all(conn: asyncpg.Connection, triggers: list[TriggerRule]) -> None:  # type: ignore[type-arg]
    """Save all trigger rules, upserting by name for idempotency."""
    for trigger in triggers:
        await _upsert_trigger(conn, trigger)
    logger.info("Saved %d triggers", len(triggers))


async def _upsert_trigger(conn: asyncpg.Connection, trigger: TriggerRule) -> None:  # type: ignore[type-arg]
    """Upsert a single trigger rule by name."""
    profile_queries_json = json.dumps([pq.model_dump(mode="json") for pq in trigger.profile_queries])

    existing = await conn.fetchrow("SELECT id FROM growthclaw.triggers WHERE name = $1", trigger.name)

    if existing:
        await conn.execute(
            """
            UPDATE growthclaw.triggers
            SET description = $1, watch_table = $2, watch_event = $3,
                watch_condition = $4, delay_minutes = $5, check_sql = $6,
                profile_queries = $7::jsonb, message_context = $8,
                channel = $9, max_fires = $10, cooldown_hours = $11
            WHERE name = $12
            """,
            trigger.description,
            trigger.watch_table,
            trigger.watch_event,
            trigger.watch_condition,
            trigger.delay_minutes,
            trigger.check_sql,
            profile_queries_json,
            trigger.message_context,
            trigger.channel,
            trigger.max_fires,
            trigger.cooldown_hours,
            trigger.name,
        )
        logger.info("Updated trigger: %s", trigger.name)
    else:
        await conn.execute(
            """
            INSERT INTO growthclaw.triggers
                (id, name, description, watch_table, watch_event, watch_condition,
                 delay_minutes, check_sql, profile_queries, message_context,
                 channel, max_fires, cooldown_hours, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13, $14)
            """,
            trigger.id,
            trigger.name,
            trigger.description,
            trigger.watch_table,
            trigger.watch_event,
            trigger.watch_condition,
            trigger.delay_minutes,
            trigger.check_sql,
            profile_queries_json,
            trigger.message_context,
            trigger.channel,
            trigger.max_fires,
            trigger.cooldown_hours,
            trigger.status,
        )
        logger.info("Created trigger: %s", trigger.name)


async def get_all(conn: asyncpg.Connection) -> list[TriggerRule]:  # type: ignore[type-arg]
    """Get all triggers."""
    rows = await conn.fetch("SELECT * FROM growthclaw.triggers ORDER BY created_at")
    return [_row_to_trigger(row) for row in rows]


async def get_active(conn: asyncpg.Connection) -> list[TriggerRule]:  # type: ignore[type-arg]
    """Get all active (approved + active) triggers."""
    rows = await conn.fetch(
        "SELECT * FROM growthclaw.triggers WHERE status IN ('approved', 'active') ORDER BY created_at"
    )
    return [_row_to_trigger(row) for row in rows]


async def get_by_id(conn: asyncpg.Connection, trigger_id: UUID) -> TriggerRule | None:  # type: ignore[type-arg]
    """Get a trigger by ID."""
    row = await conn.fetchrow("SELECT * FROM growthclaw.triggers WHERE id = $1", trigger_id)
    return _row_to_trigger(row) if row else None


async def approve(conn: asyncpg.Connection, trigger_id: UUID) -> None:  # type: ignore[type-arg]
    """Approve a proposed trigger."""
    await conn.execute(
        "UPDATE growthclaw.triggers SET status = 'approved' WHERE id = $1 AND status = 'proposed'",
        trigger_id,
    )
    logger.info("Approved trigger: %s", trigger_id)


async def approve_all(conn: asyncpg.Connection) -> int:  # type: ignore[type-arg]
    """Approve all proposed triggers. Returns count of approved."""
    result = await conn.execute("UPDATE growthclaw.triggers SET status = 'approved' WHERE status = 'proposed'")
    count = int(result.split()[-1]) if result else 0
    logger.info("Approved %d triggers", count)
    return count


async def set_active(conn: asyncpg.Connection, trigger_id: UUID) -> None:  # type: ignore[type-arg]
    """Mark a trigger as active (CDC trigger installed)."""
    await conn.execute(
        "UPDATE growthclaw.triggers SET status = 'active' WHERE id = $1",
        trigger_id,
    )


async def pause(conn: asyncpg.Connection, trigger_id: UUID) -> None:  # type: ignore[type-arg]
    """Pause an active trigger."""
    await conn.execute(
        "UPDATE growthclaw.triggers SET status = 'paused' WHERE id = $1",
        trigger_id,
    )


def _row_to_trigger(row: asyncpg.Record) -> TriggerRule:  # type: ignore[type-arg]
    """Convert a database row to a TriggerRule model."""
    profile_queries = [ProfileQuery.model_validate(pq) for pq in (row["profile_queries"] or [])]
    return TriggerRule(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        watch_table=row["watch_table"],
        watch_event=row["watch_event"],
        watch_condition=row["watch_condition"],
        delay_minutes=row["delay_minutes"],
        check_sql=row["check_sql"],
        profile_queries=profile_queries,
        message_context=row["message_context"],
        channel=row["channel"],
        max_fires=row["max_fires"],
        cooldown_hours=row["cooldown_hours"],
        status=row["status"],
        created_at=row["created_at"],
    )
