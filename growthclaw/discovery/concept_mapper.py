"""Concept mapper — uses LLM to classify tables and map business concepts from discovered schema."""

from __future__ import annotations

import logging

from growthclaw.llm.client import LLMClient, render_template
from growthclaw.models.schema_map import BusinessConcepts, RawSchema, TableSample

logger = logging.getLogger("growthclaw.discovery.concept_mapper")


async def map_concepts(
    raw_schema: RawSchema,
    samples: dict[str, TableSample],
    llm_client: LLMClient,
    business_name: str = "",
    business_description: str = "",
) -> BusinessConcepts:
    """Feed schema + sample data to LLM and get back mapped business concepts."""
    # Render the classification prompt
    prompt = render_template(
        "classify_schema.j2",
        tables=raw_schema.tables,
        business_name=business_name,
        business_description=business_description,
    )

    logger.info("Sending schema classification to LLM (%d tables)", len(raw_schema.tables))

    # Call LLM and parse JSON response
    result = await llm_client.call_json(prompt, temperature=0.1, max_tokens=4096)

    # Validate through Pydantic model
    concepts = BusinessConcepts.model_validate(result)

    logger.info(
        "Concepts mapped: business_type=%s, customer_table=%s, activation=%s",
        concepts.business_type,
        concepts.customer_table,
        concepts.activation_event,
    )

    return concepts
