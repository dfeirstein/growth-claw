"""Pydantic models for customer profiles and intelligence briefs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IntelligenceBrief(BaseModel):
    """LLM-generated analysis of a customer profile."""

    summary: str = ""
    customer_segment: str = ""
    engagement_level: str = ""
    key_facts: list[str] = Field(default_factory=list)
    recommended_tone: str = ""
    recommended_cta: str = ""
    risk_factors: list[str] = Field(default_factory=list)


class CustomerProfile(BaseModel):
    """A cached customer profile with raw data and LLM analysis."""

    user_id: str
    raw_data: dict = Field(default_factory=dict)
    analysis: IntelligenceBrief = Field(default_factory=IntelligenceBrief)
    computed_at: datetime = Field(default_factory=datetime.now)
