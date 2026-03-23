"""Memory manager — store, recall, forget, and consolidate agent memories using LanceDB."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from growthclaw.memory.embedder import EMBEDDING_DIM, embed_text
from growthclaw.memory.schemas import MemoryEntry

logger = logging.getLogger("growthclaw.memory.manager")

DEFAULT_MEMORY_PATH = "~/.growthclaw/memory"
CONFIDENCE_DECAY_RATE = 0.02  # Per day


class MemoryManager:
    """LanceDB-based semantic memory for GrowthClaw."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_MEMORY_PATH).expanduser()
        self.db = None
        self.table = None
        self._initialized = False

    async def initialize(self) -> None:
        """Connect to LanceDB and ensure the memories table exists."""
        if self._initialized:
            return

        import lancedb

        self.db_path.mkdir(parents=True, exist_ok=True)
        lance_path = str(self.db_path / "lancedb")

        self.db = await asyncio.to_thread(lancedb.connect, lance_path)

        # Check if table exists
        table_names = await asyncio.to_thread(self.db.table_names)
        if "memories" in table_names:
            self.table = await asyncio.to_thread(self.db.open_table, "memories")
        else:
            # Create with a seed entry
            seed = {
                "id": str(uuid4()),
                "text": "GrowthClaw memory system initialized",
                "vector": [0.0] * EMBEDDING_DIM,
                "importance": 0.1,
                "category": "insight",
                "trigger_id": "",
                "cycle_id": "",
                "tags": "[]",
                "confidence": 0.1,
                "created_at": datetime.now().isoformat(),
            }
            self.table = await asyncio.to_thread(self.db.create_table, "memories", [seed])
            logger.info("Created memories table at %s", lance_path)

        self._initialized = True
        logger.info("Memory system initialized (%s)", lance_path)

    async def store(
        self,
        text: str,
        category: str = "insight",
        importance: float = 0.7,
        trigger_id: UUID | None = None,
        cycle_id: UUID | None = None,
        tags: list[str] | None = None,
    ) -> UUID:
        """Store a new memory entry with embedding."""
        await self.initialize()

        vector = await embed_text(text)
        entry_id = uuid4()

        record = {
            "id": str(entry_id),
            "text": text,
            "vector": vector,
            "importance": importance,
            "category": category,
            "trigger_id": str(trigger_id) if trigger_id else "",
            "cycle_id": str(cycle_id) if cycle_id else "",
            "tags": str(tags or []),
            "confidence": importance,
            "created_at": datetime.now().isoformat(),
        }

        await asyncio.to_thread(self.table.add, [record])
        logger.info("Stored memory: category=%s, importance=%.2f, text='%s...'", category, importance, text[:60])
        return entry_id

    async def recall(
        self,
        query: str,
        category: str | None = None,
        trigger_id: UUID | None = None,
        limit: int = 5,
    ) -> list[MemoryEntry]:
        """Semantic search over memories. Returns most relevant entries."""
        await self.initialize()

        query_vector = await embed_text(query)

        # LanceDB vector search
        search = self.table.search(query_vector).limit(limit * 3)  # Over-fetch for filtering
        raw_results = await asyncio.to_thread(search.to_list)

        # Filter and convert
        entries = []
        for r in raw_results:
            if category and r.get("category") != category:
                continue
            if trigger_id and r.get("trigger_id") != str(trigger_id):
                continue

            entry = MemoryEntry(
                id=UUID(r["id"]) if r.get("id") else uuid4(),
                text=r.get("text", ""),
                vector=[],  # Don't return vectors in results
                importance=r.get("importance", 0.5),
                category=r.get("category", "insight"),
                trigger_id=UUID(r["trigger_id"]) if r.get("trigger_id") else None,
                cycle_id=UUID(r["cycle_id"]) if r.get("cycle_id") else None,
                tags=eval(r.get("tags", "[]")) if isinstance(r.get("tags"), str) else r.get("tags", []),  # noqa: S307
                confidence=r.get("confidence", 0.5),
                created_at=datetime.fromisoformat(r["created_at"]) if r.get("created_at") else datetime.now(),
            )
            entries.append(entry)

            if len(entries) >= limit:
                break

        logger.info("Memory recall: query='%s...', found %d results", query[:40], len(entries))
        return entries

    async def forget(self, memory_id: UUID) -> bool:
        """Delete a memory entry by ID."""
        await self.initialize()
        try:
            await asyncio.to_thread(self.table.delete, f"id = '{memory_id}'")
            logger.info("Forgot memory: %s", memory_id)
            return True
        except Exception as e:
            logger.warning("Failed to forget memory %s: %s", memory_id, e)
            return False


async def consolidate(db_path: str | None = None) -> int:
    """Daily memory maintenance: decay confidence scores, archive old low-confidence memories.

    Returns count of memories affected.
    """
    mgr = MemoryManager(db_path)
    await mgr.initialize()

    # Get all memories
    all_records = await asyncio.to_thread(mgr.table.to_pandas)
    affected = 0

    for _, row in all_records.iterrows():
        created = datetime.fromisoformat(row["created_at"]) if isinstance(row["created_at"], str) else row["created_at"]
        days_old = (datetime.now() - created).days
        current_confidence = row.get("confidence", 0.5)

        # Decay confidence based on age
        new_confidence = max(0.05, current_confidence - (days_old * CONFIDENCE_DECAY_RATE))

        # Delete very old, low-confidence memories
        if new_confidence < 0.1 and days_old > 90:
            await asyncio.to_thread(mgr.table.delete, f"id = '{row['id']}'")
            affected += 1
            logger.info("Archived old memory: %s (confidence=%.2f, age=%dd)", row["id"], new_confidence, days_old)

    logger.info("Memory consolidation complete: %d memories affected", affected)
    return affected
