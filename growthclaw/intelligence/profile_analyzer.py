"""Profile analyzer — uses LLM to produce an intelligence brief from customer profile data."""

from __future__ import annotations

import logging

from growthclaw.llm.client import LLMClient, render_template
from growthclaw.models.profile import IntelligenceBrief
from growthclaw.models.schema_map import BusinessConcepts

logger = logging.getLogger("growthclaw.intelligence.profile_analyzer")


async def analyze_profile(
    profile_data: dict,
    concepts: BusinessConcepts,
    trigger_context: str,
    llm_client: LLMClient,
    business_name: str = "",
) -> IntelligenceBrief:
    """Analyze customer profile data and produce an intelligence brief."""
    prompt = render_template(
        "analyze_profile.j2",
        business_name=business_name or concepts.business_description,
        business_type=concepts.business_type,
        business_description=concepts.business_description,
        profile_data=profile_data,
        trigger_context=trigger_context,
    )

    result = await llm_client.call_json(prompt, temperature=0.1)
    brief = IntelligenceBrief.model_validate(result)

    logger.info("Profile analyzed: segment=%s, engagement=%s", brief.customer_segment, brief.engagement_level)
    return brief
