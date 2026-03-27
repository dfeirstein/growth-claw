"""Trigger proposer — uses LLM to propose trigger rules based on discovered funnel."""

from __future__ import annotations

import logging

from growthclaw.llm.client import LLMClient, render_template
from growthclaw.models.schema_map import BusinessConcepts, Funnel
from growthclaw.models.trigger import ProfileQuery, TriggerRule

logger = logging.getLogger("growthclaw.triggers.proposer")


async def propose_triggers(
    concepts: BusinessConcepts,
    funnel: Funnel,
    llm_client: LLMClient,
) -> list[TriggerRule]:
    """Use LLM to propose trigger rules based on the discovered funnel and concepts."""
    prompt = render_template(
        "propose_triggers.j2",
        business_type=concepts.business_type,
        business_description=concepts.business_description,
        funnel=funnel.model_dump(mode="json"),
        concepts=concepts.model_dump(mode="json"),
        biggest_dropoff=funnel.biggest_dropoff.model_dump(mode="json") if funnel.biggest_dropoff else {},
    )

    logger.info("Requesting trigger proposals from LLM")
    result = await llm_client.call_json_list(prompt, temperature=0.3, purpose="trigger_proposal")

    triggers: list[TriggerRule] = []
    for item in result:
        # Convert profile_queries from dicts to ProfileQuery models
        pqs = [ProfileQuery.model_validate(pq) for pq in item.get("profile_queries", [])]
        item["profile_queries"] = pqs

        trigger = TriggerRule.model_validate(item)
        triggers.append(trigger)

    # Sort by priority
    triggers.sort(key=lambda t: t.priority)

    logger.info("LLM proposed %d triggers", len(triggers))
    for t in triggers:
        logger.info(
            "  [%d] %s: %s (delay=%dmin, channel=%s)", t.priority, t.name, t.description, t.delay_minutes, t.channel
        )

    return triggers
