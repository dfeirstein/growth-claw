"""WAL logical replication listener — consumes PostgreSQL WAL stream for real-time CDC.

Requires:
- wal_level=logical on the customer database (most managed Postgres: RDS, Supabase, Neon)
- Customer must create a publication: CREATE PUBLICATION growthclaw_pub FOR TABLE <tables>;
- Uses asyncpg logical replication protocol (NOT psycopg2)
- Falls back to polling if WAL is unavailable

This is a CUSTOMER-SIDE prerequisite, not something GrowthClaw installs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import asyncpg

from growthclaw.models.trigger import TriggerEvent, TriggerRule
from growthclaw.triggers.event_source import EventSource

logger = logging.getLogger("growthclaw.triggers.wal_listener")

REPLICATION_SLOT = "growthclaw_slot"
PUBLICATION = "growthclaw_pub"


class WALListener(EventSource):
    """Listens for changes via PostgreSQL logical replication (WAL streaming).

    Recommended tier: zero DB load, millisecond latency, read-only.
    Requires customer to enable wal_level=logical and create a publication.
    """

    def __init__(
        self,
        customer_dsn: str,
        triggers: list[TriggerRule],
        concepts: dict,
        on_event: object,
    ) -> None:
        self.customer_dsn = customer_dsn
        self.triggers = triggers
        self.concepts = concepts
        self.on_event = on_event
        self._running = False
        self._conn: asyncpg.Connection | None = None  # type: ignore[type-arg]

    @property
    def mode(self) -> str:
        return "wal"

    async def start(self) -> None:
        """Start consuming the WAL stream."""
        self._running = True
        retries = 0

        while self._running:
            try:
                await self._stream()
            except asyncpg.InvalidCatalogNameError:
                logger.error(
                    "WAL replication slot '%s' does not exist. "
                    "Customer must create it: SELECT pg_create_logical_replication_slot('%s', 'wal2json');",
                    REPLICATION_SLOT,
                    REPLICATION_SLOT,
                )
                logger.info("Falling back — WAL not available. Use EVENT_MODE=poll instead.")
                break
            except (asyncpg.ConnectionDoesNotExistError, OSError, ConnectionError) as e:
                if not self._running:
                    break
                retries += 1
                wait = min(2**retries, 60)
                logger.warning("WAL listener disconnected, reconnecting in %ds: %s", wait, e)
                await asyncio.sleep(wait)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.error("WAL listener error: %s", e)
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the WAL stream consumer."""
        self._running = False
        if self._conn:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None
        logger.info("WAL listener stopped")

    async def _stream(self) -> None:
        """Connect and consume the WAL stream using logical replication."""
        # Connect with replication=database for logical replication
        self._conn = await asyncpg.connect(
            dsn=self.customer_dsn,
            server_settings={"replication": "database"},
        )

        logger.info("WAL listener connected, streaming from slot '%s'", REPLICATION_SLOT)

        # Consume changes via the replication slot
        # Using SQL-level logical replication consumption (works with any asyncpg)
        while self._running:
            try:
                rows = await self._conn.fetch(
                    f"SELECT * FROM pg_logical_slot_get_changes('{REPLICATION_SLOT}', NULL, 100, "
                    "'format-version', '2', 'include-pk', '1')"
                )

                for row in rows:
                    await self._process_wal_change(row)

                if not rows:
                    await asyncio.sleep(0.1)  # Brief pause when no changes

            except Exception as e:
                if not self._running:
                    break
                logger.warning("WAL stream error: %s", e)
                raise

    async def _process_wal_change(self, row: asyncpg.Record) -> None:  # type: ignore[type-arg]
        """Process a single WAL change record."""
        try:
            data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        except (json.JSONDecodeError, KeyError):
            return

        # wal2json v2 format
        changes = data.get("change", [data]) if isinstance(data, dict) else [data]

        for change in changes:
            table = change.get("table", "")
            kind = change.get("kind", "")  # insert, update, delete

            # Map WAL kind to our event type
            op_map = {"insert": "INSERT", "update": "UPDATE", "delete": "DELETE"}
            op = op_map.get(kind, "")
            if not op:
                continue

            # Find matching trigger
            trigger = self._find_trigger(table, op)
            if not trigger:
                continue

            # Extract column values
            columns = change.get("columnvalues", change.get("columnnames", []))
            col_names = change.get("columnnames", [])
            row_data = dict(zip(col_names, columns)) if col_names and columns else {}

            # Extract user_id
            user_id = self._extract_user_id(row_data, trigger)
            if not user_id:
                continue

            event = TriggerEvent(
                table=table,
                op=op,
                ts=str(datetime.now(UTC)),
                row_id=str(row_data.get("id", "")),
                user_id=str(user_id),
                trigger_id=str(trigger.id),
            )
            asyncio.create_task(self.on_event(event))

    def _find_trigger(self, table: str, op: str) -> TriggerRule | None:
        """Find the trigger rule matching this table and operation."""
        for t in self.triggers:
            if t.watch_table == table and t.watch_event == op:
                return t
        return None

    def _extract_user_id(self, row_data: dict, trigger: TriggerRule) -> str | None:
        """Extract user_id from WAL change data."""
        if trigger.watch_table == self.concepts.get("customer_table"):
            pk = self.concepts.get("customer_id_column", "id")
            return str(row_data.get(pk, ""))

        if trigger.user_id_source:
            col = trigger.user_id_source.replace("NEW.", "").replace("new.", "")
            return str(row_data.get(col, ""))

        for col in ["user_id", "customer_id", "client_id", "account_id"]:
            if col in row_data:
                return str(row_data[col])

        return None
