"""Memory entry models for GrowthClaw's semantic memory system."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """A single memory entry stored in the vector database."""

    id: UUID = Field(default_factory=uuid4)
    text: str
    vector: list[float] = Field(default_factory=list)
    importance: float = 0.7
    category: str = "insight"  # pattern | guardrail | hypothesis | outcome | preference | insight
    trigger_id: UUID | None = None
    cycle_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.7  # decays over time
    created_at: datetime = Field(default_factory=datetime.now)
