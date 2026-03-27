"""Polling listener — reads new events from customer DB by polling watched tables."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import asyncpg

from growthclaw.models.trigger import TriggerEvent, TriggerRule
from growthclaw.triggers.event_source import EventSource

logger = logging.getLogger("growthclaw.triggers.polling_listener")


class PollingListener(EventSource):
    """Polls customer DB tables for new rows. Truly read-only — no triggers installed.

    Tracks high-water marks (last seen timestamp) per table in
    growthclaw.polling_watermarks. Emits the same TriggerEvent objects
    as CDCListener so the rest of the pipeline is unchanged.
    """

    def __init__(
        self,
        customer_dsn: str,
        internal_dsn: str,
        triggers: list[TriggerRule],
        concepts: dict,
        on_event: object,
        poll_interval: int = 30,
    ) -> None:
        self.customer_dsn = customer_dsn
        self.internal_dsn = internal_dsn
        self.triggers = triggers
        self.concepts = concepts
        self.on_event = on_event
        self.poll_interval = poll_interval
        self._running = False
        self._customer_pool: asyncpg.Pool | None = None  # type: ignore[type-arg]
        self._internal_pool: asyncpg.Pool | None = None  # type: ignore[type-arg]

    @property
    def mode(self) -> str:
        return "poll"

    async def start(self) -> None:
        """Start polling loop with automatic reconnection."""
        self._running = True
        self._customer_pool = await asyncpg.create_pool(dsn=self.customer_dsn, min_size=1, max_size=3)
        self._internal_pool = await asyncpg.create_pool(dsn=self.internal_dsn, min_size=1, max_size=3)

        # Initialize watermarks for all watched tables
        await self._init_watermarks()

        logger.info("Polling listener started (interval=%ds, tables=%d)", self.poll_interval, len(self.triggers))

        retries = 0
        while self._running:
            try:
                await self._poll_cycle()
                retries = 0
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                retries += 1
                wait = min(2**retries, 60)
                logger.warning("Polling error, retrying in %ds: %s", wait, e)
                await asyncio.sleep(wait)

    async def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        if self._customer_pool:
            await self._customer_pool.close()
        if self._internal_pool:
            await self._internal_pool.close()
        logger.info("Polling listener stopped")

    async def _init_watermarks(self) -> None:
        """Ensure watermark rows exist for all watched tables."""
        assert self._internal_pool
        async with self._internal_pool.acquire() as conn:
            for trigger in self.triggers:
                # Determine the timestamp column for this table
                ts_col = self._get_timestamp_col(trigger)
                if not ts_col:
                    logger.warning("No timestamp column for table %s, skipping", trigger.watch_table)
                    continue

                await conn.execute(
                    """
                    INSERT INTO growthclaw.polling_watermarks (table_name, trigger_id, timestamp_col)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (table_name) DO NOTHING
                    """,
                    trigger.watch_table,
                    trigger.id,
                    ts_col,
                )

    async def _poll_cycle(self) -> None:
        """Run one polling cycle: check each watched table for new rows."""
        assert self._customer_pool and self._internal_pool

        async with self._internal_pool.acquire() as iconn:
            watermarks = await iconn.fetch("SELECT * FROM growthclaw.polling_watermarks")

        for wm in watermarks:
            table = wm["table_name"]
            ts_col = wm["timestamp_col"]
            last_seen = wm["last_seen_at"]

            try:
                # Strip timezone from watermark — customer DB may use naive timestamps
                query_ts = last_seen.replace(tzinfo=None) if hasattr(last_seen, "replace") else last_seen

                async with self._customer_pool.acquire() as cconn:
                    # Safe identifier quoting
                    query = (
                        f'SELECT * FROM "{_safe_ident(table)}" '
                        f'WHERE "{_safe_ident(ts_col)}" > $1 '
                        f'ORDER BY "{_safe_ident(ts_col)}" LIMIT 100'
                    )
                    rows = await cconn.fetch(query, query_ts)

                if not rows:
                    continue

                logger.info("Poll: %d new rows in %s since %s", len(rows), table, last_seen)

                # Find the matching trigger for this table
                trigger = self._find_trigger(table)
                if not trigger:
                    continue

                # Emit events
                for row in rows:
                    user_id = self._extract_user_id(row, trigger)
                    if not user_id:
                        continue

                    event = TriggerEvent(
                        table=table,
                        op=trigger.watch_event,
                        ts=str(datetime.now(UTC)),
                        row_id=str(row.get("id", "")),
                        user_id=str(user_id),
                        trigger_id=str(trigger.id),
                    )
                    asyncio.create_task(self.on_event(event))

                # Update watermark to the latest timestamp seen
                latest_ts = rows[-1][ts_col]
                async with self._internal_pool.acquire() as iconn:
                    await iconn.execute(
                        """
                        UPDATE growthclaw.polling_watermarks
                        SET last_seen_at = $1, updated_at = NOW()
                        WHERE table_name = $2
                        """,
                        latest_ts,
                        table,
                    )

            except Exception as e:
                logger.warning("Poll failed for table %s: %s", table, e)

    def _get_timestamp_col(self, trigger: TriggerRule) -> str | None:
        """Determine the timestamp column for a watched table."""
        # Use customer_created_at_column for the customer table
        if trigger.watch_table == self.concepts.get("customer_table"):
            return self.concepts.get("customer_created_at_column", "created_at")
        # Default to created_at
        return "created_at"

    def _find_trigger(self, table: str) -> TriggerRule | None:
        """Find the trigger rule that watches this table."""
        for t in self.triggers:
            if t.watch_table == table:
                return t
        return None

    def _extract_user_id(self, row: asyncpg.Record, trigger: TriggerRule) -> str | None:  # type: ignore[type-arg]
        """Extract user_id from a row based on the trigger config."""
        if trigger.watch_table == self.concepts.get("customer_table"):
            pk = self.concepts.get("customer_id_column", "id")
            return str(row.get(pk, ""))

        # For other tables, use user_id_source or common FK names
        if trigger.user_id_source:
            col = trigger.user_id_source.replace("NEW.", "").replace("new.", "")
            return str(row.get(col, ""))

        # Try common FK column names
        for col in ["user_id", "customer_id", "client_id", "account_id"]:
            if col in row:
                return str(row[col])

        return None


def _safe_ident(name: str) -> str:
    """Sanitize a SQL identifier to prevent injection.

    Removes any characters that aren't alphanumeric or underscore.
    """
    return "".join(c for c in name if c.isalnum() or c == "_")
