"""Event source interface — ABC that all event listeners implement."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EventSource(ABC):
    """Abstract base class for event sources (polling, CDC, WAL).

    All event sources emit the same TriggerEvent objects — the rest of
    the pipeline doesn't know which source is being used.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start listening for events."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening and clean up resources."""
        ...

    @property
    @abstractmethod
    def mode(self) -> str:
        """Return the event source mode: 'poll', 'cdc', or 'wal'."""
        ...
