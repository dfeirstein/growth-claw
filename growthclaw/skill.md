# GrowthClaw — AI Marketing Engine

## When to use
Use GrowthClaw MCP tools when the operator asks about:
- Marketing triggers, campaigns, or outreach
- Customer funnels, conversion rates, or metrics
- A/B experiments or AutoResearch results
- Journey logs or message history
- Memory of past patterns and learnings
- System health or status checks
- Approving, pausing, or managing triggers

## Available MCP tools
- `gc_status` — System health: DB connections, active triggers, journey counts, dry_run mode
- `gc_triggers_list` — All triggers with status, channel, delay, fire count, conversion rate
- `gc_triggers_approve` — Approve proposed triggers (pass name or 'all')
- `gc_triggers_pause` — Pause an active trigger by name
- `gc_journeys` — Recent outreach: timestamp, user, trigger, channel, message, status, outcome
- `gc_experiments` — AutoResearch cycles: hypothesis, variable, control/test results, decision
- `gc_metrics` — Key metrics: funnel stages, sends today/week, conversions, biggest dropoff
- `gc_memory_recall` — Search agent memory for past patterns, experiments, guardrails
- `gc_memory_store` — Store a new memory: pattern, guardrail, insight, preference

## How to respond
- Format metrics in markdown tables for readability
- Highlight conversion rates, trends, and comparisons
- When showing triggers, use status icons: active=green, proposed=yellow, paused=red
- Reference past AutoResearch learnings when suggesting next experiments
- When asked "what should we test next?", use gc_memory_recall to find patterns first
- Keep responses concise — operators want quick answers, not essays

## Example interactions
- "Show me today's metrics" → call gc_metrics
- "How are triggers performing?" → call gc_triggers_list
- "Pause the weekend trigger" → call gc_triggers_pause with trigger_name
- "What has AutoResearch found?" → call gc_experiments + gc_memory_recall
- "Remember: don't test on weekends" → call gc_memory_store with category='guardrail'
