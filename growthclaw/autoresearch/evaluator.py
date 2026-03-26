"""Evaluate completed experiment cycles and decide next action."""

from __future__ import annotations

import math

from growthclaw.llm.client import LLMClient, render_template


def _conversion_rate(converted: int, sent: int) -> float:
    """Calculate conversion rate, returning 0.0 if no sends."""
    return (converted / sent) if sent > 0 else 0.0


def _basic_significance(
    control_sent: int,
    control_converted: int,
    test_sent: int,
    test_converted: int,
) -> float:
    """Compute a basic z-test confidence level for two proportions.

    Returns a confidence value between 0.0 and 1.0.
    """
    p_c = _conversion_rate(control_converted, control_sent)
    p_t = _conversion_rate(test_converted, test_sent)
    n_c = control_sent
    n_t = test_sent

    if n_c == 0 or n_t == 0:
        return 0.0

    p_pool = (control_converted + test_converted) / (n_c + n_t)
    if p_pool == 0.0 or p_pool == 1.0:
        return 0.0

    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    if se == 0:
        return 0.0

    z = abs(p_t - p_c) / se

    # Approximate two-tailed p-value -> confidence using normal CDF approximation
    # Using the Abramowitz & Stegun approximation
    t = 1.0 / (1.0 + 0.2316419 * z)
    d = 0.3989422804014327  # 1 / sqrt(2 * pi)
    p_val = (
        d
        * math.exp(-z * z / 2.0)
        * (0.3193815 * t - 0.3565638 * t**2 + 1.781478 * t**3 - 1.8212560 * t**4 + 1.3302744 * t**5)
    )
    confidence = 1.0 - 2.0 * p_val
    return max(0.0, min(1.0, confidence))


async def evaluate_cycle(cycle_data: dict, llm_client: LLMClient) -> dict:
    """Evaluate an experiment cycle and decide whether to promote, keep, or call inconclusive.

    Args:
        cycle_data: Dict with keys: experiment_name, variable, metric,
            arms (list of {arm_name, total_sent, total_converted, conversion_rate}),
            total_sent, duration_days.
        llm_client: Unified LLM client.

    Returns:
        Dict with: decision (promote_test|keep_control|inconclusive),
        uplift_pct, confidence, reasoning.
    """
    # Compute statistical significance from raw numbers
    arms = cycle_data.get("arms", [])
    control = next((a for a in arms if "control" in a.get("arm_name", "").lower()), None)
    test = next((a for a in arms if "test" in a.get("arm_name", "").lower()), None)

    confidence = 0.0
    uplift_pct = 0.0

    if control and test:
        c_sent = control.get("total_sent", 0)
        c_conv = control.get("total_converted", 0)
        t_sent = test.get("total_sent", 0)
        t_conv = test.get("total_converted", 0)

        confidence = _basic_significance(c_sent, c_conv, t_sent, t_conv)

        c_rate = _conversion_rate(c_conv, c_sent)
        t_rate = _conversion_rate(t_conv, t_sent)
        if c_rate > 0:
            uplift_pct = round(((t_rate - c_rate) / c_rate) * 100, 2)

    # Use the existing analyze_experiment.j2 template for LLM evaluation
    prompt = render_template(
        "analyze_experiment.j2",
        experiment_name=cycle_data.get("experiment_name", "AutoResearch Cycle"),
        variable=cycle_data.get("variable", "unknown"),
        metric=cycle_data.get("metric", "conversion_rate"),
        arms=arms,
        total_sent=cycle_data.get("total_sent", 0),
        duration_days=cycle_data.get("duration_days", 0),
    )

    llm_result = await llm_client.call_json(prompt, temperature=0.1, purpose="experiment_evaluation")

    # Map LLM winner to a decision
    winner = llm_result.get("winner", "inconclusive").lower()

    if "inconclusive" in winner or confidence < 0.9:
        decision = "inconclusive"
    elif "test" in winner and confidence >= 0.9:
        decision = "promote_test"
    else:
        decision = "keep_control"

    return {
        "decision": decision,
        "uplift_pct": uplift_pct,
        "confidence": round(confidence, 4),
        "reasoning": llm_result.get("analysis", ""),
        "llm_recommendation": llm_result.get("recommendation", ""),
        "suggested_next": llm_result.get("suggested_next_experiment"),
    }
