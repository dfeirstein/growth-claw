"""Growth DAG data models — hierarchical memory from raw events to strategy narratives."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SendOutcome(BaseModel):
    """Layer 0: Raw send event — every send and every outcome, never deleted."""

    id: UUID = Field(default_factory=uuid4)
    trigger_id: UUID
    trigger_name: str
    user_id: str
    channel: str  # sms | email
    message_body: str
    tone: str | None = None  # urgency | friendly | social_proof | discount
    offer: str | None = None
    send_delay_minutes: int = 0
    outcome: str | None = None  # converted | ignored | unsubscribed
    time_to_convert_minutes: float | None = None
    experiment_arm: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    outcome_at: datetime | None = None


class DAGNode(BaseModel):
    """A node in the Growth DAG at any depth."""

    id: UUID = Field(default_factory=uuid4)
    depth: int  # 0=raw, 1=trigger_summary, 2=pattern, 3=strategy
    trigger_id: UUID | None = None
    period: str  # "2026-03-25" for daily, "2026-W13" for weekly, "2026-03" for monthly
    summary_text: str
    source_node_ids: list[UUID] = Field(default_factory=list)  # Links to source nodes
    stats: dict = Field(default_factory=dict)  # sends, conversions, conversion_rate, etc.
    created_at: datetime = Field(default_factory=datetime.now)


class TriggerDailySummary(DAGNode):
    """Layer 1: Daily trigger summary with typed stats.

    stats includes: total_sends, total_conversions, conversion_rate,
    best_tone, best_channel, best_time_window, notable_patterns
    """

    depth: int = 1


class PatternWeeklySummary(DAGNode):
    """Layer 2: Weekly cross-trigger pattern summary.

    stats includes: cross_trigger_insights, channel_comparison,
    timing_patterns, segment_patterns
    """

    depth: int = 2


class StrategyMonthlySummary(DAGNode):
    """Layer 3: Monthly business strategy narrative.

    stats includes: core_thesis, top_opportunities, untapped_segments
    """

    depth: int = 3
