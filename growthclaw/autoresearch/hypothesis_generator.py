"""Generate experiment hypotheses using LLM analysis of metrics and history."""

from __future__ import annotations

from growthclaw.llm.client import LLMClient, render_template


async def generate_hypothesis(
    current_metrics: dict,
    history: list,
    llm_client: LLMClient,
) -> dict:
    """Propose the next A/B test hypothesis based on current metrics and past experiments.

    Args:
        current_metrics: Current trigger performance (sends, conversions, rate, etc.).
        history: List of past experiment cycles (most recent first).
        llm_client: Unified LLM client.

    Returns:
        Dict with: hypothesis, variable, control_value, test_value,
        expected_uplift, reasoning, min_sample_size.
    """
    prompt = render_template(
        "generate_hypothesis.j2",
        current_metrics=current_metrics,
        history=history,
    )
    return await llm_client.call_json(prompt, temperature=0.4)
