"""Growth DAG — hierarchical memory system for growth intelligence.

Four-layer DAG backed by SQLite, separate from LanceDB flat vector memory.

Layer 0: Raw send outcomes (every send, every outcome — never deleted)
Layer 1: Trigger summaries (daily compaction per trigger)
Layer 2: Pattern summaries (weekly cross-trigger condensation)
Layer 3: Strategy narratives (monthly business-level synthesis)

LanceDB = fast semantic search across flat text.
DAG     = structured hierarchical drill-down from strategy → raw events.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from uuid import UUID, uuid4

import aiosqlite

from growthclaw.llm.client import LLMClient, render_template
from growthclaw.memory.dag_models import DAGNode, SendOutcome
from growthclaw.models.schema_map import BusinessConcepts

logger = logging.getLogger("growthclaw.memory.dag")

DEFAULT_DB_PATH = os.path.expanduser("~/.growthclaw/growth_dag.db")

_CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS dag_events (
    id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL,
    trigger_name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    message_body TEXT,
    tone TEXT,
    offer TEXT,
    send_delay_minutes INTEGER DEFAULT 0,
    outcome TEXT,
    time_to_convert_minutes REAL,
    experiment_arm TEXT,
    created_at TEXT NOT NULL,
    outcome_at TEXT
);
"""

_CREATE_NODES_TABLE = """
CREATE TABLE IF NOT EXISTS dag_nodes (
    id TEXT PRIMARY KEY,
    depth INTEGER NOT NULL,
    trigger_id TEXT,
    period TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    source_node_ids TEXT NOT NULL DEFAULT '[]',
    stats TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_events_trigger_date ON dag_events(trigger_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_events_outcome ON dag_events(outcome);",
    "CREATE INDEX IF NOT EXISTS idx_nodes_depth_period ON dag_nodes(depth, period);",
    "CREATE INDEX IF NOT EXISTS idx_nodes_trigger ON dag_nodes(trigger_id);",
]


def _node_from_row(row: aiosqlite.Row) -> DAGNode:
    """Convert a DB row dict to a DAGNode."""
    return DAGNode(
        id=UUID(row["id"]),
        depth=row["depth"],
        trigger_id=UUID(row["trigger_id"]) if row["trigger_id"] else None,
        period=row["period"],
        summary_text=row["summary_text"],
        source_node_ids=[UUID(x) for x in json.loads(row["source_node_ids"])],
        stats=json.loads(row["stats"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


MAX_SUMMARY_CHARS = 2000


async def _ensure_convergence(
    summary_text: str,
    source_text_len: int,
    llm_client: LLMClient,
    purpose: str,
) -> str:
    """LCM convergence guard: ensure summary is shorter than source material.

    Three-level escalation per LCM paper:
    1. Normal — use the summary as-is if it's shorter
    2. Aggressive — re-prompt for bullet points only
    3. Deterministic — truncate to MAX_SUMMARY_CHARS
    """
    if len(summary_text) < source_text_len:
        return summary_text

    # Level 2: Aggressive re-prompt
    logger.warning(
        "Convergence violation: summary (%d) >= source (%d), re-prompting",
        len(summary_text), source_text_len,
    )
    aggressive_prompt = (
        f"This summary is too long ({len(summary_text)} chars). "
        f"Condense into bullet points only, max {MAX_SUMMARY_CHARS} chars. "
        f"Keep only key metrics and findings:\n\n{summary_text}"
    )
    try:
        result = await llm_client.call_json(aggressive_prompt, purpose=f"{purpose}_convergence")
        condensed = result.get("summary", summary_text)
        if len(condensed) < source_text_len:
            return condensed
    except Exception:
        pass

    # Level 3: Deterministic truncation
    logger.warning("Convergence still violated, deterministic truncation to %d chars", MAX_SUMMARY_CHARS)
    return summary_text[:MAX_SUMMARY_CHARS]


class GrowthDAG:
    """DAG-based hierarchical memory for growth intelligence.

    Layer 0: Raw send outcomes (every send, every outcome — never deleted)
    Layer 1: Trigger summaries (daily compaction per trigger)
    Layer 2: Pattern summaries (weekly cross-trigger condensation)
    Layer 3: Strategy narratives (monthly business-level synthesis)
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH

    async def initialize(self) -> None:
        """Create the SQLite database and tables if they don't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute(_CREATE_EVENTS_TABLE)
            await db.execute(_CREATE_NODES_TABLE)
            for idx_sql in _CREATE_INDEXES:
                await db.execute(idx_sql)
            await db.commit()
        logger.info("GrowthDAG initialized at %s", self.db_path)

    # -------------------------------------------------------------------------
    # Layer 0 — Raw events
    # -------------------------------------------------------------------------

    async def store_event(self, event: SendOutcome) -> UUID:
        """Store a raw send outcome (Layer 0). Never deleted."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO dag_events
                    (id, trigger_id, trigger_name, user_id, channel, message_body,
                     tone, offer, send_delay_minutes, outcome, time_to_convert_minutes,
                     experiment_arm, created_at, outcome_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.id),
                    str(event.trigger_id),
                    event.trigger_name,
                    event.user_id,
                    event.channel,
                    event.message_body,
                    event.tone,
                    event.offer,
                    event.send_delay_minutes,
                    event.outcome,
                    event.time_to_convert_minutes,
                    event.experiment_arm,
                    event.created_at.isoformat(),
                    event.outcome_at.isoformat() if event.outcome_at else None,
                ),
            )
            await db.commit()
        logger.debug("Stored Layer 0 event %s for trigger %s", event.id, event.trigger_id)
        return event.id

    async def update_event_outcome(
        self, event_id: UUID, outcome: str, outcome_at: datetime | None = None
    ) -> None:
        """Update a Layer 0 event with its outcome (called by outcome checker)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE dag_events SET outcome = ?, outcome_at = ?
                WHERE id = ?
                """,
                (
                    outcome,
                    (outcome_at or datetime.now()).isoformat(),
                    str(event_id),
                ),
            )
            await db.commit()
        logger.debug("Updated event %s outcome → %s", event_id, outcome)

    # -------------------------------------------------------------------------
    # Layer 1 — Daily trigger compaction (Layer 0 → Layer 1)
    # -------------------------------------------------------------------------

    async def compact_trigger_daily(
        self,
        trigger_id: UUID,
        date: str,
        llm_client: LLMClient,
    ) -> UUID | None:
        """Compact all Layer 0 events for a trigger on a date into a Layer 1 summary.

        Returns the new DAGNode UUID, or None if no events exist.
        """
        date_prefix = date[:10]  # Ensure "YYYY-MM-DD"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Fetch events for this trigger on this date
            cursor = await db.execute(
                """
                SELECT * FROM dag_events
                WHERE trigger_id = ? AND created_at LIKE ?
                ORDER BY created_at
                """,
                (str(trigger_id), f"{date_prefix}%"),
            )
            rows = await cursor.fetchall()

        if not rows:
            logger.debug("No events for trigger %s on %s — skipping compaction", trigger_id, date)
            return None

        # Build event dicts for template rendering
        events = [dict(r) for r in rows]
        trigger_name = events[0]["trigger_name"]
        source_ids = [row["id"] for row in events]

        # Call LLM for compaction summary
        prompt = render_template(
            "compact_trigger.j2",
            events=events,
            trigger_name=trigger_name,
            date=date_prefix,
        )
        result = await llm_client.call_json(prompt, purpose="dag_compact_trigger")

        source_text_len = sum(len(json.dumps(e)) for e in events)
        summary_text = await _ensure_convergence(
            result.get("summary", ""), source_text_len, llm_client, "dag_compact_trigger"
        )
        stats = result.get("stats", {})
        node_id = uuid4()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at)
                VALUES (?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(node_id),
                    str(trigger_id),
                    date_prefix,
                    summary_text,
                    json.dumps(source_ids),
                    json.dumps(stats),
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()

        logger.info("Compacted %d events → Layer 1 node %s (trigger %s, %s)", len(events), node_id, trigger_id, date)
        return node_id

    # -------------------------------------------------------------------------
    # Layer 2 — Weekly pattern condensation (Layer 1 → Layer 2)
    # -------------------------------------------------------------------------

    async def condense_patterns_weekly(
        self,
        week_start: str,
        llm_client: LLMClient,
    ) -> UUID | None:
        """Condense all Layer 1 trigger summaries from a week into a Layer 2 pattern node.

        week_start should be "YYYY-MM-DD" (Monday of the week).
        Returns the new DAGNode UUID, or None if no Layer 1 nodes exist for that week.
        """
        from datetime import timedelta

        # Build the ISO week label (e.g. "2026-W13")
        dt = datetime.strptime(week_start, "%Y-%m-%d")
        year, week, _ = dt.isocalendar()
        week_label = f"{year}-W{week:02d}"

        # Fetch all Layer 1 nodes whose period starts within this week
        week_end = (dt + timedelta(days=7)).strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM dag_nodes
                WHERE depth = 1 AND period >= ? AND period < ?
                ORDER BY period, trigger_id
                """,
                (week_start, week_end),
            )
            rows = await cursor.fetchall()

        if not rows:
            logger.debug("No Layer 1 nodes in week %s — skipping condensation", week_label)
            return None

        summaries = [dict(r) for r in rows]
        source_ids = [s["id"] for s in summaries]

        # Parse stats JSON and resolve trigger names from events table
        trigger_name_cache: dict[str, str] = {}
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT DISTINCT trigger_id, trigger_name FROM dag_events"
            )
            for row in await cursor.fetchall():
                trigger_name_cache[row["trigger_id"]] = row["trigger_name"]

        for s in summaries:
            s["stats"] = json.loads(s["stats"]) if isinstance(s["stats"], str) else s["stats"]
            tid = s.get("trigger_id", "")
            s["trigger_name"] = trigger_name_cache.get(tid, tid or "unknown")

        prompt = render_template(
            "condense_patterns.j2",
            summaries=summaries,
            week_start=week_label,
        )
        result = await llm_client.call_json(prompt, purpose="dag_condense_patterns")

        source_text_len = sum(len(s.get("summary_text", "")) for s in summaries)
        summary_text = await _ensure_convergence(
            result.get("summary", ""), source_text_len, llm_client, "dag_condense_patterns"
        )
        stats = result.get("stats", {})
        node_id = uuid4()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at)
                VALUES (?, 2, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    str(node_id),
                    week_label,
                    summary_text,
                    json.dumps(source_ids),
                    json.dumps(stats),
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()

        logger.info("Condensed %d Layer 1 nodes → Layer 2 node %s (week %s)", len(summaries), node_id, week_label)
        return node_id

    # -------------------------------------------------------------------------
    # Layer 3 — Monthly strategy synthesis (Layer 2 → Layer 3)
    # -------------------------------------------------------------------------

    async def synthesize_strategy_monthly(
        self,
        month: str,
        llm_client: LLMClient,
        concepts: BusinessConcepts,
    ) -> UUID | None:
        """Synthesize all Layer 2 weekly patterns for a month into a Layer 3 strategy narrative.

        month should be "YYYY-MM".
        Returns the new DAGNode UUID, or None if no Layer 2 nodes exist for that month.
        """
        from calendar import monthrange  # noqa: E402 — local import to avoid circular

        # Compute all ISO weeks that have at least one day in this month
        year, month_num = int(month[:4]), int(month[5:7])
        days_in_month = monthrange(year, month_num)[1]
        weeks_in_month: set[str] = set()
        for day in range(1, days_in_month + 1):
            dt = datetime(year, month_num, day)
            iso_year, iso_week, _ = dt.isocalendar()
            weeks_in_month.add(f"{iso_year}-W{iso_week:02d}")

        if not weeks_in_month:
            return None

        placeholders = ",".join("?" * len(weeks_in_month))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT * FROM dag_nodes
                WHERE depth = 2 AND period IN ({placeholders})
                ORDER BY period
                """,
                list(weeks_in_month),
            )
            rows = await cursor.fetchall()

        if not rows:
            logger.debug("No Layer 2 nodes for month %s — skipping synthesis", month)
            return None

        patterns = [dict(r) for r in rows]
        source_ids = [p["id"] for p in patterns]

        for p in patterns:
            p["stats"] = json.loads(p["stats"]) if isinstance(p["stats"], str) else p["stats"]

        prompt = render_template(
            "synthesize_strategy.j2",
            patterns=patterns,
            month=month,
            business_type=concepts.business_type or "business",
            business_description=concepts.business_description or "",
        )
        result = await llm_client.call_json(prompt, purpose="dag_synthesize_strategy")

        source_text_len = sum(len(p.get("summary_text", "")) for p in patterns)
        summary_text = await _ensure_convergence(
            result.get("summary", ""), source_text_len, llm_client, "dag_synthesize_strategy"
        )
        stats = result.get("stats", {})
        node_id = uuid4()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO dag_nodes (id, depth, trigger_id, period, summary_text, source_node_ids, stats, created_at)
                VALUES (?, 3, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    str(node_id),
                    month,
                    summary_text,
                    json.dumps(source_ids),
                    json.dumps(stats),
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()

        logger.info("Synthesized %d Layer 2 nodes → Layer 3 node %s (month %s)", len(patterns), node_id, month)
        return node_id

    # -------------------------------------------------------------------------
    # Query & drill-down
    # -------------------------------------------------------------------------

    async def grep(self, query: str, llm_client: LLMClient, limit: int = 10) -> list[DAGNode]:
        """Simple keyword search across all DAG nodes (summary_text).

        For semantic search, use LanceDB MemoryManager.recall() instead.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Split query into keywords for basic full-text matching
            words = [w.strip() for w in query.lower().split() if w.strip()]
            if not words:
                return []

            # Build LIKE conditions
            conditions = " AND ".join(["LOWER(summary_text) LIKE ?" for _ in words])
            params: list[str | int] = [f"%{w}%" for w in words]
            params.append(limit)

            cursor = await db.execute(
                f"""
                SELECT * FROM dag_nodes
                WHERE {conditions}
                ORDER BY depth DESC, created_at DESC
                LIMIT ?
                """,
                params,
            )
            rows = await cursor.fetchall()

        return [_node_from_row(r) for r in rows]

    async def expand(self, node_id: UUID) -> list[DAGNode]:
        """Expand a summary node to see its source nodes.

        For Layer 1 nodes: returns the raw Layer 0 events as synthetic DAGNodes.
        For Layer 2+ nodes: returns the Layer N-1 nodes that fed into it.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Load the node itself
            cursor = await db.execute("SELECT * FROM dag_nodes WHERE id = ?", (str(node_id),))
            row = await cursor.fetchone()

        if not row:
            logger.warning("DAG node %s not found", node_id)
            return []

        node = _node_from_row(row)
        source_ids = node.source_node_ids

        if not source_ids:
            return []

        depth = node.depth

        if depth == 1:
            # Source IDs point to dag_events rows — convert them to DAGNode-like objects
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                placeholders = ",".join("?" * len(source_ids))
                cursor = await db.execute(
                    f"SELECT * FROM dag_events WHERE id IN ({placeholders})",
                    [str(s) for s in source_ids],
                )
                event_rows = await cursor.fetchall()

            results = []
            for e in event_rows:
                results.append(
                    DAGNode(
                        id=UUID(e["id"]),
                        depth=0,
                        trigger_id=UUID(e["trigger_id"]),
                        period=e["created_at"][:10],
                        summary_text=(
                            f"[{e['channel']}] tone={e['tone'] or 'unknown'} "
                            f"delay={e['send_delay_minutes']}min "
                            f"outcome={e['outcome'] or 'pending'}"
                        ),
                        source_node_ids=[],
                        stats={
                            "channel": e["channel"],
                            "tone": e["tone"],
                            "outcome": e["outcome"],
                            "send_delay_minutes": e["send_delay_minutes"],
                            "time_to_convert_minutes": e["time_to_convert_minutes"],
                            "experiment_arm": e["experiment_arm"],
                        },
                        created_at=datetime.fromisoformat(e["created_at"]),
                    )
                )
            return results
        else:
            # Source IDs point to other dag_nodes rows
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                placeholders = ",".join("?" * len(source_ids))
                cursor = await db.execute(
                    f"SELECT * FROM dag_nodes WHERE id IN ({placeholders})",
                    [str(s) for s in source_ids],
                )
                rows = await cursor.fetchall()
            return [_node_from_row(r) for r in rows]

    async def get_composition_context(self, trigger_name: str, channel: str) -> list[DAGNode]:
        """Get relevant DAG summaries for message composition.

        Returns Layer 1 nodes for this trigger (most recent 7), filtered by channel.
        Falls back to Layer 2 nodes if no Layer 1 found.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Find trigger_ids matching trigger_name in events
            cursor = await db.execute(
                "SELECT DISTINCT trigger_id FROM dag_events WHERE trigger_name = ? AND channel = ? LIMIT 5",
                (trigger_name, channel),
            )
            trows = await cursor.fetchall()
            trigger_ids = [r["trigger_id"] for r in trows]

            if trigger_ids:
                placeholders = ",".join("?" * len(trigger_ids))
                cursor = await db.execute(
                    f"""
                    SELECT * FROM dag_nodes
                    WHERE depth = 1 AND trigger_id IN ({placeholders})
                    ORDER BY created_at DESC
                    LIMIT 7
                    """,
                    trigger_ids,
                )
                rows = await cursor.fetchall()
                if rows:
                    return [_node_from_row(r) for r in rows]

            # Fallback: return most recent Layer 2 nodes
            cursor = await db.execute(
                """
                SELECT * FROM dag_nodes
                WHERE depth = 2
                ORDER BY created_at DESC
                LIMIT 3
                """,
            )
            rows = await cursor.fetchall()
            return [_node_from_row(r) for r in rows]

    async def get_research_context(self, trigger_name: str) -> list[DAGNode]:
        """Get relevant DAG summaries for AutoResearch hypothesis generation.

        Returns Layer 1 nodes for this trigger plus Layer 2 pattern nodes.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Find trigger_ids by name
            cursor = await db.execute(
                "SELECT DISTINCT trigger_id FROM dag_events WHERE trigger_name = ? LIMIT 5",
                (trigger_name,),
            )
            trows = await cursor.fetchall()
            trigger_ids = [r["trigger_id"] for r in trows]

            results: list[DAGNode] = []

            if trigger_ids:
                placeholders = ",".join("?" * len(trigger_ids))
                cursor = await db.execute(
                    f"""
                    SELECT * FROM dag_nodes
                    WHERE depth = 1 AND trigger_id IN ({placeholders})
                    ORDER BY created_at DESC
                    LIMIT 5
                    """,
                    trigger_ids,
                )
                rows = await cursor.fetchall()
                results.extend([_node_from_row(r) for r in rows])

            # Also grab recent Layer 2 (cross-trigger patterns)
            cursor = await db.execute(
                """
                SELECT * FROM dag_nodes
                WHERE depth = 2
                ORDER BY created_at DESC
                LIMIT 3
                """,
            )
            rows = await cursor.fetchall()
            results.extend([_node_from_row(r) for r in rows])

            return results

    async def export_for_cloud(self) -> list[dict]:
        """Export anonymized Layer 2+ summaries for cloud intelligence sharing.

        NEVER exports Layer 0 (raw customer data) or Layer 1 (trigger-level data
        that may contain user-identifiable patterns). Only Layer 2+ summaries.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, depth, period, summary_text, stats, created_at
                FROM dag_nodes
                WHERE depth >= 2
                ORDER BY depth, created_at
                """
            )
            rows = await cursor.fetchall()

        return [
            {
                "id": r["id"],
                "depth": r["depth"],
                "period": r["period"],
                "summary_text": r["summary_text"],
                "stats": json.loads(r["stats"]) if isinstance(r["stats"], str) else r["stats"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
