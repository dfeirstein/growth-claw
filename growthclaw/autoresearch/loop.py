"""AutoResearch loop — continuously optimizes each trigger through experimentation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import asyncpg

from growthclaw.autoresearch.evaluator import evaluate_cycle
from growthclaw.autoresearch.hypothesis_generator import generate_hypothesis
from growthclaw.autoresearch.variant_creator import create_variant
from growthclaw.llm.client import LLMClient

logger = logging.getLogger("growthclaw.autoresearch")


class AutoResearchLoop:
    """Runs the observe-hypothesize-create-deploy loop for a single trigger."""

    def __init__(self, llm_client: LLMClient, settings) -> None:
        self.llm = llm_client
        self.settings = settings

    async def run_cycle(self, trigger_id: int, internal_conn: asyncpg.Connection) -> dict:
        """Execute one full AutoResearch cycle for a trigger.

        Steps:
            1. OBSERVE  — gather current metrics and experiment history.
            2. EVALUATE — if a running cycle has enough data, evaluate it first.
            3. HYPOTHESIZE — LLM proposes the next test.
            4. CREATE   — LLM generates control/test message variants.
            5. DEPLOY   — persist the new cycle to the database.

        Args:
            trigger_id: ID of the trigger to optimize.
            internal_conn: Connection to the GrowthClaw internal database.

        Returns:
            Dict summarizing what happened in this cycle.
        """
        # ------------------------------------------------------------------
        # 1. OBSERVE: get current metrics + experiment history
        # ------------------------------------------------------------------
        current_metrics = await self._get_trigger_metrics(trigger_id, internal_conn)
        history = await self._get_experiment_history(trigger_id, internal_conn)

        logger.info(
            "AutoResearch OBSERVE complete",
            extra={"trigger_id": trigger_id, "history_count": len(history)},
        )

        # ------------------------------------------------------------------
        # 2. EVALUATE: if a running cycle exists with enough data, evaluate it
        # ------------------------------------------------------------------
        running_cycle = await self._get_running_cycle(trigger_id, internal_conn)
        evaluation = None

        if running_cycle:
            sample_size = running_cycle.get("total_sent", 0)
            min_sample = running_cycle.get("min_sample_size", 100)

            if sample_size >= min_sample:
                logger.info(
                    "Evaluating running cycle",
                    extra={"trigger_id": trigger_id, "sample_size": sample_size},
                )
                evaluation = await evaluate_cycle(running_cycle, self.llm)
                await self._close_cycle(running_cycle["cycle_id"], evaluation, internal_conn)
            else:
                logger.info(
                    "Running cycle needs more data",
                    extra={
                        "trigger_id": trigger_id,
                        "sample_size": sample_size,
                        "min_sample": min_sample,
                    },
                )
                return {
                    "action": "waiting",
                    "trigger_id": trigger_id,
                    "cycle_id": running_cycle["cycle_id"],
                    "sample_size": sample_size,
                    "min_sample_size": min_sample,
                }

        # ------------------------------------------------------------------
        # 3. HYPOTHESIZE: LLM proposes next test
        # ------------------------------------------------------------------
        hypothesis = await generate_hypothesis(current_metrics, history, self.llm)
        logger.info(
            "AutoResearch HYPOTHESIZE complete",
            extra={
                "trigger_id": trigger_id,
                "variable": hypothesis.get("variable"),
                "expected_uplift": hypothesis.get("expected_uplift"),
            },
        )

        # ------------------------------------------------------------------
        # 4. CREATE: LLM creates variants
        # ------------------------------------------------------------------
        variants = await create_variant(hypothesis, trigger_id, self.llm)
        logger.info(
            "AutoResearch CREATE complete",
            extra={"trigger_id": trigger_id},
        )

        # ------------------------------------------------------------------
        # 5. DEPLOY: save new cycle to DB
        # ------------------------------------------------------------------
        cycle_id = await self._save_cycle(trigger_id, hypothesis, variants, internal_conn)
        logger.info(
            "AutoResearch DEPLOY complete",
            extra={"trigger_id": trigger_id, "cycle_id": cycle_id},
        )

        return {
            "action": "new_cycle",
            "trigger_id": trigger_id,
            "cycle_id": cycle_id,
            "hypothesis": hypothesis,
            "variants": variants,
            "previous_evaluation": evaluation,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_trigger_metrics(self, trigger_id: int, conn: asyncpg.Connection) -> dict:
        """Fetch current performance metrics for a trigger."""
        row = await conn.fetchrow(
            """
            SELECT
                t.id, t.name, t.channel,
                COUNT(j.id) AS total_sends,
                COUNT(j.id) FILTER (WHERE j.outcome = 'converted') AS total_conversions,
                CASE WHEN COUNT(j.id) > 0
                     THEN COUNT(j.id) FILTER (WHERE j.outcome = 'converted')::float / COUNT(j.id)
                     ELSE 0 END AS conversion_rate
            FROM triggers t
            LEFT JOIN journeys j ON j.trigger_id = t.id
            WHERE t.id = $1
            GROUP BY t.id, t.name, t.channel
            """,
            trigger_id,
        )
        if row is None:
            return {"trigger_id": trigger_id, "total_sends": 0, "total_conversions": 0, "conversion_rate": 0.0}
        return dict(row)

    async def _get_experiment_history(self, trigger_id: int, conn: asyncpg.Connection) -> list:
        """Fetch completed experiment cycles for a trigger, most recent first."""
        rows = await conn.fetch(
            """
            SELECT cycle_id, variable, control_value, test_value,
                   control_sent, control_converted, test_sent, test_converted,
                   decision, uplift_pct, confidence, created_at, completed_at
            FROM autoresearch_cycles
            WHERE trigger_id = $1 AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 20
            """,
            trigger_id,
        )
        return [dict(r) for r in rows]

    async def _get_running_cycle(self, trigger_id: int, conn: asyncpg.Connection) -> dict | None:
        """Fetch the currently running cycle for a trigger, if any."""
        row = await conn.fetchrow(
            """
            SELECT cycle_id, variable, control_value, test_value,
                   control_sent, control_converted, test_sent, test_converted,
                   min_sample_size, created_at,
                   (control_sent + test_sent) AS total_sent
            FROM autoresearch_cycles
            WHERE trigger_id = $1 AND status = 'running'
            LIMIT 1
            """,
            trigger_id,
        )
        if row is None:
            return None

        cycle = dict(row)
        # Build the arms structure expected by evaluator
        cycle["experiment_name"] = f"AutoResearch cycle {cycle['cycle_id']}"
        cycle["metric"] = "conversion_rate"
        cycle["duration_days"] = (datetime.now(UTC) - cycle["created_at"]).days if cycle.get("created_at") else 0
        cycle["arms"] = [
            {
                "arm_name": "control",
                "total_sent": cycle.get("control_sent", 0),
                "total_converted": cycle.get("control_converted", 0),
                "conversion_rate": (
                    cycle["control_converted"] / cycle["control_sent"] * 100
                    if cycle.get("control_sent", 0) > 0
                    else 0.0
                ),
            },
            {
                "arm_name": "test",
                "total_sent": cycle.get("test_sent", 0),
                "total_converted": cycle.get("test_converted", 0),
                "conversion_rate": (
                    cycle["test_converted"] / cycle["test_sent"] * 100 if cycle.get("test_sent", 0) > 0 else 0.0
                ),
            },
        ]
        cycle["min_sample"] = cycle.get("min_sample_size", 100)
        return cycle

    async def _close_cycle(self, cycle_id: int, evaluation: dict, conn: asyncpg.Connection) -> None:
        """Mark a cycle as completed with its evaluation results."""
        await conn.execute(
            """
            UPDATE autoresearch_cycles
            SET status = 'completed',
                decision = $2,
                uplift_pct = $3,
                confidence = $4,
                reasoning = $5,
                completed_at = NOW()
            WHERE cycle_id = $1
            """,
            cycle_id,
            evaluation["decision"],
            evaluation["uplift_pct"],
            evaluation["confidence"],
            evaluation.get("reasoning", ""),
        )

    async def _save_cycle(
        self,
        trigger_id: int,
        hypothesis: dict,
        variants: dict,
        conn: asyncpg.Connection,
    ) -> int:
        """Persist a new experiment cycle to the database."""
        cycle_id = await conn.fetchval(
            """
            INSERT INTO autoresearch_cycles (
                trigger_id, status, variable,
                control_value, test_value,
                control_desc, test_desc,
                control_template, test_template,
                expected_uplift, reasoning, min_sample_size,
                control_sent, control_converted,
                test_sent, test_converted,
                created_at
            ) VALUES (
                $1, 'running', $2,
                $3, $4,
                $5, $6,
                $7, $8,
                $9, $10, $11,
                0, 0,
                0, 0,
                NOW()
            )
            RETURNING cycle_id
            """,
            trigger_id,
            hypothesis.get("variable", "unknown"),
            hypothesis.get("control_value", ""),
            hypothesis.get("test_value", ""),
            variants.get("control_desc", ""),
            variants.get("test_desc", ""),
            variants.get("control_template", ""),
            variants.get("test_template", ""),
            hypothesis.get("expected_uplift", 0.0),
            hypothesis.get("reasoning", ""),
            hypothesis.get("min_sample_size", 100),
        )
        return cycle_id
