"""Tests for the Growth DAG hierarchical memory system."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from growthclaw.memory.dag import GrowthDAG
from growthclaw.memory.dag_models import DAGNode, SendOutcome


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Return a temp SQLite path for each test."""
    return str(tmp_path / "test_dag.db")


@pytest.fixture
async def dag(tmp_db):
    """Initialized GrowthDAG with a temp database."""
    d = GrowthDAG(db_path=tmp_db)
    await d.initialize()
    return d


def make_llm_client(response: dict) -> MagicMock:
    """Return a mock LLMClient whose call_json returns `response`."""
    client = MagicMock()
    client.call_json = AsyncMock(return_value=response)
    return client


def make_send_outcome(
    trigger_id: UUID | None = None,
    trigger_name: str = "test_trigger",
    channel: str = "sms",
    tone: str | None = "friendly",
    outcome: str | None = "converted",
    time_to_convert: float | None = 5.0,
) -> SendOutcome:
    return SendOutcome(
        trigger_id=trigger_id or uuid4(),
        trigger_name=trigger_name,
        user_id="user_001",
        channel=channel,
        message_body="Hello, buy now!",
        tone=tone,
        send_delay_minutes=30,
        outcome=outcome,
        time_to_convert_minutes=time_to_convert,
    )


COMPACT_RESPONSE = {
    "summary": "Friendly SMS messages converted at 50% in the afternoon.",
    "stats": {
        "total_sends": 2,
        "total_conversions": 1,
        "conversion_rate": 0.5,
        "best_performing_tone": "friendly",
        "best_performing_channel": "sms",
        "optimal_delay_minutes": 30,
        "notable_patterns": ["afternoon converts better"],
    },
}

CONDENSE_RESPONSE = {
    "summary": "Week showed strong SMS performance across all triggers.\n\nEmail underperformed vs SMS by 20%.",
    "stats": {
        "total_triggers_active": 2,
        "total_sends": 10,
        "total_conversions": 5,
        "overall_conversion_rate": 0.5,
        "cross_trigger_insights": ["SMS dominates"],
        "channel_comparison": {"sms": 0.55, "email": 0.35},
        "timing_insights": ["afternoon best"],
        "untested_opportunities": ["push notifications"],
    },
}

STRATEGY_RESPONSE = {
    "summary": "Core thesis: SMS with friendly tone wins.\n\nWhat's working: high conversion at 30min delay.\n\nOpportunity: email re-engagement.",
    "stats": {
        "core_growth_thesis": "Personalized SMS outreach converts best at 30-minute delay",
        "top_3_winning_patterns": ["friendly tone", "30min delay", "afternoon sends"],
        "top_3_opportunities": ["email re-engagement", "push notifications", "loyalty rewards"],
        "channel_strategy": "SMS primary, email secondary",
        "timing_strategy": "Send at 2-4 PM local time",
        "segment_strategy": "Focus on users who activated within 7 days",
    },
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_initialize_creates_tables(tmp_db):
    """initialize() creates dag_events and dag_nodes tables."""
    import aiosqlite

    dag = GrowthDAG(db_path=tmp_db)
    await dag.initialize()

    async with aiosqlite.connect(tmp_db) as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in await cursor.fetchall()}

    assert "dag_events" in tables
    assert "dag_nodes" in tables


async def test_store_event(dag):
    """store_event() persists a Layer 0 event and returns its UUID."""
    import aiosqlite

    trigger_id = uuid4()
    outcome = make_send_outcome(trigger_id=trigger_id)
    returned_id = await dag.store_event(outcome)

    assert returned_id == outcome.id

    async with aiosqlite.connect(dag.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM dag_events WHERE id = ?", (str(outcome.id),))
        row = await cursor.fetchone()

    assert row is not None
    assert row["trigger_name"] == "test_trigger"
    assert row["channel"] == "sms"
    assert row["outcome"] == "converted"
    assert row["tone"] == "friendly"


async def test_compact_trigger_daily_creates_layer1_node(dag):
    """compact_trigger_daily() creates a Layer 1 node linking back to Layer 0 events."""
    import aiosqlite

    trigger_id = uuid4()
    today = "2026-03-25"

    # Store two events for today
    e1 = make_send_outcome(trigger_id=trigger_id, outcome="converted")
    e2 = make_send_outcome(trigger_id=trigger_id, outcome="ignored")
    # Force created_at to today's date
    e1 = e1.model_copy(update={"created_at": datetime.fromisoformat(f"{today}T10:00:00")})
    e2 = e2.model_copy(update={"created_at": datetime.fromisoformat(f"{today}T14:00:00")})
    await dag.store_event(e1)
    await dag.store_event(e2)

    llm = make_llm_client(COMPACT_RESPONSE)
    node_id = await dag.compact_trigger_daily(trigger_id, today, llm)

    assert node_id is not None

    async with aiosqlite.connect(dag.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM dag_nodes WHERE id = ?", (str(node_id),))
        row = await cursor.fetchone()

    assert row is not None
    assert row["depth"] == 1
    assert row["period"] == today
    assert row["trigger_id"] == str(trigger_id)

    source_ids = json.loads(row["source_node_ids"])
    assert str(e1.id) in source_ids
    assert str(e2.id) in source_ids

    stats = json.loads(row["stats"])
    assert stats["total_sends"] == 2
    assert stats["conversion_rate"] == 0.5


async def test_compact_trigger_daily_returns_none_when_no_events(dag):
    """compact_trigger_daily() returns None when no events exist for that date."""
    llm = make_llm_client(COMPACT_RESPONSE)
    result = await dag.compact_trigger_daily(uuid4(), "2026-01-01", llm)
    assert result is None


async def test_condense_patterns_weekly_creates_layer2_node(dag):
    """condense_patterns_weekly() creates a Layer 2 node from Layer 1 nodes."""
    import aiosqlite

    # Manually insert two Layer 1 nodes for dates within a week
    node1_id = str(uuid4())
    node2_id = str(uuid4())
    week_start = "2026-03-23"  # Monday

    async with aiosqlite.connect(dag.db_path) as db:
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 1, ?, ?, ?, '[]', ?, ?)",
            (node1_id, str(uuid4()), "2026-03-23", "Trigger A performed well on Monday.", json.dumps({"total_sends": 5, "conversion_rate": 0.4}), datetime.now().isoformat()),
        )
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 1, ?, ?, ?, '[]', ?, ?)",
            (node2_id, str(uuid4()), "2026-03-24", "Trigger B had low conversion on Tuesday.", json.dumps({"total_sends": 5, "conversion_rate": 0.2}), datetime.now().isoformat()),
        )
        await db.commit()

    llm = make_llm_client(CONDENSE_RESPONSE)
    result_id = await dag.condense_patterns_weekly(week_start, llm)

    assert result_id is not None

    async with aiosqlite.connect(dag.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM dag_nodes WHERE id = ?", (str(result_id),))
        row = await cursor.fetchone()

    assert row is not None
    assert row["depth"] == 2
    assert "W" in row["period"]  # ISO week format like "2026-W13"

    source_ids = json.loads(row["source_node_ids"])
    assert node1_id in source_ids
    assert node2_id in source_ids


async def test_condense_patterns_weekly_returns_none_when_no_layer1(dag):
    """condense_patterns_weekly() returns None when no Layer 1 nodes exist."""
    llm = make_llm_client(CONDENSE_RESPONSE)
    result = await dag.condense_patterns_weekly("2026-01-01", llm)
    assert result is None


async def test_synthesize_strategy_monthly_creates_layer3_node(dag):
    """synthesize_strategy_monthly() creates a Layer 3 node from Layer 2 nodes."""
    import aiosqlite

    # Insert two Layer 2 nodes for the same month
    node1_id = str(uuid4())
    node2_id = str(uuid4())
    month = "2026-03"

    async with aiosqlite.connect(dag.db_path) as db:
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 2, NULL, ?, ?, '[]', ?, ?)",
            (node1_id, "2026-W12", "Week 12 showed strong SMS performance.", json.dumps({"overall_conversion_rate": 0.4}), datetime.now().isoformat()),
        )
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 2, NULL, ?, ?, '[]', ?, ?)",
            (node2_id, "2026-W13", "Week 13 showed email improving.", json.dumps({"overall_conversion_rate": 0.45}), datetime.now().isoformat()),
        )
        await db.commit()

    from growthclaw.models.schema_map import BusinessConcepts

    concepts = BusinessConcepts(
        business_type="ecommerce",
        business_description="Online pet supplies store",
        customer_table="customers",
        customer_id_column="id",
    )

    llm = make_llm_client(STRATEGY_RESPONSE)
    result_id = await dag.synthesize_strategy_monthly(month, llm, concepts)

    assert result_id is not None

    async with aiosqlite.connect(dag.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM dag_nodes WHERE id = ?", (str(result_id),))
        row = await cursor.fetchone()

    assert row is not None
    assert row["depth"] == 3
    assert row["period"] == month

    source_ids = json.loads(row["source_node_ids"])
    assert node1_id in source_ids
    assert node2_id in source_ids


async def test_expand_drills_to_source_events(dag):
    """expand() on a Layer 1 node returns the original Layer 0 events."""
    trigger_id = uuid4()
    today = "2026-03-25"

    e1 = make_send_outcome(trigger_id=trigger_id, outcome="converted")
    e2 = make_send_outcome(trigger_id=trigger_id, outcome="ignored")
    e1 = e1.model_copy(update={"created_at": datetime.fromisoformat(f"{today}T10:00:00")})
    e2 = e2.model_copy(update={"created_at": datetime.fromisoformat(f"{today}T11:00:00")})

    await dag.store_event(e1)
    await dag.store_event(e2)

    llm = make_llm_client(COMPACT_RESPONSE)
    node_id = await dag.compact_trigger_daily(trigger_id, today, llm)
    assert node_id is not None

    expanded = await dag.expand(node_id)
    assert len(expanded) == 2

    expanded_ids = {n.id for n in expanded}
    assert e1.id in expanded_ids
    assert e2.id in expanded_ids

    # All expanded nodes should be depth=0
    assert all(n.depth == 0 for n in expanded)


async def test_expand_layer2_returns_layer1_nodes(dag):
    """expand() on a Layer 2 node returns its Layer 1 source nodes."""
    import aiosqlite

    node1_id = str(uuid4())
    node2_id = str(uuid4())
    layer2_id = str(uuid4())

    async with aiosqlite.connect(dag.db_path) as db:
        # Insert two Layer 1 nodes
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 1, ?, '2026-03-23', 'L1 node A', '[]', '{}', ?)",
            (node1_id, str(uuid4()), datetime.now().isoformat()),
        )
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 1, ?, '2026-03-24', 'L1 node B', '[]', '{}', ?)",
            (node2_id, str(uuid4()), datetime.now().isoformat()),
        )
        # Insert a Layer 2 node referencing them
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 2, NULL, '2026-W13', 'L2 pattern', ?, '{}', ?)",
            (layer2_id, json.dumps([node1_id, node2_id]), datetime.now().isoformat()),
        )
        await db.commit()

    expanded = await dag.expand(UUID(layer2_id))
    assert len(expanded) == 2
    assert all(n.depth == 1 for n in expanded)


async def test_get_composition_context_returns_relevant(dag):
    """get_composition_context() returns Layer 1 nodes for the correct trigger."""
    import aiosqlite

    trigger_a_id = str(uuid4())
    trigger_b_id = str(uuid4())

    # Store events for two different triggers
    e_a = make_send_outcome(trigger_id=UUID(trigger_a_id), trigger_name="cart_abandonment", channel="sms")
    e_b = make_send_outcome(trigger_id=UUID(trigger_b_id), trigger_name="welcome_flow", channel="email")

    await dag.store_event(e_a)
    await dag.store_event(e_b)

    today = "2026-03-25"
    e_a = e_a.model_copy(update={"created_at": datetime.fromisoformat(f"{today}T09:00:00")})
    e_b = e_b.model_copy(update={"created_at": datetime.fromisoformat(f"{today}T09:30:00")})

    # Insert Layer 1 nodes for both triggers
    node_a_id = str(uuid4())
    node_b_id = str(uuid4())

    async with aiosqlite.connect(dag.db_path) as db:
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 1, ?, '2026-03-25', 'Cart abandonment SMS worked well.', '[]', '{}', ?)",
            (node_a_id, trigger_a_id, datetime.now().isoformat()),
        )
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 1, ?, '2026-03-25', 'Welcome email had poor open rate.', '[]', '{}', ?)",
            (node_b_id, trigger_b_id, datetime.now().isoformat()),
        )
        await db.commit()

    # Query for cart_abandonment SMS context
    context = await dag.get_composition_context("cart_abandonment", "sms")

    assert len(context) >= 1
    assert any("Cart abandonment" in n.summary_text for n in context)
    # Should not include the welcome email node
    assert not any("Welcome email" in n.summary_text for n in context)


async def test_export_for_cloud_only_exports_layer2_plus(dag):
    """export_for_cloud() only includes Layer 2+ nodes — never raw customer data."""
    import aiosqlite

    # Store a Layer 0 event
    e = make_send_outcome()
    await dag.store_event(e)

    # Insert Layer 1 and Layer 2 nodes
    l1_id = str(uuid4())
    l2_id = str(uuid4())

    async with aiosqlite.connect(dag.db_path) as db:
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 1, ?, '2026-03-25', 'Daily summary with user data.', '[]', '{}', ?)",
            (l1_id, str(uuid4()), datetime.now().isoformat()),
        )
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 2, NULL, '2026-W13', 'Weekly pattern summary — anonymized.', ?, '{}', ?)",
            (l2_id, json.dumps([l1_id]), datetime.now().isoformat()),
        )
        await db.commit()

    exported = await dag.export_for_cloud()

    # Must not include Layer 0 (raw events) or Layer 1 (per-trigger daily)
    depths = [item["depth"] for item in exported]
    assert all(d >= 2 for d in depths), f"Found unexpected depths: {depths}"

    # Should include the Layer 2 node
    ids = [item["id"] for item in exported]
    assert l2_id in ids
    assert l1_id not in ids

    # Should not have user_id or message_body (raw customer fields)
    for item in exported:
        assert "user_id" not in item
        assert "message_body" not in item


async def test_grep_finds_nodes_by_keyword(dag):
    """grep() returns nodes whose summary_text matches the query."""
    import aiosqlite

    async with aiosqlite.connect(dag.db_path) as db:
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 2, NULL, '2026-W13', 'Urgency messaging doubled conversions this week.', '[]', '{}', ?)",
            (str(uuid4()), datetime.now().isoformat()),
        )
        await db.execute(
            "INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at) VALUES (?, 2, NULL, '2026-W14', 'Friendly tone saw flat performance.', '[]', '{}', ?)",
            (str(uuid4()), datetime.now().isoformat()),
        )
        await db.commit()

    llm = make_llm_client({})
    results = await dag.grep("urgency", llm)

    assert len(results) == 1
    assert "urgency" in results[0].summary_text.lower()
