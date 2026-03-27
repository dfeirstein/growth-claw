"""Nightly sweep — strategic intelligence analysis of customer data."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import asyncpg

from growthclaw.llm.client import LLMClient, render_template
from growthclaw.memory.manager import MemoryManager
from growthclaw.models.schema_map import BusinessConcepts

logger = logging.getLogger("growthclaw.intelligence.nightly_sweep")


async def run_nightly_sweep(
    customer_conn: asyncpg.Connection,  # type: ignore[type-arg]
    internal_conn: asyncpg.Connection,  # type: ignore[type-arg]
    concepts: BusinessConcepts,
    llm_client: LLMClient,
    memory: MemoryManager,
    dag: object | None = None,
) -> dict[str, Any]:
    """Run the nightly strategic intelligence sweep.

    Analyzes cohort performance, timing patterns, dormancy, and whale
    behaviour. Compares against past memory insights. Returns proposals
    for new triggers and strategy adjustments.
    """
    # Gather intelligence from customer database
    cohort_data = await _analyze_cohorts(customer_conn, concepts)
    timing_data = await _analyze_timing_patterns(customer_conn, concepts)
    dormant_count = await _detect_dormancy(customer_conn, concepts)
    whale_patterns = await _identify_whale_patterns(customer_conn, concepts)

    # Recall past sweep insights from memory
    past_insights: list[str] = []
    try:
        memories = await memory.recall(
            query="nightly sweep findings and growth insights",
            category="insight",
            limit=10,
        )
        past_insights = [m.text for m in memories]
    except Exception as e:
        logger.warning("Memory recall failed during nightly sweep: %s", e)

    # Get existing active triggers
    existing_triggers = await _get_existing_triggers(internal_conn)

    # Render prompt and call LLM
    prompt = render_template(
        "nightly_sweep.j2",
        cohort_data=cohort_data,
        timing_data=timing_data,
        dormant_count=dormant_count,
        whale_patterns=whale_patterns,
        past_insights=past_insights,
        existing_triggers=existing_triggers,
        business_type=concepts.business_type or "business",
        business_description=concepts.business_description or "",
    )

    result = await llm_client.call_json(prompt, purpose="nightly_sweep")
    logger.info(
        "Nightly sweep complete: findings=%d, proposals=%d, adjustments=%d",
        len(result.get("findings", [])),
        len(result.get("trigger_proposals", [])),
        len(result.get("strategy_adjustments", [])),
    )

    # Store high-importance findings in memory
    for finding in result.get("findings", []):
        if finding.get("importance", 0) >= 0.6:
            try:
                await memory.store(
                    text=f"[{finding['type']}] {finding['description']}",
                    category="insight",
                    importance=finding["importance"],
                    tags=["nightly_sweep", finding.get("type", "general")],
                )
            except Exception as e:
                logger.warning("Failed to store finding in memory: %s", e)

    # Run DAG compaction: compact yesterday's Layer 0 events → Layer 1 per trigger
    if dag:
        from datetime import UTC
        from uuid import UUID

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        try:
            triggers = await _get_existing_triggers(internal_conn)
            for t in triggers:
                raw_id = t.get("id") or t.get("trigger_id", "")
                if raw_id:
                    try:
                        await dag.compact_trigger_daily(UUID(str(raw_id)), today, llm_client)
                    except Exception as compact_err:
                        logger.warning("DAG compaction failed for trigger %s: %s", raw_id, compact_err)
        except Exception as e:
            logger.warning("DAG nightly compaction failed: %s", e)

    return result


async def _analyze_cohorts(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    concepts: BusinessConcepts,
) -> list[dict[str, Any]]:
    """GROUP BY attribution source, compute conversion rates.

    All table/column names come from concepts — nothing is hardcoded.
    """
    if not concepts.attribution_table or not concepts.attribution_source_column:
        logger.info("No attribution table configured, skipping cohort analysis")
        return []

    customer_table = concepts.customer_table
    customer_id = concepts.customer_id_column
    attr_table = concepts.attribution_table
    attr_fk = concepts.attribution_fk_column or customer_id
    attr_source = concepts.attribution_source_column
    activation_table = concepts.activation_table
    act_fk = concepts.activation_fk_column or customer_id

    # Build activation join/condition
    if activation_table and act_fk:
        query = f"""
            SELECT
                a.{_qi(attr_source)} AS source,
                COUNT(DISTINCT c.{_qi(customer_id)}) AS total_customers,
                COUNT(DISTINCT act.{_qi(act_fk)}) AS activated_customers,
                CASE WHEN COUNT(DISTINCT c.{_qi(customer_id)}) > 0
                     THEN COUNT(DISTINCT act.{_qi(act_fk)})::float
                          / COUNT(DISTINCT c.{_qi(customer_id)})
                     ELSE 0 END AS conversion_rate
            FROM {_qi(customer_table)} c
            JOIN {_qi(attr_table)} a ON a.{_qi(attr_fk)} = c.{_qi(customer_id)}
            LEFT JOIN {_qi(activation_table)} act ON act.{_qi(act_fk)} = c.{_qi(customer_id)}
            GROUP BY a.{_qi(attr_source)}
            ORDER BY total_customers DESC
            LIMIT 20
        """
    else:
        # Without activation table, just count customers per source
        query = f"""
            SELECT
                a.{_qi(attr_source)} AS source,
                COUNT(DISTINCT c.{_qi(customer_id)}) AS total_customers,
                0 AS activated_customers,
                0.0 AS conversion_rate
            FROM {_qi(customer_table)} c
            JOIN {_qi(attr_table)} a ON a.{_qi(attr_fk)} = c.{_qi(customer_id)}
            GROUP BY a.{_qi(attr_source)}
            ORDER BY total_customers DESC
            LIMIT 20
        """

    try:
        rows = await conn.fetch(query)
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("Cohort analysis failed: %s", e)
        return []


async def _analyze_timing_patterns(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    concepts: BusinessConcepts,
) -> dict[str, Any]:
    """Extract hour-of-day and day-of-week patterns from creation and activation timestamps."""
    customer_table = concepts.customer_table
    created_at = concepts.customer_created_at_column
    activation_table = concepts.activation_table

    result: dict[str, Any] = {"signup_by_hour": [], "signup_by_dow": [], "activation_by_hour": []}

    if not created_at:
        logger.info("No created_at column configured, skipping timing analysis")
        return result

    # Signup by hour of day
    try:
        rows = await conn.fetch(
            f"""
            SELECT EXTRACT(HOUR FROM {_qi(created_at)})::int AS hour,
                   COUNT(*) AS count
            FROM {_qi(customer_table)}
            WHERE {_qi(created_at)} > NOW() - INTERVAL '90 days'
            GROUP BY hour ORDER BY hour
            """
        )
        result["signup_by_hour"] = [dict(r) for r in rows]
    except Exception as e:
        logger.warning("Signup-by-hour analysis failed: %s", e)

    # Signup by day of week
    try:
        rows = await conn.fetch(
            f"""
            SELECT EXTRACT(DOW FROM {_qi(created_at)})::int AS dow,
                   COUNT(*) AS count
            FROM {_qi(customer_table)}
            WHERE {_qi(created_at)} > NOW() - INTERVAL '90 days'
            GROUP BY dow ORDER BY dow
            """
        )
        result["signup_by_dow"] = [dict(r) for r in rows]
    except Exception as e:
        logger.warning("Signup-by-dow analysis failed: %s", e)

    # Activation by hour (if activation table exists)
    if activation_table and created_at:
        try:
            # Use the activation table's created_at or similar timestamp
            rows = await conn.fetch(
                f"""
                SELECT EXTRACT(HOUR FROM created_at)::int AS hour,
                       COUNT(*) AS count
                FROM {_qi(activation_table)}
                WHERE created_at > NOW() - INTERVAL '90 days'
                GROUP BY hour ORDER BY hour
                """
            )
            result["activation_by_hour"] = [dict(r) for r in rows]
        except Exception as e:
            logger.warning("Activation-by-hour analysis failed: %s", e)

    return result


async def _detect_dormancy(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    concepts: BusinessConcepts,
) -> int:
    """Find users who haven't had activity in 30+ days but were previously active."""
    customer_table = concepts.customer_table
    customer_id = concepts.customer_id_column
    activation_table = concepts.activation_table
    act_fk = concepts.activation_fk_column or customer_id

    if not activation_table:
        logger.info("No activation table configured, skipping dormancy detection")
        return 0

    try:
        count = await conn.fetchval(
            f"""
            SELECT COUNT(DISTINCT c.{_qi(customer_id)})
            FROM {_qi(customer_table)} c
            WHERE EXISTS (
                SELECT 1 FROM {_qi(activation_table)} act
                WHERE act.{_qi(act_fk)} = c.{_qi(customer_id)}
                  AND act.created_at < NOW() - INTERVAL '30 days'
            )
            AND NOT EXISTS (
                SELECT 1 FROM {_qi(activation_table)} act
                WHERE act.{_qi(act_fk)} = c.{_qi(customer_id)}
                  AND act.created_at >= NOW() - INTERVAL '30 days'
            )
            """
        )
        return count or 0
    except Exception as e:
        logger.warning("Dormancy detection failed: %s", e)
        return 0


async def _identify_whale_patterns(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    concepts: BusinessConcepts,
) -> list[dict[str, Any]]:
    """Find highest-value customers (by transaction amount) and their common attributes."""
    if not concepts.transaction_table or not concepts.transaction_amount_column:
        logger.info("No transaction table configured, skipping whale analysis")
        return []

    customer_table = concepts.customer_table
    customer_id = concepts.customer_id_column
    txn_table = concepts.transaction_table
    txn_fk = concepts.transaction_fk_column or customer_id
    txn_amount = concepts.transaction_amount_column
    txn_status = concepts.transaction_status_column
    txn_completed = concepts.transaction_completed_value

    # Build optional status filter
    status_filter = ""
    if txn_status and txn_completed:
        status_filter = f"AND t.{_qi(txn_status)} = '{txn_completed}'"

    # Divisor for cents vs dollars
    divisor = 100.0 if concepts.transaction_amount_is_cents else 1.0

    try:
        rows = await conn.fetch(
            f"""
            SELECT
                c.{_qi(customer_id)} AS customer_id,
                SUM(t.{_qi(txn_amount)}) / {divisor} AS total_spend,
                COUNT(t.*) AS transaction_count
            FROM {_qi(customer_table)} c
            JOIN {_qi(txn_table)} t ON t.{_qi(txn_fk)} = c.{_qi(customer_id)}
            WHERE TRUE {status_filter}
            GROUP BY c.{_qi(customer_id)}
            ORDER BY total_spend DESC
            LIMIT 50
            """
        )
        whales = [dict(r) for r in rows]

        if not whales:
            return []

        # Summarize whale patterns
        total_spend_values = [w["total_spend"] for w in whales]
        txn_counts = [w["transaction_count"] for w in whales]

        return [
            {
                "whale_count": len(whales),
                "avg_total_spend": sum(total_spend_values) / len(total_spend_values) if total_spend_values else 0,
                "avg_transaction_count": sum(txn_counts) / len(txn_counts) if txn_counts else 0,
                "min_whale_spend": min(total_spend_values) if total_spend_values else 0,
                "max_whale_spend": max(total_spend_values) if total_spend_values else 0,
            }
        ]
    except Exception as e:
        logger.warning("Whale pattern analysis failed: %s", e)
        return []


async def _get_existing_triggers(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> list[dict[str, Any]]:
    """Load existing active triggers from the internal database."""
    try:
        rows = await conn.fetch(
            """
            SELECT name, description, watch_table, watch_event, channel
            FROM growthclaw.triggers
            WHERE is_active = true
            """
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("Failed to load existing triggers: %s", e)
        return []


def _qi(name: str) -> str:
    """Quote a SQL identifier — strips everything except alphanumeric and underscore."""
    safe = "".join(c for c in name if c.isalnum() or c == "_")
    return f'"{safe}"'
