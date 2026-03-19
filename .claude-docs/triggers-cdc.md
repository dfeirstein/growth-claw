# PostgreSQL Triggers & CDC Patterns for GrowthClaw

## How CDC Works in GrowthClaw

1. GrowthClaw creates trigger FUNCTIONS in the `growthclaw` schema
2. GrowthClaw creates TRIGGERS on customer tables that call these functions
3. Triggers fire `pg_notify('growthclaw_events', payload)` on INSERT/UPDATE
4. A dedicated asyncpg connection LISTENs for these notifications
5. Events are parsed and processed through the trigger pipeline

## Trigger Function Pattern

```sql
CREATE OR REPLACE FUNCTION growthclaw.growthclaw_notify_users()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify('growthclaw_events', json_build_object(
    'table', TG_TABLE_NAME,
    'op', TG_OP,
    'ts', NOW(),
    'row_id', NEW.id::text,
    'user_id', NEW.id::text,
    'trigger_id', 'uuid-here'
  )::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

## Trigger Installation

```sql
DROP TRIGGER IF EXISTS gc_users_change ON public.users;
CREATE TRIGGER gc_users_change
  AFTER INSERT ON public.users
  FOR EACH ROW EXECUTE FUNCTION growthclaw.growthclaw_notify_users();
```

Key points:
- Functions live in `growthclaw` schema (we own this)
- Triggers are on `public.*` tables (customer's tables)
- Always DROP IF EXISTS before CREATE to be idempotent
- AFTER triggers don't affect the original transaction
- FOR EACH ROW fires once per row, not per statement

## user_id Extraction

The trigger must extract the correct user_id depending on which table is being watched:

- **Customer table** (e.g., `users`): `user_id = NEW.id` (the PK)
- **Other tables** (e.g., `cards`, `bookings`): `user_id = NEW.{fk_column}` (the FK to customer)

This is determined at trigger generation time based on the discovered schema.

## pg_notify Constraints

- **Payload limit**: ~8000 bytes per notification
- Keep payloads minimal: table, operation, user_id, trigger_id, timestamp
- Do NOT include full row data in the payload — query it later if needed
- Notifications are transactional — they fire only when the triggering transaction commits
- If the LISTEN connection drops, notifications during downtime are LOST

## LISTEN/NOTIFY Consumer Pattern

```python
import asyncpg
import asyncio
import json

async def start_listener(dsn: str, on_event):
    conn = await asyncpg.connect(dsn=dsn)

    def handle_notification(conn, pid, channel, payload):
        event = json.loads(payload)
        asyncio.create_task(on_event(event))

    await conn.add_listener("growthclaw_events", handle_notification)

    # Keep connection alive
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        await conn.remove_listener("growthclaw_events", handle_notification)
        await conn.close()
```

## Reconnection Strategy

Since LISTEN connections can drop:

```python
async def listen_with_reconnect(dsn, on_event, max_retries=None):
    retries = 0
    while max_retries is None or retries < max_retries:
        try:
            await start_listener(dsn, on_event)
        except (asyncpg.ConnectionDoesNotExistError, OSError) as e:
            retries += 1
            wait = min(2 ** retries, 60)  # exponential backoff, max 60s
            logger.warning("listener_disconnected", retry_in=wait, error=str(e))
            await asyncio.sleep(wait)
```

## Trigger Cleanup

When stopping GrowthClaw, remove installed triggers:

```python
async def uninstall_all(conn, internal_conn):
    rows = await internal_conn.fetch(
        "SELECT table_name, trigger_name, function_name FROM growthclaw.installed_triggers"
    )
    for row in rows:
        await conn.execute(f"DROP TRIGGER IF EXISTS {row['trigger_name']} ON public.{row['table_name']}")
        await conn.execute(f"DROP FUNCTION IF EXISTS growthclaw.{row['function_name']}()")
    await internal_conn.execute("DELETE FROM growthclaw.installed_triggers")
```

## Conditional Triggers

Some triggers have watch conditions:

```sql
CREATE TRIGGER gc_bookings_completed
  AFTER UPDATE ON public.bookings
  FOR EACH ROW
  WHEN (NEW.status = 'completed' AND OLD.status != 'completed')
  EXECUTE FUNCTION growthclaw.growthclaw_notify_bookings();
```

The WHEN clause filters at the PG level, reducing unnecessary notifications.
