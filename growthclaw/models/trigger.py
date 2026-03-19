"""Pydantic models for triggers and CDC events."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ProfileQuery(BaseModel):
    name: str
    sql: str
    description: str = ""


class TriggerRule(BaseModel):
    """A trigger rule proposed by the LLM and potentially approved by a human."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    priority: int = 1
    watch_table: str
    watch_event: Literal["INSERT", "UPDATE", "DELETE"] = "INSERT"
    watch_condition: str | None = None
    delay_minutes: int = 30
    check_sql: str
    profile_queries: list[ProfileQuery] = Field(default_factory=list)
    message_context: str = ""
    channel: Literal["sms", "email"] = "sms"
    user_id_source: str = ""  # e.g., "NEW.id" or "NEW.user_id"
    max_fires: int = 3
    cooldown_hours: int = 24
    status: Literal["proposed", "approved", "active", "paused"] = "proposed"
    expected_audience_per_week: int = 0
    expected_conversion_lift: Literal["low", "medium", "high"] = "medium"
    reasoning: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


class TriggerEvent(BaseModel):
    """A CDC event received via pg_notify."""

    table: str
    op: str  # INSERT, UPDATE, DELETE
    ts: str
    row_id: str
    user_id: str
    trigger_id: str


class TriggerState(BaseModel):
    """Cooldown tracking state for a user-trigger pair."""

    user_id: str
    trigger_id: UUID
    fire_count: int = 0
    last_fired_at: datetime | None = None


class InstalledTrigger(BaseModel):
    """Record of a PG trigger installed on a customer table."""

    id: UUID = Field(default_factory=uuid4)
    table_name: str
    trigger_name: str
    function_name: str
    installed_at: datetime = Field(default_factory=datetime.now)
