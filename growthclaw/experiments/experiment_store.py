"""Experiment store — persists experiments and results to growthclaw.experiments."""

from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg

from growthclaw.models.experiment import Experiment, ExperimentResult

logger = logging.getLogger("growthclaw.experiments.store")


async def save(conn: asyncpg.Connection, experiment: Experiment) -> UUID:  # type: ignore[type-arg]
    """Save an experiment and initialize result rows for each arm."""
    arms_json = json.dumps([a.model_dump(mode="json") for a in experiment.arms])

    await conn.execute(
        """
        INSERT INTO growthclaw.experiments (id, name, trigger_id, variable, arms, metric, status)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
        ON CONFLICT (id) DO UPDATE SET
            arms = EXCLUDED.arms, status = EXCLUDED.status
        """,
        experiment.id,
        experiment.name,
        experiment.trigger_id,
        experiment.variable,
        arms_json,
        experiment.metric,
        experiment.status,
    )

    # Initialize result rows for each arm
    for arm in experiment.arms:
        await conn.execute(
            """
            INSERT INTO growthclaw.experiment_results (experiment_id, arm_name)
            VALUES ($1, $2)
            ON CONFLICT (experiment_id, arm_name) DO NOTHING
            """,
            experiment.id,
            arm.name,
        )

    logger.info("Saved experiment '%s' with %d arms", experiment.name, len(experiment.arms))
    return experiment.id


async def record_send(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    experiment_id: UUID,
    arm_name: str,
) -> None:
    """Record that a message was sent for an experiment arm."""
    await conn.execute(
        """
        UPDATE growthclaw.experiment_results
        SET total_sent = total_sent + 1, last_updated = NOW()
        WHERE experiment_id = $1 AND arm_name = $2
        """,
        experiment_id,
        arm_name,
    )


async def get_results(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    experiment_id: UUID,
) -> list[ExperimentResult]:
    """Get results for all arms of an experiment."""
    rows = await conn.fetch(
        "SELECT * FROM growthclaw.experiment_results WHERE experiment_id = $1 ORDER BY arm_name",
        experiment_id,
    )
    return [
        ExperimentResult(
            arm_name=row["arm_name"],
            total_sent=row["total_sent"],
            total_converted=row["total_converted"],
            conversion_rate=row["conversion_rate"] or 0.0,
            last_updated=row["last_updated"],
        )
        for row in rows
    ]


async def get_all_active(conn: asyncpg.Connection) -> list[Experiment]:  # type: ignore[type-arg]
    """Get all active experiments."""
    rows = await conn.fetch("SELECT * FROM growthclaw.experiments WHERE status = 'active' ORDER BY created_at")
    return [
        Experiment(
            id=row["id"],
            name=row["name"],
            trigger_id=row["trigger_id"],
            variable=row["variable"],
            arms=row["arms"],
            metric=row["metric"],
            status=row["status"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
