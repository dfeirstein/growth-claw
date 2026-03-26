"""GrowthClaw MCP Server — exposes GrowthClaw operations as MCP tools for Claude Code."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

import asyncpg

from growthclaw.config import get_settings

logger = logging.getLogger("growthclaw.mcp_server")

# MCP protocol constants
JSONRPC_VERSION = "2.0"


def _json_serial(obj: Any) -> str:
    """JSON serializer for objects not serializable by default."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__str__"):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


# ─── Tool Definitions ───────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "gc_status",
        "description": "Check GrowthClaw system health: DB connections, active triggers, recent events, journey counts",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "gc_triggers_list",
        "description": "List all triggers with status, channel, delay, fire count, and conversion rate",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "gc_triggers_approve",
        "description": "Approve proposed triggers. Pass trigger_name to approve one, or 'all' to approve all.",
        "inputSchema": {
            "type": "object",
            "properties": {"trigger_name": {"type": "string", "description": "Trigger name or 'all'"}},
            "required": ["trigger_name"],
        },
    },
    {
        "name": "gc_triggers_pause",
        "description": "Pause an active trigger by name",
        "inputSchema": {
            "type": "object",
            "properties": {"trigger_name": {"type": "string"}},
            "required": ["trigger_name"],
        },
    },
    {
        "name": "gc_journeys",
        "description": "Show recent outreach journeys with status, channel, message preview, and outcomes",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max results (default 20)"}},
            "required": [],
        },
    },
    {
        "name": "gc_experiments",
        "description": "Show AutoResearch experiment cycle results",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "gc_metrics",
        "description": "Get key dashboard metrics: funnel stages, conversion rates, sends today/this week",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "gc_memory_recall",
        "description": "Search agent memory for past experiments, patterns, and learnings",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Semantic search query"},
                "category": {
                    "type": "string",
                    "description": "Filter by category: pattern, guardrail, hypothesis, outcome, preference",
                },
                "limit": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "gc_memory_store",
        "description": "Store a new memory: pattern, guardrail, insight, or operator preference",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The memory content to store"},
                "category": {
                    "type": "string",
                    "description": "Category: pattern, guardrail, hypothesis, outcome, preference, insight",
                },
                "importance": {"type": "number", "description": "Importance score 0-1 (default 0.7)"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags"},
            },
            "required": ["text", "category"],
        },
    },
    {
        "name": "gc_llm_usage",
        "description": "Show LLM usage stats: calls, tokens, and estimated costs by provider (last 30 days)",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "gc_get_pending_events",
        "description": "Get pending events from event_queue ready for message composition, with trigger context",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max events to return (default 20)"}},
            "required": [],
        },
    },
    {
        "name": "gc_compose_message",
        "description": "Update an event_queue entry with a composed message body (and optional subject for email)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_queue_id": {"type": "string", "description": "UUID of the event_queue entry"},
                "message_body": {"type": "string", "description": "Composed message body (SMS text or email HTML)"},
                "message_subject": {"type": "string", "description": "Email subject line (optional, email only)"},
            },
            "required": ["event_queue_id", "message_body"],
        },
    },
    {
        "name": "gc_send_message",
        "description": "Send a composed message via the appropriate channel (Twilio SMS or email). Checks DRY_RUN.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_queue_id": {"type": "string", "description": "UUID of the event_queue entry to send"},
            },
            "required": ["event_queue_id"],
        },
    },
    {
        "name": "gc_get_workspace_context",
        "description": "Get workspace context files (VOICE.md, SOUL.md, BUSINESS.md, etc.) for message composition",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Specific file name (e.g. 'VOICE.md') or 'all' for everything",
                },
            },
            "required": ["file"],
        },
    },
]


# ─── Tool Handlers ───────────────────────────────────────────────────────────


async def _get_conn() -> asyncpg.Connection:  # type: ignore[type-arg]
    settings = get_settings()
    return await asyncpg.connect(dsn=settings.growthclaw_database_url)


async def handle_gc_status(args: dict) -> str:
    settings = get_settings()
    results = {}

    # Check internal DB
    try:
        conn = await _get_conn()
        results["trigger_count"] = await conn.fetchval(
            "SELECT COUNT(*) FROM growthclaw.triggers WHERE status IN ('active', 'approved')"
        )
        results["proposed_triggers"] = await conn.fetchval(
            "SELECT COUNT(*) FROM growthclaw.triggers WHERE status = 'proposed'"
        )
        results["unprocessed_events"] = await conn.fetchval(
            "SELECT COUNT(*) FROM growthclaw.events WHERE processed = FALSE"
        )
        results["total_journeys"] = await conn.fetchval("SELECT COUNT(*) FROM growthclaw.journeys")
        results["journeys_today"] = await conn.fetchval(
            "SELECT COUNT(*) FROM growthclaw.journeys WHERE created_at >= CURRENT_DATE"
        )
        results["conversions_today"] = await conn.fetchval(
            "SELECT COUNT(*) FROM growthclaw.journeys WHERE outcome = 'converted' AND outcome_at >= CURRENT_DATE"
        )
        results["internal_db"] = "connected"
        await conn.close()
    except Exception as e:
        results["internal_db"] = f"error: {e}"

    # Check customer DB
    try:
        conn = await asyncpg.connect(dsn=settings.customer_database_url)
        table_count = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        results["customer_db"] = f"connected ({table_count} tables)"
        await conn.close()
    except Exception as e:
        results["customer_db"] = f"error: {e}"

    results["dry_run"] = settings.dry_run
    return json.dumps(results, indent=2, default=_json_serial)


async def handle_gc_triggers_list(args: dict) -> str:
    conn = await _get_conn()
    try:
        rows = await conn.fetch("""
            SELECT t.name, t.status, t.channel, t.delay_minutes, t.description,
                   COUNT(j.id) as total_fires,
                   COUNT(j.id) FILTER (WHERE j.outcome = 'converted') as conversions
            FROM growthclaw.triggers t
            LEFT JOIN growthclaw.journeys j ON j.trigger_id = t.id AND j.status = 'sent'
            GROUP BY t.id, t.name, t.status, t.channel, t.delay_minutes, t.description
            ORDER BY total_fires DESC
        """)
        triggers = []
        for r in rows:
            fires = r["total_fires"] or 0
            convs = r["conversions"] or 0
            rate = f"{convs / fires * 100:.1f}%" if fires > 0 else "N/A"
            triggers.append(
                {
                    "name": r["name"],
                    "status": r["status"],
                    "channel": r["channel"],
                    "delay_minutes": r["delay_minutes"],
                    "description": r["description"],
                    "fires": fires,
                    "conversions": convs,
                    "conversion_rate": rate,
                }
            )
        return json.dumps(triggers, indent=2)
    finally:
        await conn.close()


async def handle_gc_triggers_approve(args: dict) -> str:
    name = args.get("trigger_name", "all")
    conn = await _get_conn()
    try:
        if name == "all":
            result = await conn.execute("UPDATE growthclaw.triggers SET status = 'approved' WHERE status = 'proposed'")
            count = int(result.split()[-1]) if result else 0
            return f"Approved {count} triggers."
        else:
            result = await conn.execute(
                "UPDATE growthclaw.triggers SET status = 'approved' WHERE name = $1 AND status = 'proposed'", name
            )
            count = int(result.split()[-1]) if result else 0
            return f"Approved trigger '{name}'." if count > 0 else f"No proposed trigger named '{name}' found."
    finally:
        await conn.close()


async def handle_gc_triggers_pause(args: dict) -> str:
    name = args["trigger_name"]
    conn = await _get_conn()
    try:
        result = await conn.execute(
            "UPDATE growthclaw.triggers SET status = 'paused' WHERE name = $1 AND status IN ('active', 'approved')",
            name,
        )
        count = int(result.split()[-1]) if result else 0
        return f"Paused trigger '{name}'." if count > 0 else f"No active trigger named '{name}' found."
    finally:
        await conn.close()


async def handle_gc_journeys(args: dict) -> str:
    limit = args.get("limit", 20)
    conn = await _get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT j.created_at, j.user_id, t.name as trigger_name, j.channel,
                   LEFT(j.message_body, 80) as message_preview, j.status, j.outcome, j.sent_at
            FROM growthclaw.journeys j
            JOIN growthclaw.triggers t ON t.id = j.trigger_id
            ORDER BY j.created_at DESC LIMIT $1
            """,
            limit,
        )
        journeys = [dict(r) for r in rows]
        return json.dumps(journeys, indent=2, default=_json_serial)
    finally:
        await conn.close()


async def handle_gc_experiments(args: dict) -> str:
    conn = await _get_conn()
    try:
        rows = await conn.fetch("""
            SELECT ac.cycle_number, t.name as trigger_name, ac.hypothesis, ac.variable,
                   ac.control_sends, ac.control_conversions, ac.test_sends, ac.test_conversions,
                   ac.status, ac.decision, ac.uplift_pct, ac.reasoning, ac.started_at, ac.completed_at
            FROM growthclaw.autoresearch_cycles ac
            JOIN growthclaw.triggers t ON t.id = ac.trigger_id
            ORDER BY ac.started_at DESC LIMIT 20
        """)
        experiments = [dict(r) for r in rows]
        return json.dumps(experiments, indent=2, default=_json_serial)
    finally:
        await conn.close()


async def handle_gc_metrics(args: dict) -> str:
    conn = await _get_conn()
    try:
        # Get funnel data
        funnel_row = await conn.fetchrow(
            "SELECT business_name, business_type, funnel, concepts"
            " FROM growthclaw.schema_map ORDER BY discovered_at DESC LIMIT 1"
        )
        # Get send stats
        sends_today = await conn.fetchval(
            "SELECT COUNT(*) FROM growthclaw.journeys WHERE sent_at >= CURRENT_DATE AND status = 'sent'"
        )
        sends_week = await conn.fetchval(
            "SELECT COUNT(*) FROM growthclaw.journeys"
            " WHERE sent_at >= CURRENT_DATE - INTERVAL '7 days' AND status = 'sent'"
        )
        convs_today = await conn.fetchval(
            "SELECT COUNT(*) FROM growthclaw.journeys WHERE outcome = 'converted' AND outcome_at >= CURRENT_DATE"
        )
        convs_week = await conn.fetchval(
            "SELECT COUNT(*) FROM growthclaw.journeys"
            " WHERE outcome = 'converted' AND outcome_at >= CURRENT_DATE - INTERVAL '7 days'"
        )

        metrics: dict[str, Any] = {
            "sends_today": sends_today or 0,
            "sends_this_week": sends_week or 0,
            "conversions_today": convs_today or 0,
            "conversions_this_week": convs_week or 0,
        }

        if funnel_row:
            funnel = (
                funnel_row["funnel"] if isinstance(funnel_row["funnel"], dict) else json.loads(funnel_row["funnel"])
            )
            stages = funnel.get("funnel_stages") or funnel.get("stages", [])
            metrics["business"] = funnel_row["business_name"] or funnel_row["business_type"]
            metrics["funnel_stages"] = [{"name": s["name"], "count": s.get("count", 0)} for s in stages]
            dropoff = funnel.get("biggest_dropoff")
            if dropoff:
                metrics["biggest_dropoff"] = dropoff.get("description", "")

        return json.dumps(metrics, indent=2, default=_json_serial)
    finally:
        await conn.close()


async def handle_gc_memory_recall(args: dict) -> str:
    try:
        from growthclaw.memory.manager import MemoryManager

        mgr = MemoryManager()
        await mgr.initialize()
        results = await mgr.recall(
            query=args["query"],
            category=args.get("category"),
            limit=args.get("limit", 5),
        )
        return json.dumps(
            [r.model_dump(mode="json", exclude={"vector"}) for r in results], indent=2, default=_json_serial
        )
    except ImportError:
        return json.dumps({"error": "Memory system not initialized. Install lancedb: pip install lancedb"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_gc_memory_store(args: dict) -> str:
    try:
        from growthclaw.memory.manager import MemoryManager

        mgr = MemoryManager()
        await mgr.initialize()
        entry_id = await mgr.store(
            text=args["text"],
            category=args["category"],
            importance=args.get("importance", 0.7),
            tags=args.get("tags", []),
        )
        return json.dumps({"stored": True, "id": str(entry_id)})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_gc_llm_usage(args: dict) -> str:
    conn = await _get_conn()
    try:
        from growthclaw.llm.usage_tracker import get_usage_summary

        summary = await get_usage_summary(conn)
        return json.dumps(summary, indent=2, default=_json_serial)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_gc_get_pending_events(args: dict) -> str:
    limit = args.get("limit", 20)
    conn = await _get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT eq.id, eq.user_id, eq.trigger_id, eq.contact_value, eq.channel,
                   eq.profile_data, eq.intelligence, eq.ar_cycle_id, eq.ar_arm,
                   eq.status, eq.created_at,
                   t.name as trigger_name, t.description as trigger_description,
                   t.message_context, t.channel as trigger_channel
            FROM growthclaw.event_queue eq
            JOIN growthclaw.triggers t ON t.id = eq.trigger_id
            WHERE eq.status = 'pending'
            ORDER BY eq.created_at
            LIMIT $1
            """,
            limit,
        )
        events = []
        for r in rows:
            event = dict(r)
            # Parse JSONB fields if they are strings
            for field in ("profile_data", "intelligence", "message_context"):
                if field in event and isinstance(event[field], str):
                    try:
                        event[field] = json.loads(event[field])
                    except (json.JSONDecodeError, TypeError):
                        pass
            events.append(event)
        return json.dumps(events, indent=2, default=_json_serial)
    finally:
        await conn.close()


async def handle_gc_compose_message(args: dict) -> str:
    event_queue_id = args["event_queue_id"]
    message_body = args["message_body"]
    message_subject = args.get("message_subject")
    conn = await _get_conn()
    try:
        result = await conn.execute(
            """
            UPDATE growthclaw.event_queue
            SET message_body = $1, message_subject = $2, status = 'composed', composed_at = NOW()
            WHERE id = $3
            """,
            message_body,
            message_subject,
            event_queue_id,
        )
        count = int(result.split()[-1]) if result else 0
        if count > 0:
            return json.dumps({"status": "composed", "event_queue_id": event_queue_id})
        else:
            return json.dumps({"error": f"No pending event_queue entry found with id {event_queue_id}"})
    finally:
        await conn.close()


async def handle_gc_send_message(args: dict) -> str:
    from datetime import UTC, datetime
    from uuid import uuid4

    from growthclaw.models.journey import Journey
    from growthclaw.outreach.email_sender import EmailSender
    from growthclaw.outreach.sms_sender import SMSSender

    event_queue_id = args["event_queue_id"]
    settings = get_settings()
    conn = await _get_conn()
    try:
        # Fetch the event_queue entry
        row = await conn.fetchrow(
            """
            SELECT eq.*, t.name as trigger_name, t.channel as trigger_channel
            FROM growthclaw.event_queue eq
            JOIN growthclaw.triggers t ON t.id = eq.trigger_id
            WHERE eq.id = $1
            """,
            event_queue_id,
        )
        if not row:
            return json.dumps({"error": f"No event_queue entry found with id {event_queue_id}"})

        if row["status"] != "composed":
            return json.dumps({"error": f"Event is not composed (status={row['status']}). Compose first."})

        channel = row["channel"] or row["trigger_channel"]
        contact_value = row["contact_value"]
        message_body = row["message_body"]
        message_subject = row.get("message_subject")
        provider_id = None

        # Send via appropriate channel (respects DRY_RUN internally)
        try:
            if channel == "sms":
                sender = SMSSender(settings)
                provider_id = await sender.send(to=contact_value, body=message_body)
            elif channel == "email":
                email_sender = EmailSender(settings)
                provider_id = await email_sender.send(
                    to_email=contact_value,
                    subject=message_subject or "",
                    html_body=message_body,
                )
            else:
                return json.dumps({"error": f"Unknown channel: {channel}"})
        except Exception as e:
            # Mark as failed
            await conn.execute(
                "UPDATE growthclaw.event_queue SET status = 'failed' WHERE id = $1",
                event_queue_id,
            )
            return json.dumps({"status": "failed", "error": str(e)})

        # Update event_queue status to sent
        await conn.execute(
            "UPDATE growthclaw.event_queue SET status = 'sent', provider_id = $1, sent_at = NOW() WHERE id = $2",
            provider_id,
            event_queue_id,
        )

        # Create a Journey record
        journey = Journey(
            id=uuid4(),
            user_id=row["user_id"],
            trigger_id=row["trigger_id"],
            event_id=row.get("event_id"),
            channel=channel,
            contact_info=contact_value,
            message_body=message_body,
            provider_id=provider_id,
            status="sent",
            created_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
        )
        from growthclaw.outreach.journey_store import create as create_journey

        await create_journey(conn, journey)

        # Record in global_frequency
        await conn.execute(
            """
            INSERT INTO growthclaw.global_frequency (user_id, channel, sent_at)
            VALUES ($1, $2, NOW())
            """,
            row["user_id"],
            channel,
        )

        return json.dumps(
            {
                "status": "sent",
                "provider_id": provider_id,
                "journey_id": str(journey.id),
                "dry_run": settings.dry_run,
            },
            indent=2,
            default=_json_serial,
        )
    finally:
        await conn.close()


async def handle_gc_get_workspace_context(args: dict) -> str:
    from growthclaw.workspace_context import WorkspaceContext

    filename = args.get("file", "all")
    ctx = WorkspaceContext()
    if filename == "all":
        result = ctx.get_all()
        return json.dumps(result, indent=2, default=_json_serial)
    else:
        content = ctx.get(filename)
        if content is None:
            return json.dumps({"error": f"File '{filename}' not found in workspace"})
        return json.dumps({filename: content}, indent=2, default=_json_serial)


# ─── Tool Dispatch ───────────────────────────────────────────────────────────

TOOL_HANDLERS = {
    "gc_status": handle_gc_status,
    "gc_triggers_list": handle_gc_triggers_list,
    "gc_triggers_approve": handle_gc_triggers_approve,
    "gc_triggers_pause": handle_gc_triggers_pause,
    "gc_journeys": handle_gc_journeys,
    "gc_experiments": handle_gc_experiments,
    "gc_metrics": handle_gc_metrics,
    "gc_memory_recall": handle_gc_memory_recall,
    "gc_memory_store": handle_gc_memory_store,
    "gc_llm_usage": handle_gc_llm_usage,
    "gc_get_pending_events": handle_gc_get_pending_events,
    "gc_compose_message": handle_gc_compose_message,
    "gc_send_message": handle_gc_send_message,
    "gc_get_workspace_context": handle_gc_get_workspace_context,
}


# ─── MCP Protocol (stdio JSON-RPC) ──────────────────────────────────────────


async def handle_request(request: dict) -> dict:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "growthclaw", "version": "0.2.0"},
            },
        }

    if method == "notifications/initialized":
        return {}  # No response needed for notifications

    if method == "tools/list":
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)

        if not handler:
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}], "isError": True},
            }

        try:
            result_text = await handler(tool_args)
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "result": {"content": [{"type": "text", "text": result_text}]},
            }
        except Exception as e:
            logger.exception("Tool %s failed", tool_name)
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True},
            }

    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


async def main() -> None:
    """Run the MCP server on stdio (JSON-RPC over stdin/stdout)."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    logger.info("GrowthClaw MCP server starting on stdio...")

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

    while True:
        try:
            line = await reader.readline()
            if not line:
                break
            request = json.loads(line.decode().strip())
            response = await handle_request(request)
            if response:  # Don't send empty responses for notifications
                response_bytes = (json.dumps(response) + "\n").encode()
                writer.write(response_bytes)
                await writer.drain()
        except json.JSONDecodeError:
            continue
        except Exception as e:
            logger.exception("MCP server error: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
