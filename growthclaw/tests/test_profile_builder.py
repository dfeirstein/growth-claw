"""Tests for profile_builder — verifies generic profile query execution with mock data."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from growthclaw.intelligence.profile_builder import build_profile
from growthclaw.models.trigger import ProfileQuery, TriggerRule


def _trigger_with_queries(queries: list[ProfileQuery]) -> TriggerRule:
    """Create a TriggerRule with the given profile queries."""
    return TriggerRule(
        name="test_trigger",
        description="Test trigger",
        watch_table="users",
        watch_event="INSERT",
        check_sql="SELECT TRUE",
        profile_queries=queries,
    )


def _make_record(mapping: dict) -> MagicMock:
    """Create a mock asyncpg Record."""
    rec = MagicMock()
    rec.__getitem__ = lambda self, key: mapping[key]
    rec.keys.return_value = mapping.keys()
    rec.values.return_value = mapping.values()
    rec.items.return_value = mapping.items()

    def to_dict(self=rec):
        return dict(mapping)

    rec.__iter__ = lambda self: iter(mapping)
    return rec


# ---------------------------------------------------------------------------
# Basic execution tests
# ---------------------------------------------------------------------------

async def test_executes_all_profile_queries():
    """All profile queries are executed and results collected."""
    queries = [
        ProfileQuery(name="basic_info", sql="SELECT * FROM users WHERE id = $1", description="Basic info"),
        ProfileQuery(name="orders", sql="SELECT * FROM orders WHERE user_id = $1", description="Orders"),
        ProfileQuery(name="cards", sql="SELECT * FROM cards WHERE user_id = $1", description="Cards"),
    ]
    trigger = _trigger_with_queries(queries)

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"id": 1, "name": "Alice"}])

    profile = await build_profile(conn, "123", trigger)

    assert "basic_info" in profile
    assert "orders" in profile
    assert "cards" in profile
    assert conn.fetch.call_count == 3


async def test_profile_returns_list_of_dicts():
    """Each profile query result is returned as a list of dicts."""
    queries = [
        ProfileQuery(name="orders", sql="SELECT * FROM orders WHERE user_id = $1", description="Orders"),
    ]
    trigger = _trigger_with_queries(queries)

    mock_rows = [{"id": 1, "total": 5000}, {"id": 2, "total": 3000}]
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=mock_rows)

    profile = await build_profile(conn, "42", trigger)
    assert len(profile["orders"]) == 2
    assert profile["orders"][0]["total"] == 5000


async def test_empty_profile_queries():
    """No queries means empty profile dict and no DB calls."""
    trigger = _trigger_with_queries([])
    conn = AsyncMock()

    profile = await build_profile(conn, "123", trigger)

    assert profile == {}
    conn.fetch.assert_not_called()


async def test_single_query():
    """Single profile query works correctly."""
    queries = [
        ProfileQuery(name="user_info", sql="SELECT email, name FROM users WHERE id = $1", description="User info"),
    ]
    trigger = _trigger_with_queries(queries)

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"email": "alice@test.com", "name": "Alice"}])

    profile = await build_profile(conn, "1", trigger)
    assert profile["user_info"][0]["email"] == "alice@test.com"


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

async def test_handles_failed_query_gracefully():
    """A failing query results in None for that key, other queries still succeed."""
    queries = [
        ProfileQuery(name="good", sql="SELECT 1", description="Works"),
        ProfileQuery(name="bad", sql="SELECT invalid", description="Fails"),
        ProfileQuery(name="also_good", sql="SELECT 2", description="Also works"),
    ]
    trigger = _trigger_with_queries(queries)

    call_count = 0

    async def mock_fetch(sql, *args):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception("Query failed")
        return [{"result": call_count}]

    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=mock_fetch)

    profile = await build_profile(conn, "123", trigger)

    assert profile["good"] is not None
    assert profile["bad"] is None
    assert profile["also_good"] is not None


async def test_all_queries_fail():
    """When all queries fail, profile has all None values."""
    queries = [
        ProfileQuery(name="q1", sql="SELECT bad", description="Fail 1"),
        ProfileQuery(name="q2", sql="SELECT bad", description="Fail 2"),
    ]
    trigger = _trigger_with_queries(queries)

    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=RuntimeError("DB error"))

    profile = await build_profile(conn, "123", trigger)
    assert profile["q1"] is None
    assert profile["q2"] is None


async def test_query_returns_empty_result():
    """An empty result set is stored as an empty list, not None."""
    queries = [
        ProfileQuery(name="empty", sql="SELECT * FROM orders WHERE user_id = $1", description="No rows"),
    ]
    trigger = _trigger_with_queries(queries)

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    profile = await build_profile(conn, "999", trigger)
    assert profile["empty"] == []


# ---------------------------------------------------------------------------
# User ID conversion tests
# ---------------------------------------------------------------------------

async def test_numeric_user_id_conversion():
    """Numeric string user_ids are converted to int for parameterized queries."""
    queries = [ProfileQuery(name="test", sql="SELECT 1 WHERE id = $1", description="test")]
    trigger = _trigger_with_queries(queries)

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    await build_profile(conn, "456", trigger)

    conn.fetch.assert_called_once_with("SELECT 1 WHERE id = $1", 456)


async def test_non_numeric_user_id():
    """Non-numeric IDs (UUIDs, etc.) stay as strings."""
    queries = [ProfileQuery(name="test", sql="SELECT 1 WHERE id = $1", description="test")]
    trigger = _trigger_with_queries(queries)

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    await build_profile(conn, "uuid-abc-123", trigger)

    conn.fetch.assert_called_once_with("SELECT 1 WHERE id = $1", "uuid-abc-123")


async def test_zero_user_id_is_numeric():
    """User ID '0' is treated as numeric."""
    queries = [ProfileQuery(name="test", sql="SELECT 1 WHERE id = $1", description="test")]
    trigger = _trigger_with_queries(queries)

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    await build_profile(conn, "0", trigger)

    conn.fetch.assert_called_once_with("SELECT 1 WHERE id = $1", 0)


# ---------------------------------------------------------------------------
# Realistic profile scenarios
# ---------------------------------------------------------------------------

async def test_ecommerce_profile():
    """Realistic ecommerce profile with customer info, orders, and items."""
    queries = [
        ProfileQuery(
            name="customer",
            sql='SELECT first_name, email, created_at FROM customers WHERE id = $1',
            description="Basic customer info",
        ),
        ProfileQuery(
            name="recent_orders",
            sql=(
                "SELECT id, total_cents, status, created_at FROM orders"
                " WHERE customer_id = $1 ORDER BY created_at DESC LIMIT 5"
            ),
            description="Recent orders",
        ),
        ProfileQuery(
            name="order_count",
            sql='SELECT COUNT(*) as count FROM orders WHERE customer_id = $1',
            description="Total order count",
        ),
    ]
    trigger = _trigger_with_queries(queries)

    call_index = 0
    responses = [
        [{"first_name": "Alice", "email": "alice@example.com", "created_at": "2024-01-15"}],
        [
            {"id": 101, "total_cents": 5999, "status": "delivered", "created_at": "2024-12-01"},
            {"id": 102, "total_cents": 2499, "status": "shipped", "created_at": "2024-12-10"},
        ],
        [{"count": 7}],
    ]

    async def mock_fetch(sql, *args):
        nonlocal call_index
        result = responses[call_index]
        call_index += 1
        return result

    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=mock_fetch)

    profile = await build_profile(conn, "42", trigger)

    assert profile["customer"][0]["first_name"] == "Alice"
    assert len(profile["recent_orders"]) == 2
    assert profile["order_count"][0]["count"] == 7


async def test_driver_service_profile():
    """Realistic driver service profile with bookings and subscription."""
    queries = [
        ProfileQuery(
            name="user_info",
            sql='SELECT first_name, phone, created_at FROM users WHERE id = $1',
            description="User info",
        ),
        ProfileQuery(
            name="booking_history",
            sql=(
                "SELECT status, total_cents, scheduled_at FROM bookings"
                " WHERE user_id = $1 ORDER BY scheduled_at DESC LIMIT 3"
            ),
            description="Recent bookings",
        ),
        ProfileQuery(
            name="subscription",
            sql=(
                "SELECT plan_name, status, monthly_amount_cents FROM subscriptions"
                " WHERE user_id = $1 AND status = 'active'"
            ),
            description="Active subscription",
        ),
    ]
    trigger = _trigger_with_queries(queries)

    call_index = 0
    responses = [
        [{"first_name": "Michael", "phone": "+12125551234", "created_at": "2024-03-20"}],
        [
            {"status": "completed", "total_cents": 12000, "scheduled_at": "2024-12-20T19:00:00Z"},
            {"status": "completed", "total_cents": 15000, "scheduled_at": "2024-12-15T08:00:00Z"},
        ],
        [{"plan_name": "premium", "status": "active", "monthly_amount_cents": 49900}],
    ]

    async def mock_fetch(sql, *args):
        nonlocal call_index
        result = responses[call_index]
        call_index += 1
        return result

    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=mock_fetch)

    profile = await build_profile(conn, "5", trigger)

    assert profile["user_info"][0]["first_name"] == "Michael"
    assert len(profile["booking_history"]) == 2
    assert profile["subscription"][0]["plan_name"] == "premium"
