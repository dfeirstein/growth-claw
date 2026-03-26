# Harness Architecture

## Dual-Mode Runtime

GrowthClaw runs as a unified harness (`growthclaw/harness.py`) with two concurrent modes:

### Mode 1: Python Fast Loop (always running, zero LLM cost)
- **Polling listener** — queries customer DB every 30s for new events
- **Trigger evaluation** — cooldowns, consent, quiet hours, frequency caps
- **Profile building** — gathers customer data from DB (no LLM needed)
- **Event queue** — approved events inserted into `growthclaw.event_queue`

### Mode 2: Claude Code Brain (cron-driven wake-ups)
- **Every 15 min** — process event queue: compose messages with VOICE.md context, send
- **Every 6 hours** — AutoResearch cycle: recall memory, generate hypothesis, create variants
- **Daily 2 AM** — nightly sweep: cohort analysis, dormancy detection, pattern storage
- **Weekly Sunday 3 AM** — self-hosting pass: analyze outcomes, propose prompt rewrites

## Event Flow

```
Customer DB
    ↓ (polling, every 30s)
Python Fast Loop
    ↓ (evaluate: cooldowns, consent, quiet hours, frequency caps)
    ↓ (build profile, assign AutoResearch arm)
growthclaw.event_queue (status: pending)
    ↓ (Claude Code wakes up via cron)
gc_get_pending_events → gc_get_workspace_context → compose → gc_compose_message
    ↓ (status: composed)
gc_send_message → Twilio/Resend
    ↓ (status: sent, Journey created, frequency recorded)
```

## Session Management

- First harness start initializes a Claude Code session: `claude --auto-mode -p "..." --output-format json`
- Session ID stored at `~/.growthclaw/session_id`
- All subsequent wake-ups use `claude --resume <session-id> --auto-mode -p "..."`
- Same session = shared context (SOUL.md, VOICE.md, memory) across all wake-ups
- If Claude Code CLI unavailable, harness logs warning and skips wake-ups (Python loop continues)

## Event Queue Table (migration 006)

```sql
growthclaw.event_queue:
  id, user_id, trigger_id, event_id, channel, contact_value,
  profile_data (JSONB), intelligence (JSONB),
  ar_cycle_id, ar_arm,
  status (pending|composing|composed|sent|failed),
  message_body, message_subject, provider_id,
  created_at, composed_at, sent_at
```

## Standalone Fallback

When `STANDALONE_MODE=true` in config, the old `main.py` engine handles everything:
- Direct LLM API calls for composition (requires NVIDIA/Anthropic API key)
- APScheduler runs AutoResearch and outcome checking in-process
- No Claude Code dependency

The harness and standalone paths coexist — no code was removed.

## Config Flags

```
STANDALONE_MODE=false     # false=harness (default), true=standalone
EVENT_MODE=poll           # poll|cdc|wal
POLL_INTERVAL_SECONDS=30
```

## Per-Task Model Routing (anthropic_fallback.py)

Creative tasks → Opus 4.6 (`claude-opus-4-6`):
- compose_sms, compose_email, compose_sms_retry
- nightly_sweep, hypothesis_generation, variant_creation, prompt_optimization

Analytical tasks → Sonnet 4.6 (`claude-sonnet-4-6`):
- schema_classification, funnel_analysis, trigger_proposal
- profile_analysis, experiment_evaluation
- All JSON fix retries

Purpose strings are passed through: caller → `LLMClient.call(purpose=)` → `AnthropicProvider.call(purpose=)` → `model_for_purpose()`.
