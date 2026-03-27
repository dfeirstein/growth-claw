"""Funnel analyzer — computes funnel statistics and uses LLM to identify lifecycle stages and drop-offs."""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from growthclaw.llm.client import LLMClient, render_template
from growthclaw.models.schema_map import BusinessConcepts, Funnel

logger = logging.getLogger("growthclaw.discovery.funnel_analyzer")


async def _count_customers(conn: asyncpg.Connection, concepts: BusinessConcepts) -> int:  # type: ignore[type-arg]
    """Count total customers based on discovered concepts."""
    table = concepts.customer_table
    id_col = concepts.customer_id_column

    filters = []
    if concepts.soft_delete_column:
        filters.append(f'"{concepts.soft_delete_column}" IS NULL')
    if concepts.customer_type_column and concepts.customer_type_value:
        filters.append(f"\"{concepts.customer_type_column}\" = '{concepts.customer_type_value}'")
    for f in concepts.exclude_filters:
        filters.append(f)

    where = f" WHERE {' AND '.join(filters)}" if filters else ""
    query = f'SELECT COUNT(DISTINCT "{id_col}") FROM "{table}"{where}'  # noqa: S608
    return await conn.fetchval(query) or 0


async def _count_activated(conn: asyncpg.Connection, concepts: BusinessConcepts) -> int:  # type: ignore[type-arg]
    """Count customers who completed the activation step."""
    if not concepts.activation_table or not concepts.activation_fk_column:
        return 0
    table = concepts.activation_table
    fk = concepts.activation_fk_column

    filters = []
    if concepts.activation_soft_delete:
        col = concepts.activation_soft_delete
        # If it's just a column name, wrap with IS NULL; if it's already a full expression, use as-is
        if " " not in col:
            filters.append(f'"{col}" IS NULL')
        else:
            filters.append(col)

    where = f" WHERE {' AND '.join(filters)}" if filters else ""
    query = f'SELECT COUNT(DISTINCT "{fk}") FROM "{table}"{where}'  # noqa: S608
    return await conn.fetchval(query) or 0


async def _count_transacted(conn: asyncpg.Connection, concepts: BusinessConcepts) -> int:  # type: ignore[type-arg]
    """Count customers with completed transactions."""
    if not concepts.transaction_table or not concepts.transaction_fk_column:
        return 0
    table = concepts.transaction_table
    fk = concepts.transaction_fk_column

    filters = []
    if concepts.transaction_status_column and concepts.transaction_completed_value:
        filters.append(f"\"{concepts.transaction_status_column}\" = '{concepts.transaction_completed_value}'")

    where = f" WHERE {' AND '.join(filters)}" if filters else ""
    query = f'SELECT COUNT(DISTINCT "{fk}") FROM "{table}"{where}'  # noqa: S608
    return await conn.fetchval(query) or 0


async def _count_subscribed(conn: asyncpg.Connection, concepts: BusinessConcepts) -> int:  # type: ignore[type-arg]
    """Count customers with active subscriptions."""
    if not concepts.subscription_table or not concepts.subscription_fk_column:
        return 0
    table = concepts.subscription_table
    fk = concepts.subscription_fk_column

    filters = []
    if concepts.subscription_status_column and concepts.subscription_active_value:
        filters.append(f"\"{concepts.subscription_status_column}\" = '{concepts.subscription_active_value}'")

    where = f" WHERE {' AND '.join(filters)}" if filters else ""
    query = f'SELECT COUNT(DISTINCT "{fk}") FROM "{table}"{where}'  # noqa: S608
    return await conn.fetchval(query) or 0


async def _count_sms_consent(conn: asyncpg.Connection, concepts: BusinessConcepts) -> int:  # type: ignore[type-arg]
    """Count customers with SMS consent."""
    if not concepts.sms_consent_check:
        return 0
    table = concepts.customer_table
    query = f'SELECT COUNT(*) FROM "{table}" WHERE {concepts.sms_consent_check}'  # noqa: S608
    return await conn.fetchval(query) or 0


async def _time_to_activation_distribution(
    conn: asyncpg.Connection,
    concepts: BusinessConcepts,  # type: ignore[type-arg]
) -> dict[str, Any]:
    """Compute distribution of time between signup and activation."""
    if not concepts.activation_table or not concepts.activation_fk_column or not concepts.customer_created_at_column:
        return {}

    ct = concepts.customer_table
    at = concepts.activation_table
    cid = concepts.customer_id_column
    afk = concepts.activation_fk_column
    cat = concepts.customer_created_at_column

    query = f"""
        SELECT
            COUNT(*) FILTER (WHERE diff_minutes <= 15) as within_15min,
            COUNT(*) FILTER (WHERE diff_minutes <= 30) as within_30min,
            COUNT(*) FILTER (WHERE diff_minutes <= 60) as within_1hour,
            COUNT(*) FILTER (WHERE diff_minutes <= 1440) as within_24hours,
            COUNT(*) as total,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY diff_minutes) as median_minutes
        FROM (
            SELECT EXTRACT(EPOCH FROM (MIN(a.created_at) - c."{cat}")) / 60.0 as diff_minutes
            FROM "{ct}" c
            JOIN "{at}" a ON a."{afk}" = c."{cid}"
            WHERE c."{cat}" IS NOT NULL
            GROUP BY c."{cid}", c."{cat}"
            HAVING EXTRACT(EPOCH FROM (MIN(a.created_at) - c."{cat}")) > 0
        ) timing
    """  # noqa: S608

    try:
        row = await conn.fetchrow(query)
        if not row:
            return {}
        return {
            "within_15min": row["within_15min"] or 0,
            "within_30min": row["within_30min"] or 0,
            "within_1hour": row["within_1hour"] or 0,
            "within_24hours": row["within_24hours"] or 0,
            "total_activated": row["total"] or 0,
            "median_minutes": round(float(row["median_minutes"]), 1) if row["median_minutes"] else None,
        }
    except Exception as e:
        logger.warning("Time-to-activation query failed: %s", e)
        return {}


async def analyze_funnel(
    concepts: BusinessConcepts,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    llm_client: LLMClient,
) -> Funnel:
    """Analyze the customer funnel: compute stats, then use LLM to identify stages and drop-offs."""
    # Compute aggregate statistics
    customer_count = await _count_customers(conn, concepts)
    activated_count = await _count_activated(conn, concepts)
    transacted_count = await _count_transacted(conn, concepts)
    subscribed_count = await _count_subscribed(conn, concepts)
    sms_consent_count = await _count_sms_consent(conn, concepts)
    time_distribution = await _time_to_activation_distribution(conn, concepts)

    activation_rate = round(activated_count / customer_count * 100, 1) if customer_count > 0 else 0.0

    logger.info(
        "Funnel stats: %d customers, %d activated (%.1f%%), %d transacted, %d subscribed",
        customer_count,
        activated_count,
        activation_rate,
        transacted_count,
        subscribed_count,
    )

    # Render prompt and call LLM
    prompt = render_template(
        "analyze_funnel.j2",
        business_type=concepts.business_type,
        business_description=concepts.business_description,
        concepts=concepts.model_dump(mode="json"),
        customer_count=customer_count,
        activation_event=concepts.activation_event or "unknown",
        activated_count=activated_count,
        activation_rate=activation_rate,
        transacted_count=transacted_count,
        subscribed_count=subscribed_count,
        sms_consent_count=sms_consent_count,
        time_to_activation_distribution=time_distribution,
    )

    result = await llm_client.call_json(prompt, temperature=0.1, purpose="funnel_analysis")
    funnel = Funnel.model_validate(result)

    logger.info(
        "Funnel analysis: %d stages, biggest dropoff: %s",
        len(funnel.stages),
        funnel.biggest_dropoff.description if funnel.biggest_dropoff else "none",
    )

    return funnel
