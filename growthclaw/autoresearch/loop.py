"""AutoResearch loop — continuously optimizes each trigger through experimentation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from growthclaw.autoresearch.evaluator import evaluate_cycle
from growthclaw.autoresearch.hypothesis_generator import generate_hypothesis
from growthclaw.autoresearch.variant_creator import create_variant
from growthclaw.llm.client import LLMClient

logger = logging.getLogger("growthclaw.autoresearch")


class AutoResearchLoop:
    """Runs the observe-hypothesize-create-deploy loop for a single trigger."""

    def __init__(self, llm_client: LLMClient, settings: object) -> None:
        self.llm = llm_client
        self.settings = settings
        self._memory = None
        self._dag: object | None = None

    async def _get_memory(self):  # type: ignore[no-untyped-def]
        """Lazy-load memory manager."""
        if self._memory is None:
            try:
                from growthclaw.memory.manager import MemoryManager

                self._memory = MemoryManager(getattr(self.settings, "memory_db_path", None))
                await self._memory.initialize()
            except Exception as e:
                logger.warning("Memory system unavailable: %s", e)
        return self._memory

    async def run_cycle(self, trigger_id: UUID, internal_conn: asyncpg.Connection) -> dict:  # type: ignore[type-arg]
        """Execute one full AutoResearch cycle for a trigger."""
        # 1. OBSERVE: get current metrics + experiment history + memory
        current_metrics = await self._get_trigger_metrics(trigger_id, internal_conn)
        history = await self._get_experiment_history(trigger_id, internal_conn)

        # Memory-enhanced observe
        past_hypotheses = []
        patterns = []
        guardrails = []
        memory = await self._get_memory()
        if memory:
            try:
                past_hypotheses = await memory.recall(
                    query=f"hypotheses tested on trigger {current_metrics.get('name', '')}",
                    category="hypothesis",
                    limit=5,
                )
                patterns = await memory.recall(
                    query=f"validated patterns for {current_metrics.get('channel', 'sms')} outreach",
                    category="pattern",
                    limit=5,
                )
                guardrails = await memory.recall(query="constraints and guardrails", category="guardrail", limit=5)
            except Exception as e:
                logger.warning("Memory recall failed: %s", e)

        # DAG-enhanced observe — get hierarchical performance summaries
        dag_insights: list[str] = []
        if self._dag:
            try:
                dag_nodes = await self._dag.get_research_context(current_metrics.get("name", ""))
                dag_insights = [n.summary_text for n in dag_nodes]
            except Exception as e:
                logger.warning("DAG research context fetch failed: %s", e)

        logger.info(
            "AutoResearch OBSERVE: trigger=%s, history=%d, memories=%d",
            trigger_id,
            len(history),
            len(past_hypotheses) + len(patterns) + len(guardrails),
        )

        # 2. EVALUATE: if a running cycle exists with enough data
        running_cycle = await self._get_running_cycle(trigger_id, internal_conn)
        evaluation = None

        if running_cycle:
            control_sends = running_cycle.get("control_sends", 0)
            test_sends = running_cycle.get("test_sends", 0)
            total_sent = control_sends + test_sends
            min_sample = running_cycle.get("min_sample_size", 100)

            if total_sent >= min_sample:
                evaluation = await evaluate_cycle(running_cycle, self.llm)
                await self._close_cycle(running_cycle["id"], evaluation, internal_conn)

                # Store evaluation result in memory
                if memory:
                    try:
                        decision = evaluation.get("decision", "inconclusive")
                        if decision == "promote_test":
                            await memory.store(
                                text=f"Validated: {running_cycle.get('hypothesis', '')} — "
                                f"{evaluation.get('uplift_pct', 0):.1f}% uplift",
                                category="pattern",
                                importance=0.95,
                                trigger_id=trigger_id,
                                tags=["validated", running_cycle.get("variable", "")],
                            )
                        else:
                            await memory.store(
                                text=f"Tested: {running_cycle.get('hypothesis', '')} — {decision}",
                                category="hypothesis",
                                importance=0.7,
                                trigger_id=trigger_id,
                                tags=["tested", running_cycle.get("variable", "")],
                            )
                    except Exception as e:
                        logger.warning("Memory store failed: %s", e)
            else:
                return {
                    "action": "waiting",
                    "trigger_id": str(trigger_id),
                    "sample_size": total_sent,
                    "min_sample_size": min_sample,
                }

        # 3. HYPOTHESIZE: LLM proposes next test (with memory context)
        memory_context = {
            "past_hypotheses": [m.text for m in past_hypotheses] if past_hypotheses else [],
            "known_patterns": [m.text for m in patterns] if patterns else [],
            "guardrails": [m.text for m in guardrails] if guardrails else [],
        }
        hypothesis = await generate_hypothesis(current_metrics, history, self.llm, memory_context=memory_context)
        logger.info("AutoResearch HYPOTHESIZE: variable=%s", hypothesis.get("variable"))

        # 4. CREATE: LLM creates variants
        variants = await create_variant(hypothesis, trigger_id, self.llm)

        # 5. DEPLOY: save new cycle to DB
        cycle_number = (history[0].get("cycle_number", 0) + 1) if history else 1
        cycle_id = await self._save_cycle(trigger_id, cycle_number, hypothesis, variants, internal_conn)
        logger.info("AutoResearch DEPLOY: cycle_id=%s, cycle_number=%d", cycle_id, cycle_number)

        return {
            "action": "new_cycle",
            "trigger_id": str(trigger_id),
            "cycle_id": str(cycle_id),
            "hypothesis": hypothesis,
            "previous_evaluation": evaluation,
        }

    # ── Private helpers ──────────────────────────────────────────────────

    async def _get_trigger_metrics(self, trigger_id: UUID, conn: asyncpg.Connection) -> dict:  # type: ignore[type-arg]
        row = await conn.fetchrow(
            """
            SELECT t.id, t.name, t.channel,
                   COUNT(j.id) AS total_sends,
                   COUNT(j.id) FILTER (WHERE j.outcome = 'converted') AS total_conversions,
                   CASE WHEN COUNT(j.id) > 0
                        THEN COUNT(j.id) FILTER (WHERE j.outcome = 'converted')::float / COUNT(j.id)
                        ELSE 0 END AS conversion_rate
            FROM growthclaw.triggers t
            LEFT JOIN growthclaw.journeys j ON j.trigger_id = t.id
            WHERE t.id = $1
            GROUP BY t.id, t.name, t.channel
            """,
            trigger_id,
        )
        if row is None:
            return {"trigger_id": str(trigger_id), "total_sends": 0, "conversion_rate": 0.0}
        return dict(row)

    async def _get_experiment_history(self, trigger_id: UUID, conn: asyncpg.Connection) -> list:  # type: ignore[type-arg]
        rows = await conn.fetch(
            """
            SELECT id, cycle_number, hypothesis, variable, control_desc, test_desc,
                   control_sends, control_conversions, test_sends, test_conversions,
                   decision, uplift_pct, confidence, started_at, completed_at
            FROM growthclaw.autoresearch_cycles
            WHERE trigger_id = $1 AND status = 'completed'
            ORDER BY completed_at DESC LIMIT 20
            """,
            trigger_id,
        )
        return [dict(r) for r in rows]

    async def _get_running_cycle(self, trigger_id: UUID, conn: asyncpg.Connection) -> dict | None:  # type: ignore[type-arg]
        row = await conn.fetchrow(
            """
            SELECT id, cycle_number, hypothesis, variable, control_desc, test_desc,
                   control_sends, control_conversions, test_sends, test_conversions,
                   min_sample_size, started_at
            FROM growthclaw.autoresearch_cycles
            WHERE trigger_id = $1 AND status = 'running'
            LIMIT 1
            """,
            trigger_id,
        )
        if row is None:
            return None

        cycle = dict(row)
        # Build arms for evaluator
        cs = cycle.get("control_sends", 0) or 0
        cc = cycle.get("control_conversions", 0) or 0
        ts = cycle.get("test_sends", 0) or 0
        tc = cycle.get("test_conversions", 0) or 0
        cycle["experiment_name"] = f"AutoResearch cycle {cycle.get('cycle_number', '?')}"
        cycle["metric"] = "conversion_rate"
        cycle["duration_days"] = (datetime.now(UTC) - cycle["started_at"]).days if cycle.get("started_at") else 0
        cycle["arms"] = [
            {
                "arm_name": "control",
                "total_sent": cs,
                "total_converted": cc,
                "conversion_rate": cc / cs * 100 if cs > 0 else 0.0,
            },
            {
                "arm_name": "test",
                "total_sent": ts,
                "total_converted": tc,
                "conversion_rate": tc / ts * 100 if ts > 0 else 0.0,
            },
        ]
        return cycle

    async def _close_cycle(self, cycle_id: UUID, evaluation: dict, conn: asyncpg.Connection) -> None:  # type: ignore[type-arg]
        await conn.execute(
            """
            UPDATE growthclaw.autoresearch_cycles
            SET status = 'completed', decision = $2, uplift_pct = $3,
                confidence = $4, reasoning = $5, completed_at = NOW()
            WHERE id = $1
            """,
            cycle_id,
            evaluation["decision"],
            evaluation["uplift_pct"],
            evaluation["confidence"],
            evaluation.get("reasoning", ""),
        )

    async def _save_cycle(
        self,
        trigger_id: UUID,
        cycle_number: int,
        hypothesis: dict,
        variants: dict,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
    ) -> UUID:
        cycle_id = await conn.fetchval(
            """
            INSERT INTO growthclaw.autoresearch_cycles (
                trigger_id, cycle_number, hypothesis, variable,
                control_desc, test_desc, control_template, test_template,
                min_sample_size, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'running')
            RETURNING id
            """,
            trigger_id,
            cycle_number,
            hypothesis.get("hypothesis", ""),
            hypothesis.get("variable", "unknown"),
            variants.get("control_desc", ""),
            variants.get("test_desc", ""),
            variants.get("control_template", ""),
            variants.get("test_template", ""),
            hypothesis.get("min_sample_size", 100),
        )
        return cycle_id
