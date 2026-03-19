"""Tests for trigger_evaluator — verifies cooldown, consent, quiet hours, max fires, and activation checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from growthclaw.config import Settings
from growthclaw.models.schema_map import BusinessConcepts
from growthclaw.models.trigger import TriggerEvent, TriggerRule
from growthclaw.triggers.trigger_evaluator import _in_quiet_hours, evaluate, record_fire

CONCEPTS = BusinessConcepts(
    customer_table="users",
    customer_id_column="id",
    sms_consent_column="accepted_sms_at",
    sms_consent_check="accepted_sms_at IS NOT NULL",
)

TRIGGER = TriggerRule(
    name="test_trigger",
    description="Test trigger",
    watch_table="users",
    watch_event="INSERT",
    check_sql="SELECT NOT EXISTS(SELECT 1 FROM cards WHERE user_id = $1)",
    max_fires=3,
    cooldown_hours=24,
    channel="sms",
)

EVENT = TriggerEvent(
    table="users",
    op="INSERT",
    ts="2026-01-15T10:00:00Z",
    row_id="123",
    user_id="123",
    trigger_id=str(TRIGGER.id),
)


def _settings(**overrides) -> Settings:
    defaults = {
        "customer_database_url": "postgresql://localhost/test",
        "growthclaw_database_url": "postgresql://localhost/test",
        "anthropic_api_key": "test-key",
        "quiet_hours_start": 21,
        "quiet_hours_end": 8,
        "dry_run": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _mock_conns(state_row=None, consent_val=True, check_val=True):
    """Create mock customer and internal connections."""
    customer_conn = AsyncMock()
    internal_conn = AsyncMock()

    # Internal: trigger state lookup
    internal_conn.fetchrow = AsyncMock(return_value=state_row)

    # Customer: SMS consent check and activation check
    customer_conn.fetchval = AsyncMock(
        side_effect=lambda q, *a: consent_val if "accepted_sms" in q.lower() else check_val
    )

    return customer_conn, internal_conn


# ---------------------------------------------------------------------------
# Quiet hours tests
# ---------------------------------------------------------------------------


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=True)
async def test_block_during_quiet_hours(mock_qh):
    """Triggers are blocked during quiet hours."""
    cconn, iconn = _mock_conns()
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is False


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_allow_outside_quiet_hours(mock_qh):
    """Triggers are allowed outside quiet hours."""
    cconn, iconn = _mock_conns(state_row=None, consent_val=True, check_val=True)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is True


def test_quiet_hours_spanning_midnight():
    """Quiet hours 21:00-08:00 blocks at 23:00."""
    settings = _settings(quiet_hours_start=21, quiet_hours_end=8)
    with patch("growthclaw.triggers.trigger_evaluator.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 15, 23, 0, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert _in_quiet_hours(settings) is True


def test_quiet_hours_spanning_midnight_allows_noon():
    """Quiet hours 21:00-08:00 allows at 12:00."""
    settings = _settings(quiet_hours_start=21, quiet_hours_end=8)
    with patch("growthclaw.triggers.trigger_evaluator.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert _in_quiet_hours(settings) is False


def test_quiet_hours_same_day():
    """Quiet hours 02:00-06:00 blocks at 03:00."""
    settings = _settings(quiet_hours_start=2, quiet_hours_end=6)
    with patch("growthclaw.triggers.trigger_evaluator.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 15, 3, 0, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert _in_quiet_hours(settings) is True


def test_quiet_hours_same_day_allows_outside():
    """Quiet hours 02:00-06:00 allows at 10:00."""
    settings = _settings(quiet_hours_start=2, quiet_hours_end=6)
    with patch("growthclaw.triggers.trigger_evaluator.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert _in_quiet_hours(settings) is False


# ---------------------------------------------------------------------------
# Cooldown tests
# ---------------------------------------------------------------------------


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_block_during_cooldown(mock_qh):
    """Trigger is blocked if fired recently (within cooldown_hours)."""
    state = {"fire_count": 1, "last_fired_at": datetime.now(UTC) - timedelta(hours=2)}
    cconn, iconn = _mock_conns(state_row=state)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is False


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_allow_after_cooldown_expired(mock_qh):
    """Trigger is allowed after cooldown period has passed."""
    state = {"fire_count": 1, "last_fired_at": datetime.now(UTC) - timedelta(hours=25)}
    cconn, iconn = _mock_conns(state_row=state, consent_val=True, check_val=True)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is True


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_cooldown_with_naive_timestamp(mock_qh):
    """Handles naive (non-timezone-aware) last_fired_at timestamps."""
    state = {"fire_count": 1, "last_fired_at": datetime.now() - timedelta(hours=2)}
    cconn, iconn = _mock_conns(state_row=state)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is False


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_cooldown_boundary_exactly_at_limit(mock_qh):
    """At exactly the cooldown boundary, trigger should still be blocked."""
    # Just under 24 hours
    state = {"fire_count": 1, "last_fired_at": datetime.now(UTC) - timedelta(hours=23, minutes=59)}
    cconn, iconn = _mock_conns(state_row=state)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is False


# ---------------------------------------------------------------------------
# Max fires tests
# ---------------------------------------------------------------------------


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_block_when_max_fires_reached(mock_qh):
    """Trigger is blocked when max_fires (3) has been reached."""
    state = {"fire_count": 3, "last_fired_at": datetime.now(UTC) - timedelta(hours=48)}
    cconn, iconn = _mock_conns(state_row=state)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is False


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_allow_when_fires_below_max(mock_qh):
    """Trigger is allowed when fire count is below max."""
    state = {"fire_count": 2, "last_fired_at": datetime.now(UTC) - timedelta(hours=48)}
    cconn, iconn = _mock_conns(state_row=state, consent_val=True, check_val=True)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is True


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_block_when_fires_exceed_max(mock_qh):
    """Trigger is blocked even when fire count exceeds max (safety check)."""
    state = {"fire_count": 10, "last_fired_at": datetime.now(UTC) - timedelta(hours=48)}
    cconn, iconn = _mock_conns(state_row=state)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is False


# ---------------------------------------------------------------------------
# SMS consent tests
# ---------------------------------------------------------------------------


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_block_when_no_sms_consent(mock_qh):
    """SMS trigger is blocked when user has not opted in."""
    cconn, iconn = _mock_conns(state_row=None, consent_val=False, check_val=True)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is False


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_skip_consent_check_for_email(mock_qh):
    """Email triggers do not require SMS consent."""
    email_trigger = TriggerRule(
        name="email_trigger",
        description="Test email trigger",
        watch_table="users",
        watch_event="INSERT",
        check_sql="SELECT NOT EXISTS(SELECT 1 FROM cards WHERE user_id = $1)",
        max_fires=3,
        cooldown_hours=24,
        channel="email",
    )
    email_event = TriggerEvent(
        table="users",
        op="INSERT",
        ts="2026-01-15T10:00:00Z",
        row_id="123",
        user_id="123",
        trigger_id=str(email_trigger.id),
    )

    cconn, iconn = _mock_conns(state_row=None, consent_val=False, check_val=True)
    result = await evaluate(email_event, email_trigger, cconn, iconn, CONCEPTS, _settings())
    assert result is True


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_skip_consent_when_no_consent_check_configured(mock_qh):
    """SMS consent is not checked when sms_consent_check is not set."""
    concepts_no_consent = BusinessConcepts(
        customer_table="users",
        customer_id_column="id",
    )
    cconn, iconn = _mock_conns(state_row=None, consent_val=False, check_val=True)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, concepts_no_consent, _settings())
    assert result is True


# ---------------------------------------------------------------------------
# Already activated tests
# ---------------------------------------------------------------------------


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_block_when_user_already_activated(mock_qh):
    """Trigger is blocked when user has already completed the watched action."""
    cconn, iconn = _mock_conns(state_row=None, consent_val=True, check_val=False)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is False


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_block_when_check_sql_raises(mock_qh):
    """Trigger is blocked when the check SQL raises an exception (fail-safe)."""
    cconn = AsyncMock()
    iconn = AsyncMock()
    iconn.fetchrow = AsyncMock(return_value=None)

    call_count = 0

    async def mock_fetchval(q, *a):
        nonlocal call_count
        call_count += 1
        if "accepted_sms" in q.lower():
            return True
        raise RuntimeError("SQL error")

    cconn.fetchval = AsyncMock(side_effect=mock_fetchval)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is False


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_no_check_sql_still_passes(mock_qh):
    """Trigger without check_sql passes the activation check."""
    trigger_no_check = TriggerRule(
        name="no_check_trigger",
        description="Trigger with no check_sql",
        watch_table="users",
        watch_event="INSERT",
        check_sql="",
        max_fires=3,
        cooldown_hours=24,
        channel="sms",
    )
    event = TriggerEvent(
        table="users",
        op="INSERT",
        ts="2026-01-15T10:00:00Z",
        row_id="123",
        user_id="123",
        trigger_id=str(trigger_no_check.id),
    )
    cconn, iconn = _mock_conns(state_row=None, consent_val=True, check_val=True)
    result = await evaluate(event, trigger_no_check, cconn, iconn, CONCEPTS, _settings())
    assert result is True


# ---------------------------------------------------------------------------
# All checks pass (happy path)
# ---------------------------------------------------------------------------


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_approve_when_all_checks_pass(mock_qh):
    """Trigger fires when all conditions are met."""
    cconn, iconn = _mock_conns(state_row=None, consent_val=True, check_val=True)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is True


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_approve_with_existing_state_under_limits(mock_qh):
    """Trigger fires when state exists but all limits are under threshold."""
    state = {"fire_count": 1, "last_fired_at": datetime.now(UTC) - timedelta(hours=48)}
    cconn, iconn = _mock_conns(state_row=state, consent_val=True, check_val=True)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is True


# ---------------------------------------------------------------------------
# Numeric user_id handling
# ---------------------------------------------------------------------------


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_numeric_user_id_converted_for_consent_check(mock_qh):
    """Numeric user_ids are converted to int for parameterized queries."""
    cconn, iconn = _mock_conns(state_row=None, consent_val=True, check_val=True)
    result = await evaluate(EVENT, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is True
    # The user_id "123" should be converted to int(123)
    consent_call = cconn.fetchval.call_args_list[0]
    assert consent_call[0][1] == 123


@patch("growthclaw.triggers.trigger_evaluator._in_quiet_hours", return_value=False)
async def test_uuid_user_id_stays_as_string(mock_qh):
    """UUID user_ids are kept as strings."""
    uuid_event = TriggerEvent(
        table="users",
        op="INSERT",
        ts="2026-01-15T10:00:00Z",
        row_id="abc-def",
        user_id="abc-def",
        trigger_id=str(TRIGGER.id),
    )
    cconn, iconn = _mock_conns(state_row=None, consent_val=True, check_val=True)
    result = await evaluate(uuid_event, TRIGGER, cconn, iconn, CONCEPTS, _settings())
    assert result is True
    consent_call = cconn.fetchval.call_args_list[0]
    assert consent_call[0][1] == "abc-def"


# ---------------------------------------------------------------------------
# record_fire tests
# ---------------------------------------------------------------------------


async def test_record_fire():
    """record_fire inserts/updates trigger state."""
    iconn = AsyncMock()
    await record_fire(iconn, "123", TRIGGER)
    iconn.execute.assert_awaited_once()
    call_args = iconn.execute.call_args[0]
    assert "INSERT INTO growthclaw.trigger_state" in call_args[0]
    assert call_args[1] == "123"
    assert call_args[2] == TRIGGER.id
