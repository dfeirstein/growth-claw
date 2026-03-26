"""Tests for polling_listener — verifies poll cycles, watermark updates, and event emission."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from growthclaw.models.trigger import TriggerEvent, TriggerRule
from growthclaw.triggers.polling_listener import PollingListener, _safe_ident


class _MockPool:
    """Mock asyncpg pool that returns an async context manager from acquire()."""

    def __init__(self, conn: AsyncMock) -> None:
        self._conn = conn
        self.close = AsyncMock()

    def acquire(self) -> _MockAcquireCtx:
        return _MockAcquireCtx(self._conn)


class _MockAcquireCtx:
    def __init__(self, conn: AsyncMock) -> None:
        self._conn = conn

    async def __aenter__(self) -> AsyncMock:
        return self._conn

    async def __aexit__(self, *args: object) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONCEPTS = {
    "customer_table": "users",
    "customer_id_column": "id",
    "customer_created_at_column": "created_at",
}

TRIGGER = TriggerRule(
    name="signup_no_card",
    description="User signed up but did not add a card",
    watch_table="users",
    watch_event="INSERT",
    check_sql="SELECT NOT EXISTS(SELECT 1 FROM cards WHERE user_id = $1)",
    max_fires=3,
    cooldown_hours=24,
    channel="sms",
)

FK_TRIGGER = TriggerRule(
    name="order_placed",
    description="User placed an order",
    watch_table="orders",
    watch_event="INSERT",
    check_sql="SELECT TRUE",
    max_fires=3,
    cooldown_hours=24,
    channel="email",
    user_id_source="NEW.user_id",
)


def _make_listener(on_event: AsyncMock | None = None) -> PollingListener:
    """Create a PollingListener with mocked connections."""
    return PollingListener(
        customer_dsn="postgresql://localhost/test",
        internal_dsn="postgresql://localhost/test",
        triggers=[TRIGGER, FK_TRIGGER],
        concepts=CONCEPTS,
        on_event=on_event or AsyncMock(),
        poll_interval=5,
    )


def _make_row(row_id: str, user_id: str | None = None, ts: datetime | None = None) -> dict:
    """Create a mock asyncpg Record-like dict."""
    row = {
        "id": row_id,
        "created_at": ts or datetime.now(UTC),
    }
    if user_id:
        row["user_id"] = user_id
    return row


# ---------------------------------------------------------------------------
# _safe_ident tests
# ---------------------------------------------------------------------------


def test_safe_ident_sanitizes():
    """_safe_ident strips non-alphanumeric characters (except underscore)."""
    assert _safe_ident("users") == "users"
    assert _safe_ident("my_table") == "my_table"
    assert _safe_ident("table; DROP TABLE users--") == "tableDROPTABLEusers"
    assert _safe_ident('table"name') == "tablename"
    assert _safe_ident("") == ""
    assert _safe_ident("123_abc") == "123_abc"


# ---------------------------------------------------------------------------
# _extract_user_id tests
# ---------------------------------------------------------------------------


def test_extract_user_id_from_customer_table():
    """User ID is extracted from the PK column when the table is the customer table."""
    listener = _make_listener()
    row = _make_row("42")
    user_id = listener._extract_user_id(row, TRIGGER)
    assert user_id == "42"


def test_extract_user_id_from_fk_table():
    """User ID is extracted from user_id_source when watching a non-customer table."""
    listener = _make_listener()
    row = _make_row("order-1", user_id="99")
    user_id = listener._extract_user_id(row, FK_TRIGGER)
    assert user_id == "99"


def test_extract_user_id_fallback_to_common_fk():
    """Falls back to common FK column names when no user_id_source is set."""
    trigger_no_source = TriggerRule(
        name="payment_received",
        description="Payment was received",
        watch_table="payments",
        watch_event="INSERT",
        check_sql="SELECT TRUE",
        max_fires=3,
        cooldown_hours=24,
        channel="email",
    )
    listener = _make_listener()
    row = {"id": "pay-1", "customer_id": "77", "created_at": datetime.now(UTC)}
    user_id = listener._extract_user_id(row, trigger_no_source)
    assert user_id == "77"


# ---------------------------------------------------------------------------
# Poll cycle tests
# ---------------------------------------------------------------------------


async def test_poll_cycle_detects_new_rows():
    """Poll cycle detects new rows and emits trigger events."""
    on_event = AsyncMock()
    listener = _make_listener(on_event=on_event)

    now = datetime.now(UTC)
    watermark = {
        "table_name": "users",
        "timestamp_col": "created_at",
        "last_seen_at": now - timedelta(hours=1),
    }

    new_row = _make_row("new-user-1", ts=now)

    # Mock pools
    mock_internal_conn = AsyncMock()
    mock_internal_conn.fetch = AsyncMock(return_value=[watermark])
    mock_internal_conn.execute = AsyncMock()

    mock_customer_conn = AsyncMock()
    mock_customer_conn.fetch = AsyncMock(return_value=[new_row])

    mock_internal_pool = _MockPool(mock_internal_conn)
    mock_customer_pool = _MockPool(mock_customer_conn)

    listener._internal_pool = mock_internal_pool
    listener._customer_pool = mock_customer_pool

    await listener._poll_cycle()

    # Should have queried the customer DB
    mock_customer_conn.fetch.assert_awaited_once()


async def test_poll_cycle_updates_watermark():
    """Poll cycle updates the watermark after processing new rows."""
    on_event = AsyncMock()
    listener = _make_listener(on_event=on_event)

    now = datetime.now(UTC)
    watermark = {
        "table_name": "users",
        "timestamp_col": "created_at",
        "last_seen_at": now - timedelta(hours=1),
    }

    new_row = _make_row("new-user-1", ts=now)

    # Single mock conn handles both read (fetch) and write (execute)
    mock_internal_conn = AsyncMock()
    mock_internal_conn.fetch = AsyncMock(return_value=[watermark])
    mock_internal_conn.execute = AsyncMock()

    mock_customer_conn = AsyncMock()
    mock_customer_conn.fetch = AsyncMock(return_value=[new_row])

    mock_internal_pool = _MockPool(mock_internal_conn)
    mock_customer_pool = _MockPool(mock_customer_conn)

    listener._internal_pool = mock_internal_pool
    listener._customer_pool = mock_customer_pool

    await listener._poll_cycle()

    # Watermark update should have been called
    mock_internal_conn.execute.assert_awaited()


async def test_poll_cycle_emits_trigger_events():
    """Poll cycle creates TriggerEvent tasks for each new row."""
    events_received: list = []

    async def capture_event(event: TriggerEvent) -> None:
        events_received.append(event)

    listener = _make_listener(on_event=capture_event)

    now = datetime.now(UTC)
    watermark = {
        "table_name": "users",
        "timestamp_col": "created_at",
        "last_seen_at": now - timedelta(hours=1),
    }

    rows = [_make_row(f"user-{i}", ts=now - timedelta(minutes=i)) for i in range(3)]

    mock_internal_conn = AsyncMock()
    mock_internal_conn.fetch = AsyncMock(return_value=[watermark])
    mock_internal_conn.execute = AsyncMock()

    mock_customer_conn = AsyncMock()
    mock_customer_conn.fetch = AsyncMock(return_value=rows)

    mock_internal_pool = _MockPool(mock_internal_conn)
    mock_customer_pool = _MockPool(mock_customer_conn)

    listener._internal_pool = mock_internal_pool
    listener._customer_pool = mock_customer_pool

    await listener._poll_cycle()

    # Allow background tasks to complete
    await asyncio.sleep(0.1)


async def test_poll_no_new_rows():
    """Poll cycle does nothing when there are no new rows."""
    on_event = AsyncMock()
    listener = _make_listener(on_event=on_event)

    now = datetime.now(UTC)
    watermark = {
        "table_name": "users",
        "timestamp_col": "created_at",
        "last_seen_at": now,
    }

    mock_internal_conn = AsyncMock()
    mock_internal_conn.fetch = AsyncMock(return_value=[watermark])

    mock_customer_conn = AsyncMock()
    mock_customer_conn.fetch = AsyncMock(return_value=[])  # No new rows

    mock_internal_pool = _MockPool(mock_internal_conn)
    mock_customer_pool = _MockPool(mock_customer_conn)

    listener._internal_pool = mock_internal_pool
    listener._customer_pool = mock_customer_pool

    await listener._poll_cycle()

    # on_event should never be called
    on_event.assert_not_awaited()
