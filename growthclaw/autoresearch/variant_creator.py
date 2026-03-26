"""Create control and test message variants from a hypothesis."""

from __future__ import annotations

from growthclaw.llm.client import LLMClient, render_template


async def create_variant(
    hypothesis: dict,
    trigger_id: int | str,
    llm_client: LLMClient,
) -> dict:
    """Generate control and test message templates for an experiment.

    Args:
        hypothesis: Output from generate_hypothesis (variable, values, etc.).
        trigger_id: ID of the trigger being tested.
        llm_client: Unified LLM client.

    Returns:
        Dict with: control_desc, test_desc, control_template, test_template.
    """
    prompt = render_template(
        "create_variant.j2",
        hypothesis=hypothesis,
        trigger_id=trigger_id,
    )
    return await llm_client.call_json(prompt, temperature=0.3, purpose="variant_creation")
