"""CDC listener — consumes PostgreSQL LISTEN/NOTIFY events and schedules delayed processing."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import asyncpg

from growthclaw.models.trigger import TriggerEvent
from growthclaw.triggers.event_source import EventSource

logger = logging.getLogger("growthclaw.triggers.cdc_listener")

CHANNEL = "growthclaw_events"

# Type for the async callback that processes events
EventCallback = Callable[[TriggerEvent], Coroutine[Any, Any, None]]


class CDCListener(EventSource):
    """Listens for PostgreSQL NOTIFY events on the growthclaw_events channel."""

    def __init__(self, dsn: str, on_event: EventCallback) -> None:
        self.dsn = dsn
        self.on_event = on_event
        self._conn: asyncpg.Connection | None = None  # type: ignore[type-arg]
        self._running = False

    @property
    def mode(self) -> str:
        return "cdc"

    async def start(self) -> None:
        """Start listening for CDC events with automatic reconnection."""
        self._running = True
        retries = 0

        while self._running:
            try:
                await self._listen()
            except (asyncpg.ConnectionDoesNotExistError, OSError, ConnectionError) as e:
                if not self._running:
                    break
                retries += 1
                wait = min(2**retries, 60)
                logger.warning("Listener disconnected, reconnecting in %ds: %s", wait, e)
                await asyncio.sleep(wait)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.error("Unexpected listener error: %s", e)
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the listener and close the connection."""
        self._running = False
        if self._conn:
            try:
                await self._conn.remove_listener(CHANNEL, self._notification_handler)
                await self._conn.close()
            except Exception:
                pass
            self._conn = None
        logger.info("CDC listener stopped")

    async def _listen(self) -> None:
        """Connect and listen for notifications."""
        self._conn = await asyncpg.connect(dsn=self.dsn)
        await self._conn.add_listener(CHANNEL, self._notification_handler)
        logger.info("CDC listener connected, listening on channel '%s'", CHANNEL)

        # Keep connection alive
        while self._running:
            await asyncio.sleep(1)

    def _notification_handler(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """Handle incoming NOTIFY events."""
        try:
            data = json.loads(payload)
            event = TriggerEvent(
                table=data["table"],
                op=data["op"],
                ts=data["ts"],
                row_id=data["row_id"],
                user_id=data["user_id"],
                trigger_id=data["trigger_id"],
            )
            logger.info(
                "CDC event: %s %s on %s (user_id=%s, trigger=%s)",
                event.op,
                event.row_id,
                event.table,
                event.user_id,
                event.trigger_id,
            )
            # Schedule async processing
            asyncio.create_task(self.on_event(event))
        except Exception as e:
            logger.error("Failed to process CDC notification: %s (payload: %s)", e, payload[:200])
