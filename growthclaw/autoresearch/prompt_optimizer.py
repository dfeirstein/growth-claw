"""Prompt optimizer — analyzes journey outcomes and proposes template rewrites."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import asyncpg

from growthclaw.llm.client import LLMClient, render_template
from growthclaw.memory.manager import MemoryManager

logger = logging.getLogger("growthclaw.autoresearch.prompt_optimizer")

# Directory containing prompt templates
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


async def optimize_prompts(
    internal_conn: asyncpg.Connection,  # type: ignore[type-arg]
    llm_client: LLMClient,
    memory: MemoryManager,
) -> dict[str, Any]:
    """Analyze recent journey outcomes and propose prompt template improvements.

    Queries journeys from the last 30 days grouped by trigger, loads
    current prompt templates, and asks the LLM to identify winning
    patterns and propose rewrites.
    """
    # 1. Query journeys with outcomes from last 30 days, grouped by trigger
    trigger_results = await _get_trigger_results(internal_conn)

    if not trigger_results:
        logger.info("No journey outcomes in the last 30 days, skipping prompt optimization")
        return {"analysis": "No data available", "winning_patterns": [], "proposed_rewrites": []}

    # 2. Get current prompt templates
    current_templates = _load_prompt_templates()

    # 3. Recall validated patterns from memory
    memory_patterns: list[str] = []
    try:
        memories = await memory.recall(
            query="validated message patterns and winning copy",
            category="pattern",
            limit=10,
        )
        memory_patterns = [m.text for m in memories]
    except Exception as e:
        logger.warning("Memory recall failed during prompt optimization: %s", e)

    # 4. Render the optimization prompt and call LLM
    prompt = render_template(
        "optimize_prompts.j2",
        trigger_results=trigger_results,
        current_templates=current_templates,
        memory_patterns=memory_patterns,
    )

    result = await llm_client.call_json(prompt, purpose="prompt_optimization")
    logger.info(
        "Prompt optimization complete: patterns=%d, rewrites=%d",
        len(result.get("winning_patterns", [])),
        len(result.get("proposed_rewrites", [])),
    )

    # Store winning patterns in memory
    for pattern in result.get("winning_patterns", []):
        try:
            await memory.store(
                text=f"Winning pattern: {pattern}",
                category="pattern",
                importance=0.85,
                tags=["prompt_optimization", "winning_pattern"],
            )
        except Exception as e:
            logger.warning("Failed to store winning pattern in memory: %s", e)

    return result


async def _get_trigger_results(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> list[dict[str, Any]]:
    """Query journeys with outcomes from last 30 days, grouped by trigger."""
    try:
        rows = await conn.fetch(
            """
            SELECT
                t.id AS trigger_id,
                t.name AS trigger_name,
                t.channel,
                j.outcome,
                j.message_body,
                j.autoresearch_arm,
                COUNT(*) AS count
            FROM growthclaw.journeys j
            JOIN growthclaw.triggers t ON t.id = j.trigger_id
            WHERE j.created_at > NOW() - INTERVAL '30 days'
              AND j.outcome IS NOT NULL
            GROUP BY t.id, t.name, t.channel, j.outcome, j.message_body, j.autoresearch_arm
            ORDER BY t.name, j.outcome
            """
        )
        # Group by trigger
        triggers: dict[str, dict[str, Any]] = {}
        for row in rows:
            tid = str(row["trigger_id"])
            if tid not in triggers:
                triggers[tid] = {
                    "trigger_name": row["trigger_name"],
                    "channel": row["channel"],
                    "outcomes": [],
                }
            triggers[tid]["outcomes"].append(
                {
                    "outcome": row["outcome"],
                    "message_body": row["message_body"] or "",
                    "autoresearch_arm": row["autoresearch_arm"] or "control",
                    "count": row["count"],
                }
            )
        return list(triggers.values())
    except Exception as e:
        logger.warning("Failed to query trigger results: %s", e)
        return []


def _load_prompt_templates() -> list[dict[str, str]]:
    """Load all .j2 prompt templates from the prompts directory."""
    templates: list[dict[str, str]] = []
    if not PROMPTS_DIR.exists():
        return templates

    for template_file in sorted(PROMPTS_DIR.glob("*.j2")):
        try:
            content = template_file.read_text()
            templates.append({"name": template_file.name, "content": content})
        except Exception as e:
            logger.warning("Failed to read template %s: %s", template_file.name, e)

    return templates
