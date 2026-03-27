"""Trigger evaluator — checks cooldowns, consent, quiet hours, and activation status before firing."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import asyncpg

from growthclaw.config import Settings
from growthclaw.models.schema_map import BusinessConcepts
from growthclaw.models.trigger import TriggerEvent, TriggerRule

logger = logging.getLogger("growthclaw.triggers.evaluator")

# Track which triggers have already logged check_sql errors (avoid spam)
_check_sql_errors_logged: set[str] = set()


async def evaluate(
    event: TriggerEvent,
    trigger: TriggerRule,
    customer_conn: asyncpg.Connection,  # type: ignore[type-arg]
    internal_conn: asyncpg.Connection,  # type: ignore[type-arg]
    concepts: BusinessConcepts,
    settings: Settings,
) -> bool:
    """Evaluate whether a trigger should fire for this event.

    Checks in order:
    1. Quiet hours
    2. Cooldown not exceeded
    3. Max fires not reached
    4. SMS consent exists (for SMS triggers)
    5. User still hasn't completed the activation step
    """
    user_id = event.user_id

    # 1. Quiet hours check
    if _in_quiet_hours(settings):
        logger.info("Blocked: quiet hours (user_id=%s, trigger=%s)", user_id, trigger.name)
        return False

    # 2 & 3. Cooldown and max fires check
    state = await internal_conn.fetchrow(
        "SELECT fire_count, last_fired_at FROM growthclaw.trigger_state WHERE user_id = $1 AND trigger_id = $2",
        user_id,
        trigger.id,
    )

    if state:
        # Max fires check
        if state["fire_count"] >= trigger.max_fires:
            logger.info(
                "Blocked: max fires reached (%d/%d, user_id=%s, trigger=%s)",
                state["fire_count"],
                trigger.max_fires,
                user_id,
                trigger.name,
            )
            return False

        # Cooldown check
        if state["last_fired_at"]:
            now = datetime.now(UTC)
            last_fired = state["last_fired_at"]
            if last_fired.tzinfo is None:
                last_fired = last_fired.replace(tzinfo=UTC)
            hours_since = (now - last_fired).total_seconds() / 3600
            if hours_since < trigger.cooldown_hours:
                logger.info(
                    "Blocked: cooldown (%d/%dh, user_id=%s, trigger=%s)",
                    int(hours_since),
                    trigger.cooldown_hours,
                    user_id,
                    trigger.name,
                )
                return False

    # 4. SMS consent check
    if trigger.channel == "sms" and concepts.sms_consent_check:
        has_consent = await customer_conn.fetchval(
            f'SELECT {concepts.sms_consent_check} FROM "{concepts.customer_table}" '  # noqa: S608
            f'WHERE "{concepts.customer_id_column}" = $1',
            user_id if not user_id.isdigit() else int(user_id),
        )
        if not has_consent:
            logger.info("Blocked: no SMS consent (user_id=%s, trigger=%s)", user_id, trigger.name)
            return False

    # 5. Check if user still hasn't activated (the condition the trigger is watching for)
    if trigger.check_sql:
        try:
            sql = trigger.check_sql.strip()
            # LLM sometimes returns SQL fragments — wrap in SELECT if needed
            if not sql.upper().startswith("SELECT"):
                sql = f"SELECT ({sql})"
            still_needs_action = await customer_conn.fetchval(
                sql,
                user_id if not user_id.isdigit() else int(user_id),
            )
            if not still_needs_action:
                logger.info("Blocked: user already activated (user_id=%s, trigger=%s)", user_id, trigger.name)
                return False
        except Exception as e:
            # Log once per trigger, not per event
            if trigger.name not in _check_sql_errors_logged:
                _check_sql_errors_logged.add(trigger.name)
                logger.warning("check_sql failed for trigger %s (will not repeat): %s", trigger.name, e)
            return False

    logger.info("Trigger approved: user_id=%s, trigger=%s", user_id, trigger.name)
    return True


async def record_fire(
    internal_conn: asyncpg.Connection,  # type: ignore[type-arg]
    user_id: str,
    trigger: TriggerRule,
) -> None:
    """Record that a trigger has fired for a user."""
    await internal_conn.execute(
        """
        INSERT INTO growthclaw.trigger_state (user_id, trigger_id, fire_count, last_fired_at)
        VALUES ($1, $2, 1, NOW())
        ON CONFLICT (user_id, trigger_id) DO UPDATE SET
            fire_count = growthclaw.trigger_state.fire_count + 1,
            last_fired_at = NOW()
        """,
        user_id,
        trigger.id,
    )


def _in_quiet_hours(settings: Settings) -> bool:
    """Check if the current time is within quiet hours."""
    now = datetime.now(UTC)
    hour = now.hour

    start = settings.quiet_hours_start
    end = settings.quiet_hours_end

    if start > end:
        # Quiet hours span midnight (e.g., 21:00 - 08:00)
        return hour >= start or hour < end
    else:
        # Quiet hours within same day (e.g., 02:00 - 06:00)
        return start <= hour < end
