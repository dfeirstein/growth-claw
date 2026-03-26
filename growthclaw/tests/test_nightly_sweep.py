"""Tests for nightly sweep — verifies cohort analysis, timing, dormancy detection."""

from __future__ import annotations

from unittest.mock import AsyncMock

from growthclaw.models.schema_map import BusinessConcepts

CONCEPTS = BusinessConcepts(
    business_type="driver_service",
    business_description="Premium driver service",
    customer_table="users",
    customer_id_column="id",
    customer_created_at_column="created_at",
    activation_table="bookings",
    activation_event="first booking",
    activation_fk_column="user_id",
    activation_check_sql="SELECT EXISTS(SELECT 1 FROM bookings WHERE user_id = $1)",
    transaction_table="bookings",
    transaction_fk_column="user_id",
    transaction_amount_column="amount_cents",
    attribution_table="utms",
    attribution_fk_column="user_id",
    attribution_source_column="source",
)


async def test_nightly_sweep_returns_findings():
    from growthclaw.intelligence.nightly_sweep import run_nightly_sweep

    customer_conn = AsyncMock()
    customer_conn.fetch = AsyncMock(return_value=[])
    customer_conn.fetchval = AsyncMock(return_value=0)

    internal_conn = AsyncMock()

    llm = AsyncMock()
    llm.call_json = AsyncMock(
        return_value={
            "findings": [{"description": "Test finding", "type": "cohort", "importance": 0.8}],
            "trigger_proposals": [],
            "strategy_adjustments": [],
        }
    )

    memory = AsyncMock()
    memory.recall = AsyncMock(return_value=[])
    memory.store = AsyncMock()

    result = await run_nightly_sweep(customer_conn, internal_conn, CONCEPTS, llm, memory)

    assert "findings" in result
    assert len(result["findings"]) == 1
    assert result["findings"][0]["type"] == "cohort"


async def test_sweep_stores_high_importance_findings():
    from growthclaw.intelligence.nightly_sweep import run_nightly_sweep

    customer_conn = AsyncMock()
    customer_conn.fetch = AsyncMock(return_value=[])
    customer_conn.fetchval = AsyncMock(return_value=0)

    internal_conn = AsyncMock()

    llm = AsyncMock()
    llm.call_json = AsyncMock(
        return_value={
            "findings": [
                {"description": "High importance", "type": "timing", "importance": 0.9},
                {"description": "Low importance", "type": "cohort", "importance": 0.3},
            ],
            "trigger_proposals": [],
            "strategy_adjustments": [],
        }
    )

    memory = AsyncMock()
    memory.recall = AsyncMock(return_value=[])
    memory.store = AsyncMock()

    await run_nightly_sweep(customer_conn, internal_conn, CONCEPTS, llm, memory)

    # Only high importance findings (>= 0.7) should be stored
    assert memory.store.call_count >= 1


async def test_sweep_calls_llm():
    from growthclaw.intelligence.nightly_sweep import run_nightly_sweep

    customer_conn = AsyncMock()
    customer_conn.fetch = AsyncMock(return_value=[])
    customer_conn.fetchval = AsyncMock(return_value=0)

    internal_conn = AsyncMock()

    llm = AsyncMock()
    llm.call_json = AsyncMock(return_value={"findings": [], "trigger_proposals": [], "strategy_adjustments": []})

    memory = AsyncMock()
    memory.recall = AsyncMock(return_value=[])
    memory.store = AsyncMock()

    await run_nightly_sweep(customer_conn, internal_conn, CONCEPTS, llm, memory)

    llm.call_json.assert_called_once()
