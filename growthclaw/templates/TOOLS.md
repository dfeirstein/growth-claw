# GrowthClaw Tools

## MCP Tools (available via Claude Code)

### System
- `gc_status` — System health: DB connections, active triggers, event counts, dry_run mode
- `gc_llm_usage` — LLM usage stats: calls, tokens, cost by provider (last 30 days)

### Triggers
- `gc_triggers_list` — All triggers with status, channel, delay, fires, conversion rate
- `gc_triggers_approve` — Approve proposed triggers (pass name or 'all')
- `gc_triggers_pause` — Pause an active trigger by name

### Outreach
- `gc_journeys` — Recent outreach: timestamp, user, trigger, channel, message, status, outcome
- `gc_metrics` — Key metrics: funnel stages, sends today/week, conversions, biggest dropoff

### Experiments
- `gc_experiments` — AutoResearch cycles: hypothesis, variable, control/test results, decision

### Memory
- `gc_memory_recall` — Search past learnings by semantic query + category filter
- `gc_memory_store` — Save a pattern, guardrail, insight, or operator preference

## CLI Commands
- `growthclaw onboard` — Discover database schema + propose triggers
- `growthclaw migrate` — Create/update internal tables
- `growthclaw start` / `stop` — CDC listener + scheduler
- `growthclaw triggers list` / `approve` / `approve --all`
- `growthclaw status` — Health check
- `growthclaw journeys` — Recent outreach log
- `growthclaw experiments` — A/B test results
- `growthclaw dashboard` — Open Streamlit web UI
- `growthclaw daemon start [--claude]` — Start the agent
- `growthclaw daemon stop` / `status` — Manage daemon

## When to Use What
- Operator asks about metrics → `gc_metrics` or `gc_triggers_list`
- Operator asks "what should we test?" → `gc_memory_recall` then `gc_experiments`
- Operator asks to pause/approve → `gc_triggers_pause` or `gc_triggers_approve`
- Operator says "remember this" → `gc_memory_store`
- Something seems wrong → `gc_status` first
