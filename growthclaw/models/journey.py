"""Pydantic models for outreach journeys."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Journey(BaseModel):
    """A single outreach event in the customer journey."""

    id: UUID = Field(default_factory=uuid4)
    user_id: str
    trigger_id: UUID
    event_id: UUID | None = None
    channel: Literal["sms", "email"] = "sms"
    contact_info: str | None = None
    message_body: str
    provider_id: str | None = None  # Twilio SID, etc.
    status: Literal["composed", "approved", "sent", "delivered", "failed"] = "composed"
    experiment_id: UUID | None = None
    experiment_arm: str | None = None
    llm_reasoning: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    sent_at: datetime | None = None
    outcome: Literal["converted", "ignored", "unsubscribed"] | None = None
    outcome_at: datetime | None = None
