"""Pydantic models for A/B experiments."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExperimentArm(BaseModel):
    """A single arm/variant of an experiment."""

    name: str
    value: int | float | str  # e.g., delay_minutes value


class ExperimentResult(BaseModel):
    """Aggregated results for one arm of an experiment."""

    arm_name: str
    total_sent: int = 0
    total_converted: int = 0
    conversion_rate: float = 0.0
    last_updated: datetime = Field(default_factory=datetime.now)


class Experiment(BaseModel):
    """An A/B experiment on a trigger variable (e.g., delay timing)."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    trigger_id: UUID
    variable: str  # e.g., "delay_minutes"
    arms: list[ExperimentArm] = Field(default_factory=list)
    metric: str = "conversion_rate"  # What we're optimizing
    status: Literal["active", "paused", "completed"] = "active"
    results: list[ExperimentResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
