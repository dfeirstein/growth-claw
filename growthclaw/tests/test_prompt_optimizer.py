"""Tests for prompt optimizer — verifies self-hosting pass."""

from __future__ import annotations

from unittest.mock import AsyncMock


async def test_optimize_prompts_queries_journeys():
    from growthclaw.autoresearch.prompt_optimizer import optimize_prompts

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    llm = AsyncMock()
    llm.call_json = AsyncMock(
        return_value={
            "analysis": "No data yet",
            "winning_patterns": [],
            "proposed_rewrites": [],
        }
    )

    memory = AsyncMock()
    memory.recall = AsyncMock(return_value=[])
    memory.store = AsyncMock()

    result = await optimize_prompts(conn, llm, memory)

    assert "analysis" in result
    conn.fetch.assert_called_once()


async def test_optimize_prompts_stores_winning_patterns():
    from growthclaw.autoresearch.prompt_optimizer import optimize_prompts

    conn = AsyncMock()
    conn.fetch = AsyncMock(
        return_value=[
            {
                "trigger_id": "t1",
                "message_body": "Hi!",
                "channel": "sms",
                "outcome": "converted",
                "trigger_name": "signup",
                "message_context": "test",
                "autoresearch_arm": "control",
                "count": 5,
            },
        ]
    )

    llm = AsyncMock()
    llm.call_json = AsyncMock(
        return_value={
            "analysis": "Short messages win",
            "winning_patterns": ["Short messages have 20% higher conversion"],
            "proposed_rewrites": [],
        }
    )

    memory = AsyncMock()
    memory.recall = AsyncMock(return_value=[])
    memory.store = AsyncMock()

    result = await optimize_prompts(conn, llm, memory)

    assert len(result["winning_patterns"]) == 1
    memory.store.assert_called_once()


async def test_optimize_prompts_returns_rewrites():
    from growthclaw.autoresearch.prompt_optimizer import optimize_prompts

    conn = AsyncMock()
    conn.fetch = AsyncMock(
        return_value=[
            {
                "trigger_id": "t1",
                "trigger_name": "signup",
                "channel": "sms",
                "outcome": "converted",
                "message_body": "Welcome!",
                "autoresearch_arm": "test",
                "count": 3,
            },
        ]
    )

    llm = AsyncMock()
    llm.call_json = AsyncMock(
        return_value={
            "analysis": "Analysis",
            "winning_patterns": [],
            "proposed_rewrites": [
                {
                    "template_name": "compose_message.j2",
                    "current_version": "v1",
                    "proposed_version": "v2",
                    "reasoning": "Better tone",
                },
            ],
        }
    )

    memory = AsyncMock()
    memory.recall = AsyncMock(return_value=[])
    memory.store = AsyncMock()

    result = await optimize_prompts(conn, llm, memory)

    assert len(result["proposed_rewrites"]) == 1
    assert result["proposed_rewrites"][0]["template_name"] == "compose_message.j2"
