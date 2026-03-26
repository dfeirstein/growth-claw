"""LLM usage tracking — records every LLM call with provider, tokens, estimated cost."""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

logger = logging.getLogger("growthclaw.llm.usage")

# Estimated costs per 1M tokens (cents) — March 2026
COST_PER_M_TOKENS: dict[str, dict[str, float]] = {
    "subscription": {"input": 0, "output": 0},  # Free with Claude Code subscription
    "anthropic_sonnet": {"input": 300, "output": 1500},  # Sonnet 4.6: $3/$15 per M
    "anthropic_opus": {"input": 500, "output": 2500},  # Opus 4.6: $5/$25 per M
    "anthropic": {"input": 300, "output": 1500},  # Default to Sonnet rates
    "nvidia": {"input": 200, "output": 200},  # NIM cloud: ~$2/$2 per M
    "nvidia_local": {"input": 0, "output": 0},  # Self-hosted: no per-token cost
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


def estimate_cost_cents(provider: str, input_tokens: int, output_tokens: int) -> int:
    """Estimate cost in cents for a given provider and token counts."""
    rates = COST_PER_M_TOKENS.get(provider, {"input": 300, "output": 1500})
    input_cost = input_tokens / 1_000_000 * rates["input"]
    output_cost = output_tokens / 1_000_000 * rates["output"]
    return round((input_cost + output_cost) * 100)  # cents


async def record_usage(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    purpose: str,
    cost_cents: int = 0,
) -> None:
    """Record an LLM call to the usage tracking table."""
    try:
        await conn.execute(
            """
            INSERT INTO growthclaw.llm_usage
                (provider, model, input_tokens, output_tokens, cost_cents, purpose)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            provider,
            model,
            input_tokens,
            output_tokens,
            cost_cents,
            purpose,
        )
    except Exception as e:
        # Don't let usage tracking failures break the pipeline
        logger.warning("Failed to record LLM usage: %s", e)


async def get_usage_summary(conn: asyncpg.Connection) -> dict[str, Any]:  # type: ignore[type-arg]
    """Get usage summary for dashboard display."""
    rows = await conn.fetch("""
        SELECT
            provider,
            COUNT(*) as call_count,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens,
            SUM(cost_cents) as total_cost_cents
        FROM growthclaw.llm_usage
        WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY provider
        ORDER BY total_cost_cents DESC
    """)

    summary: dict[str, Any] = {"providers": [], "total_cost_cents": 0, "total_calls": 0}
    for r in rows:
        summary["providers"].append(
            {
                "provider": r["provider"],
                "calls": r["call_count"],
                "input_tokens": r["total_input_tokens"],
                "output_tokens": r["total_output_tokens"],
                "cost_cents": r["total_cost_cents"],
            }
        )
        summary["total_cost_cents"] += r["total_cost_cents"] or 0
        summary["total_calls"] += r["call_count"] or 0

    return summary
