# MCP Tools Reference

GrowthClaw exposes 14 MCP tools in the `gc_*` namespace via `growthclaw/mcp_server.py`.
Claude Code accesses these when running in the `~/.growthclaw/` workspace.

## Tool List

### System
| Tool | Description |
|------|-------------|
| `gc_status` | Health check: DB connections, active triggers, events, journeys |
| `gc_llm_usage` | LLM usage stats by provider (last 30 days) |
| `gc_get_workspace_context` | Read workspace .md files (VOICE, SOUL, BUSINESS, etc.) |

### Triggers
| Tool | Description |
|------|-------------|
| `gc_triggers_list` | All triggers with status, channel, fires, conversion rate |
| `gc_triggers_approve` | Approve proposed triggers (one or all) |
| `gc_triggers_pause` | Pause an active trigger |

### Outreach Pipeline (harness mode)
| Tool | Description |
|------|-------------|
| `gc_get_pending_events` | Fetch pending events from event_queue with trigger context |
| `gc_compose_message` | Save composed message body/subject to event_queue |
| `gc_send_message` | Send composed message via Twilio/Resend, create Journey |

### Data & Intelligence
| Tool | Description |
|------|-------------|
| `gc_journeys` | Recent outreach log with outcomes |
| `gc_experiments` | AutoResearch cycle results |
| `gc_metrics` | Dashboard metrics: funnel, sends, conversions |
| `gc_memory_recall` | Semantic search of agent memory |
| `gc_memory_store` | Store new memory (pattern, guardrail, insight) |

## Harness Composition Flow

Claude Code processes events on a 15-minute cron cycle:

```
1. gc_get_pending_events(limit=20)
   → Returns: [{id, user_id, contact_value, channel, profile_data,
                 trigger_name, trigger_description, message_context}]

2. gc_get_workspace_context(file="VOICE.md")
   → Returns: VOICE.md content (tone, style, brand guidelines)

3. For each event, compose a message following VOICE.md:
   gc_compose_message(event_queue_id=..., message_body=..., message_subject=...)
   → Updates: status pending→composed

4. gc_send_message(event_queue_id=...)
   → Sends via Twilio (SMS) or Resend (email)
   → Creates Journey record in growthclaw.journeys
   → Records send in growthclaw.global_frequency
   → Updates: status composed→sent
```

## Input Schemas

### gc_get_pending_events
```json
{"limit": 20}  // optional, default 20
```

### gc_compose_message
```json
{
  "event_queue_id": "uuid-string",     // required
  "message_body": "Hello {{name}}...", // required
  "message_subject": "Subject line"    // optional, email only
}
```

### gc_send_message
```json
{
  "event_queue_id": "uuid-string"  // required, must be status=composed
}
```

### gc_get_workspace_context
```json
{"file": "VOICE.md"}  // or "all" for everything
```

### gc_memory_recall
```json
{
  "query": "what tone works best",      // required
  "category": "pattern",                 // optional filter
  "limit": 5                             // optional, default 5
}
```

### gc_memory_store
```json
{
  "text": "Casual tone converts 23% better for driver_service",
  "category": "pattern",        // pattern|guardrail|hypothesis|outcome|preference|insight
  "importance": 0.8,            // optional, 0-1
  "tags": ["tone", "conversion"] // optional
}
```

## MCP Server Configuration

The MCP server is configured in `~/.growthclaw/.mcp.json`:
```json
{
  "mcpServers": {
    "growthclaw": {
      "command": "python3",
      "args": ["-m", "growthclaw.mcp_server"],
      "cwd": "~/.growthclaw/"
    }
  }
}
```

Runs on stdio (JSON-RPC). Protocol version: 2024-11-05.
