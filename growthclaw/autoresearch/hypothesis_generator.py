"""Generate experiment hypotheses using LLM analysis of metrics, history, and memory."""

from __future__ import annotations

from growthclaw.llm.client import LLMClient, render_template


async def generate_hypothesis(
    current_metrics: dict,
    history: list,
    llm_client: LLMClient,
    memory_context: dict | None = None,
) -> dict:
    """Propose the next A/B test hypothesis based on metrics, history, and agent memory.

    Args:
        current_metrics: Current trigger performance (sends, conversions, rate, etc.).
        history: List of past experiment cycles (most recent first).
        llm_client: Unified LLM client.
        memory_context: Optional dict with past_hypotheses, known_patterns, guardrails from memory.

    Returns:
        Dict with: hypothesis, variable, control_value, test_value,
        expected_uplift, reasoning, min_sample_size.
    """
    ctx = memory_context or {}
    prompt = render_template(
        "generate_hypothesis.j2",
        current_metrics=current_metrics,
        history=history,
        past_hypotheses=ctx.get("past_hypotheses", []),
        known_patterns=ctx.get("known_patterns", []),
        guardrails=ctx.get("guardrails", []),
    )
    return await llm_client.call_json(prompt, temperature=0.4, purpose="hypothesis_generation")
