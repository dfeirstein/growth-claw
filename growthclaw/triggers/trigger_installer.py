"""Trigger installer — generates and installs PostgreSQL NOTIFY triggers on customer tables."""

from __future__ import annotations

import logging

import asyncpg

from growthclaw.models.schema_map import BusinessConcepts
from growthclaw.models.trigger import TriggerRule

logger = logging.getLogger("growthclaw.triggers.installer")


async def install_trigger(
    customer_conn: asyncpg.Connection,  # type: ignore[type-arg]
    internal_conn: asyncpg.Connection,  # type: ignore[type-arg]
    trigger: TriggerRule,
    concepts: BusinessConcepts,
) -> str:
    """Generate and install a PG trigger function + trigger for CDC notifications.

    Functions are created in the growthclaw schema.
    Triggers are installed on the customer's tables (AFTER INSERT/UPDATE).
    """
    function_name = f"growthclaw_notify_{trigger.watch_table}"
    trigger_name = f"gc_{trigger.watch_table}_{trigger.watch_event.lower()}"

    # Determine user_id extraction based on table
    if trigger.watch_table == concepts.customer_table:
        user_id_expr = f'NEW."{concepts.customer_id_column}"'
    elif trigger.user_id_source:
        # user_id_source is like "NEW.user_id" — extract the column name
        col = trigger.user_id_source.replace("NEW.", "").replace("new.", "")
        user_id_expr = f'NEW."{col}"'
    else:
        # Fallback: try the activation FK column if watching activation table
        if trigger.watch_table == concepts.activation_table and concepts.activation_fk_column:
            user_id_expr = f'NEW."{concepts.activation_fk_column}"'
        else:
            user_id_expr = "NEW.id"

    # Determine row_id (usually the PK)
    row_id_expr = "NEW.id"

    # Create trigger function in growthclaw schema
    function_sql = f"""
    CREATE OR REPLACE FUNCTION growthclaw.{function_name}()
    RETURNS TRIGGER AS $$
    BEGIN
      PERFORM pg_notify('growthclaw_events', json_build_object(
        'table', TG_TABLE_NAME,
        'op', TG_OP,
        'ts', NOW()::text,
        'row_id', {row_id_expr}::text,
        'user_id', {user_id_expr}::text,
        'trigger_id', '{trigger.id}'
      )::text);
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """

    # Build trigger SQL with optional WHEN condition
    when_clause = ""
    if trigger.watch_condition:
        when_clause = f"\n      WHEN ({trigger.watch_condition})"

    trigger_sql = f"""
    DROP TRIGGER IF EXISTS {trigger_name} ON public."{trigger.watch_table}";
    CREATE TRIGGER {trigger_name}
      AFTER {trigger.watch_event} ON public."{trigger.watch_table}"
      FOR EACH ROW{when_clause}
      EXECUTE FUNCTION growthclaw.{function_name}();
    """

    # Execute on customer DB
    await customer_conn.execute(function_sql)
    await customer_conn.execute(trigger_sql)

    # Track installation in internal DB
    await internal_conn.execute(
        """
        INSERT INTO growthclaw.installed_triggers (table_name, trigger_name, function_name)
        VALUES ($1, $2, $3)
        ON CONFLICT (table_name, trigger_name) DO UPDATE SET
            function_name = EXCLUDED.function_name,
            installed_at = NOW()
        """,
        trigger.watch_table,
        trigger_name,
        function_name,
    )

    logger.info("Installed trigger %s on %s (function: %s)", trigger_name, trigger.watch_table, function_name)
    return trigger_name


async def uninstall_all(
    customer_conn: asyncpg.Connection,  # type: ignore[type-arg]
    internal_conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> int:
    """Remove all installed triggers and functions. Returns count of removed triggers."""
    rows = await internal_conn.fetch(
        "SELECT table_name, trigger_name, function_name FROM growthclaw.installed_triggers"
    )

    for row in rows:
        try:
            await customer_conn.execute(f'DROP TRIGGER IF EXISTS {row["trigger_name"]} ON public."{row["table_name"]}"')
            await customer_conn.execute(f"DROP FUNCTION IF EXISTS growthclaw.{row['function_name']}()")
            logger.info("Uninstalled trigger %s from %s", row["trigger_name"], row["table_name"])
        except Exception as e:
            logger.warning("Failed to uninstall trigger %s: %s", row["trigger_name"], e)

    await internal_conn.execute("DELETE FROM growthclaw.installed_triggers")
    logger.info("Uninstalled %d triggers", len(rows))
    return len(rows)
