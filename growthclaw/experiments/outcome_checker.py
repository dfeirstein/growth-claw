"""Outcome checker — polls for conversions and updates journey outcomes."""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from growthclaw.outreach import journey_store
from growthclaw.triggers import trigger_store

logger = logging.getLogger("growthclaw.experiments.outcome_checker")


async def check_outcomes(
    customer_conn: asyncpg.Connection,  # type: ignore[type-arg]
    internal_conn: asyncpg.Connection,  # type: ignore[type-arg]
    dag: object | None = None,
) -> int:
    """Check all pending journeys for conversion outcomes.

    Returns the number of outcomes resolved.
    """
    pending = await journey_store.get_pending_outcomes(internal_conn)
    if not pending:
        return 0

    resolved = 0
    for journey in pending:
        try:
            trigger = await trigger_store.get_by_id(internal_conn, journey.trigger_id)
            if not trigger:
                logger.warning("Trigger %s not found for journey %s", journey.trigger_id, journey.id)
                continue

            # Run the trigger's check_sql to see if the user has now activated
            if trigger.check_sql:
                param = int(journey.user_id) if journey.user_id.isdigit() else journey.user_id
                still_needs_action = await customer_conn.fetchval(trigger.check_sql, param)

                if not still_needs_action:
                    # User has converted!
                    await journey_store.update_outcome(internal_conn, journey.id, "converted")
                    logger.info("Conversion detected: user=%s, journey=%s", journey.user_id, journey.id)
                    resolved += 1

                    # Update DAG Layer 0 event outcome (match by user_id + trigger_id)
                    if dag and hasattr(dag, "update_event_outcome_by_user"):
                        try:
                            await dag.update_event_outcome_by_user(
                                journey.user_id, journey.trigger_id, "converted"
                            )
                        except Exception as dag_err:
                            logger.warning("DAG outcome update failed: %s", dag_err)

                    # Update experiment results if applicable
                    if journey.experiment_id and journey.experiment_arm:
                        await _update_experiment_result(
                            internal_conn, journey.experiment_id, journey.experiment_arm, converted=True
                        )
        except Exception as e:
            logger.warning("Failed to check outcome for journey %s: %s", journey.id, e)

    logger.info("Outcome check complete: %d/%d resolved", resolved, len(pending))
    return resolved


async def _update_experiment_result(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    experiment_id: UUID,
    arm_name: str,
    converted: bool,
) -> None:
    """Update experiment results with a new data point."""
    if converted:
        await conn.execute(
            """
            UPDATE growthclaw.experiment_results
            SET total_converted = total_converted + 1,
                conversion_rate = (total_converted + 1)::float / NULLIF(total_sent, 0),
                last_updated = NOW()
            WHERE experiment_id = $1 AND arm_name = $2
            """,
            experiment_id,
            arm_name,
        )
