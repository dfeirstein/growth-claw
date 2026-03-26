# AutoGrow V1 — The Growth Compiler
## Full E2E Product Specification

**Branch:** `v1-autogrow-compiler`
**Goal:** Take GrowthClaw from Phase 1 (discovery + single-trigger SMS) to a fully functioning, deployable product that can run on Jeevz in production and onboard managed customers.

---

## Part 1: Architecture Changes

### 1.1 Polling Listener (DEFAULT — replaces CDC as primary)

**File:** `growthclaw/triggers/polling_listener.py` (NEW)

The current CDC listener requires installing pg_notify triggers on the customer's database (write access). This is a deployment blocker for most customers.

**Polling listener spec:**
- Configurable interval (default: 30 seconds)
- Tracks high-water mark (last seen timestamp) per watched table in internal DB
- Queries: `SELECT * FROM "{table}" WHERE "{timestamp_col}" > $1 ORDER BY "{timestamp_col}" LIMIT 100`
- Emits the same `TriggerEvent` objects as the CDC listener — the rest of the pipeline doesn't know the difference
- Automatic reconnection with exponential backoff (same pattern as CDC listener)
- Stores watermarks in `growthclaw.polling_watermarks` table

**Config:**
```python
# config.py additions
event_mode: str = "poll"  # "poll" | "cdc" | "wal"
poll_interval_seconds: int = 30
```

**Changes to main.py:**
- `start()` checks `event_mode` and instantiates either `PollingListener`, `CDCListener`, or `WALListener`
- All three implement the same interface: `start()`, `stop()`, `on_event` callback

**Migration:** `migrations/004_polling_watermarks.sql`
```sql
CREATE TABLE IF NOT EXISTS growthclaw.polling_watermarks (
    table_name TEXT PRIMARY KEY,
    trigger_id UUID REFERENCES growthclaw.triggers(id),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 1.2 WAL Logical Replication Listener (RECOMMENDED tier)

**File:** `growthclaw/triggers/wal_listener.py` (NEW)

For customers with `wal_level=logical` enabled (most managed Postgres: RDS, Supabase, Neon, Cloud SQL).

**Spec:**
- Uses `psycopg2` or `asyncpg` logical replication protocol
- Creates a replication slot: `growthclaw_slot`
- Uses `wal2json` output plugin (standard on managed Postgres)
- Consumes WAL stream, filters for watched tables, emits `TriggerEvent`
- Zero load on customer DB (reading WAL the DB is already writing)
- Real-time (millisecond latency)
- Read-only — no schema modifications needed

**Onboarding auto-detection:**
```python
# In onboard(), after connecting:
wal_level = await conn.fetchval("SHOW wal_level")
if wal_level == 'logical':
    print("  ✅ wal_level = logical (real-time streaming available!)")
    # Prompt user or auto-select WAL mode
else:
    print("  ⚠️  wal_level = replica (falling back to polling mode)")
```

**Requirements on customer side:**
```sql
-- Customer runs once:
ALTER SYSTEM SET wal_level = logical;  -- requires restart
-- Then:
CREATE PUBLICATION growthclaw_pub FOR TABLE users, bookings;  -- only watched tables
```

### 1.3 Event Source Interface

**File:** `growthclaw/triggers/event_source.py` (NEW)

Abstract base class that all three listeners implement:

```python
from abc import ABC, abstractmethod
from growthclaw.triggers.cdc_listener import EventCallback

class EventSource(ABC):
    @abstractmethod
    async def start(self) -> None: ...
    
    @abstractmethod
    async def stop(self) -> None: ...
    
    @property
    @abstractmethod
    def mode(self) -> str: ...  # "poll" | "cdc" | "wal"
```

All three listeners (`PollingListener`, `CDCListener`, `WALListener`) implement this interface. `main.py` instantiates based on config.

---

## Part 2: AutoResearch Integration

### 2.1 Wire AutoResearch into Main Engine

The AutoResearch loop (`autoresearch/loop.py`) exists but isn't connected to the main engine's scheduler.

**Changes to main.py `start()`:**
```python
# After starting the event listener, schedule AutoResearch
from growthclaw.autoresearch.loop import AutoResearchLoop

self.autoresearch = AutoResearchLoop(self.llm_client, self.settings)

# Run AutoResearch cycle every 6 hours for each active trigger
self.scheduler.add_job(
    self._run_autoresearch,
    "interval",
    hours=6,
    id="autoresearch_loop",
)
```

```python
async def _run_autoresearch(self) -> None:
    """Run one AutoResearch cycle for each active trigger."""
    async with self.internal_pool.acquire() as conn:
        triggers = await trigger_store.get_active(conn)
    for trigger in triggers:
        try:
            result = await self.autoresearch.run_cycle(trigger.id, conn)
            logger.info("AutoResearch: trigger=%s action=%s", trigger.name, result["action"])
        except Exception as e:
            logger.error("AutoResearch failed for %s: %s", trigger.name, e)
```

### 2.2 AutoResearch Variant Assignment in Pipeline

**Changes to `_delayed_evaluate()` in main.py:**

Currently the experiment system only tests delay timing (3 arms). AutoResearch tests message content (control vs test template). Wire this in:

```python
# After building the customer profile and before composing the message:
async with self.internal_pool.acquire() as iconn:
    running_cycle = await self.autoresearch._get_running_cycle(trigger.id, iconn)

if running_cycle:
    # Assign to control or test based on user_id hash
    import hashlib
    hash_val = int(hashlib.md5(f"{event.user_id}{running_cycle['id']}".encode()).hexdigest(), 16)
    is_test = hash_val % 2 == 1
    
    template = running_cycle["test_template"] if is_test else running_cycle["control_template"]
    arm_name = "test" if is_test else "control"
    
    # Use the template to override the default message composition
    # (compose with template context injected)
```

### 2.3 Nightly Strategic Sweep

**File:** `growthclaw/intelligence/nightly_sweep.py` (NEW)

Runs once per night (2 AM local time). Scans the database for patterns, proposes new triggers, updates memory.

```python
async def run_nightly_sweep(
    customer_conn: asyncpg.Connection,
    internal_conn: asyncpg.Connection,
    concepts: BusinessConcepts,
    llm_client: LLMClient,
    memory: MemoryManager,
) -> dict:
    """Run the nightly strategic intelligence sweep."""
    
    # 1. SCAN — cohort analysis, timing patterns, dormancy detection
    cohort_data = await _analyze_cohorts(customer_conn, concepts)
    timing_data = await _analyze_timing_patterns(customer_conn, concepts)
    dormant_users = await _detect_dormancy(customer_conn, concepts)
    whale_patterns = await _identify_whale_patterns(customer_conn, concepts)
    
    # 2. COMPARE — check against semantic memory
    past_insights = await memory.recall(query="nightly sweep findings", category="insight", limit=10)
    
    # 3. PROPOSE — LLM generates new trigger proposals or strategy adjustments
    prompt = render_template("nightly_sweep.j2", 
        cohort_data=cohort_data,
        timing_data=timing_data, 
        dormant_count=len(dormant_users),
        whale_patterns=whale_patterns,
        past_insights=[m.text for m in past_insights],
        existing_triggers=...,  # current active triggers
    )
    proposals = await llm_client.call_json(prompt, temperature=0.3)
    
    # 4. LEARN — store findings in memory
    for finding in proposals.get("findings", []):
        await memory.store(
            text=finding["description"],
            category="insight",
            importance=finding.get("importance", 0.7),
            tags=["nightly_sweep", finding.get("type", "general")],
        )
    
    return proposals
```

**New prompt template:** `prompts/nightly_sweep.j2`

**Scheduler in main.py:**
```python
self.scheduler.add_job(
    self._nightly_sweep,
    "cron",
    hour=2,
    id="nightly_sweep",
)
```

---

## Part 3: Self-Hosting Compiler Pass

### 3.1 Prompt Template Optimizer

**File:** `growthclaw/autoresearch/prompt_optimizer.py` (NEW)

The "self-hosting" pass: LLM analyzes which prompt templates produced the best outcomes and rewrites them.

```python
async def optimize_prompts(
    internal_conn: asyncpg.Connection,
    llm_client: LLMClient,
    memory: MemoryManager,
) -> dict:
    """Analyze prompt template performance and propose rewrites."""
    
    # 1. Get all journeys with outcomes, grouped by trigger
    journeys = await internal_conn.fetch("""
        SELECT j.trigger_id, j.message_body, j.channel, j.outcome,
               t.name as trigger_name, t.message_context
        FROM growthclaw.journeys j
        JOIN growthclaw.triggers t ON t.id = j.trigger_id
        WHERE j.outcome IS NOT NULL
        AND j.created_at > NOW() - INTERVAL '30 days'
        ORDER BY j.trigger_id, j.outcome
    """)
    
    # 2. Group by trigger, compute conversion rates per message pattern
    # 3. Ask LLM to identify what makes winning messages different
    # 4. Ask LLM to rewrite the prompt template to bias toward winning patterns
    # 5. Save new template as a variant for AutoResearch to test
    
    prompt = render_template("optimize_prompts.j2",
        trigger_results=grouped_results,
        current_templates=current_templates,
        memory_patterns=[m.text for m in await memory.recall("validated patterns", limit=10)],
    )
    
    optimized = await llm_client.call_json(prompt, temperature=0.2)
    return optimized
```

**Schedule:** Runs weekly (Sunday 3 AM), after enough data accumulates.

**New prompt template:** `prompts/optimize_prompts.j2`

---

## Part 4: Email Channel Hardening

### 4.1 Resend as Default (already partially built)

The email sender exists (`outreach/email_sender.py`) but needs:

- **Unsubscribe link injection:** Every email must include a one-click unsubscribe link (CAN-SPAM)
- **Suppression list management:** Track unsubscribes, bounces, complaints in `growthclaw.suppressions` table
- **Webhook handler for Resend events:** Bounce, complaint, unsubscribe events from Resend webhook

**Migration:** `migrations/005_suppressions.sql`
```sql
CREATE TABLE IF NOT EXISTS growthclaw.suppressions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL,  -- 'email' or 'sms'
    reason TEXT NOT NULL,   -- 'unsubscribe', 'bounce', 'complaint'
    provider_event_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, channel)
);
```

**Changes to email_sender.py:**
- Auto-append unsubscribe link to every email HTML body
- Check suppressions table before sending (already partially done in `_delayed_evaluate`)

**New file:** `growthclaw/outreach/webhook_handler.py`
- Simple HTTP endpoint that receives Resend/SendGrid webhook events
- Inserts into suppressions table on bounce/complaint/unsubscribe

### 4.2 Email Template Improvements

**Changes to `prompts/compose_email.j2`:**
- Add instruction to include unsubscribe text at bottom
- Add instruction to keep subject line under 60 chars
- Add instruction for preheader text
- Add responsive HTML email best practices (inline CSS, table-based layout)

---

## Part 5: CLI & Rebrand

### 5.1 Rename CLI

**Changes to `pyproject.toml`:**
```toml
[project]
name = "autogrow"

[project.scripts]
autogrow = "growthclaw.cli:main"
# Keep backward compat:
growthclaw = "growthclaw.cli:main"
```

### 5.2 CLI Additions

**New commands:**
```
autogrow research          # Show AutoResearch status and latest cycle results
autogrow sweep             # Manually trigger nightly sweep
autogrow intelligence      # Show memory contents (top insights, patterns, guardrails)
autogrow health            # Extended health check: DB connectivity, event source, triggers, experiments
```

### 5.3 Updated Onboarding Output

Update the `onboard()` method to include event source auto-detection:

```
🐾 AutoGrow — Connecting to your database...

[1/7] Scanning database schema...
  Found 66 tables, 962 columns

[2/7] Detecting event source capabilities...
  ✅ wal_level = logical (real-time streaming available!)
  Using: WAL streaming (zero DB load, millisecond latency)

[3/7] Sampling data distributions...
  Sampled 56 tables with data

[4/7] Understanding your business...
  Business type: driver_service
  Customer table: users
  Activation event: Customer completes their first ride booking

[5/7] Analyzing customer funnel...
  Funnel stages: Registration -> Activation -> First Payment -> Subscription
  Biggest drop-off: 81.7% of registered customers never complete their first ride

[6/7] Proposing growth triggers...
  1. [SMS] registration_immediate_booking_nudge (5min delay, ~1500/week)
  2. [EMAIL] registration_24hour_email_sequence (24h delay, ~1200/week)
  3. [SMS] incomplete_booking_recovery (30min delay, ~200/week)
  4. [EMAIL] payment_method_activation_blocker (2h delay, ~150/week)
  5. [SMS] weekend_activation_opportunity (7d delay, ~300/week)

[7/7] Saving configuration...
  Business profile written to: ~/.autogrow/BUSINESS.md

✅ AutoGrow discovery complete!

  Compilation passes initialized:
  ├── PASS 1 (Parse)      ✅ Schema scanned
  ├── PASS 2 (Understand) ✅ Business concepts mapped
  ├── PASS 3 (Model)      ✅ Funnel analyzed
  ├── PASS 4 (Compile)    ✅ 5 triggers proposed
  ├── PASS 5 (Optimize)   ⏳ Starts after first sends
  └── PASS 6 (Self-Host)  ⏳ Starts after 30 days of data
```

---

## Part 6: Workspace & Configuration

### 6.1 Workspace Directory

Rename default workspace from `~/.growthclaw/` to `~/.autogrow/` (with backward compat symlink).

### 6.2 New Workspace Files

```
~/.autogrow/
├── SOUL.md              # Agent persona (existing)
├── BUSINESS.md          # Auto-generated business profile (existing)
├── VOICE.md             # Message tone/style guide (existing)
├── COMPILER.md          # NEW — compilation pass status, optimization log
├── SECURITY.md          # Security rules (existing)
├── OWNER.md             # Owner info (existing)
├── skills/              # Skill files (existing)
├── .env                 # Credentials (existing)
├── .mcp.json            # MCP tools (existing)
├── CLAUDE.md            # Master context (existing)
└── data/
    ├── memory/          # LanceDB semantic memory (existing)
    └── logs/            # Tool call logs (existing)
```

**COMPILER.md** (auto-generated, updated nightly):
```markdown
# AutoGrow Compiler Status

## Current Compilation State
- Event Source: WAL streaming (wal_level=logical)
- Active Triggers: 5
- Total Sends: 8,247
- Total Experiments: 156
- Winning Variants Promoted: 41

## Pass Status
| Pass | Status | Last Run | Result |
|------|--------|----------|--------|
| Parse | ✅ Complete | Mar 25 | 66 tables, 962 columns |
| Understand | ✅ Complete | Mar 25 | driver_service, users table |
| Model | ✅ Complete | Mar 25 | 4-stage funnel, 81.7% drop-off |
| Compile | ✅ Active | Continuous | 5 triggers running |
| Optimize | ✅ Active | 6h cycle | Cycle #47, testing urgency tone |
| Self-Host | ⏳ Pending | Day 30 | Needs 30 days of outcome data |

## Latest Nightly Sweep Findings
- [Mar 25] Customers from Instagram have 2.3x LTV — proposing referral trigger
- [Mar 24] Wednesday 6-8 PM is highest-conversion window
- [Mar 23] 340 users stuck at payment method step — new trigger proposed
```

---

## Part 7: Database Migrations

### 7.1 New Migration Files

```
migrations/004_polling_watermarks.sql
migrations/005_suppressions.sql
migrations/006_autoresearch_memory.sql
migrations/007_compiler_state.sql
```

**006_autoresearch_memory.sql:**
```sql
-- AutoResearch semantic memory index
CREATE TABLE IF NOT EXISTS growthclaw.memory_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    text TEXT NOT NULL,
    category TEXT NOT NULL,  -- 'hypothesis', 'pattern', 'guardrail', 'insight'
    importance FLOAT NOT NULL DEFAULT 0.5,
    trigger_id UUID REFERENCES growthclaw.triggers(id),
    tags TEXT[] DEFAULT '{}',
    embedding VECTOR(384),  -- for LanceDB, or stored externally
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX idx_memory_category ON growthclaw.memory_entries(category);
CREATE INDEX idx_memory_trigger ON growthclaw.memory_entries(trigger_id);
```

**007_compiler_state.sql:**
```sql
CREATE TABLE IF NOT EXISTS growthclaw.compiler_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pass_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'active', 'complete'
    last_run_at TIMESTAMPTZ,
    result JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS growthclaw.prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_name TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    content TEXT NOT NULL,
    performance_score FLOAT,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(template_name, version)
);
```

---

## Part 8: New Prompt Templates

```
prompts/nightly_sweep.j2          — Nightly strategic intelligence sweep
prompts/optimize_prompts.j2       — Self-hosting pass: rewrite prompt templates
prompts/propose_new_triggers.j2   — Propose new triggers from sweep findings
```

---

## Part 9: Test Updates

### 9.1 New Test Files

```
tests/test_polling_listener.py     — Polling listener unit tests
tests/test_nightly_sweep.py        — Nightly sweep tests
tests/test_prompt_optimizer.py     — Self-hosting pass tests
tests/test_suppressions.py         — Email suppression tests
```

### 9.2 New Fixtures

```
tests/fixtures/driver_service_wal.json  — WAL event stream fixture
tests/fixtures/sweep_cohort_data.json   — Nightly sweep test data
```

### 9.3 Update Existing Tests

- Update CLI tests for new commands (`research`, `sweep`, `intelligence`, `health`)
- Update `test_trigger_evaluator.py` to test suppression checking
- Update integration tests for polling listener path

---

## Part 10: Configuration Defaults

### 10.1 Updated `.env.example`

```bash
# === Database ===
CUSTOMER_DATABASE_URL=postgresql://user:pass@host:5432/dbname
GROWTHCLAW_DATABASE_URL=postgresql://user:pass@host:5432/autogrow

# === Event Source ===
EVENT_MODE=poll              # poll | cdc | wal
POLL_INTERVAL_SECONDS=30

# === LLM ===
ANTHROPIC_API_KEY=sk-ant-...
NVIDIA_API_KEY=nvapi-...     # Optional: NVIDIA NIM primary

# === Outreach ===
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=growth@yourbusiness.com
RESEND_FROM_NAME=Your Business
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...

# === AutoResearch ===
AUTORESEARCH_INTERVAL_HOURS=6
NIGHTLY_SWEEP_HOUR=2         # Local hour (24h)
PROMPT_OPTIMIZATION_DAY=0    # 0=Monday, 6=Sunday

# === Safety ===
DRY_RUN=true                 # Set false for real sends
MAX_SMS_PER_DAY=2
MAX_SMS_PER_WEEK=5
MAX_EMAIL_PER_DAY=3
MAX_EMAIL_PER_WEEK=10
QUIET_HOURS_START=21         # 9 PM
QUIET_HOURS_END=9            # 9 AM

# === Cloud Intelligence (future) ===
# AUTOGROW_CLOUD_KEY=ag_...
```

---

## Part 11: Implementation Priority Order

For a developer (or Claude Code agent) implementing this spec:

### Sprint 1 (Week 1): Core — Get to Live Sends on Jeevz
1. ✅ Polling listener (`polling_listener.py` + migration)
2. ✅ Event source interface (`event_source.py`)
3. ✅ Wire polling into `main.py start()`
4. ✅ Suppression table + check in pipeline
5. ✅ Email unsubscribe link injection
6. ✅ Run `autogrow onboard` against Jeevz Postgres
7. ✅ Shadow mode: DRY_RUN=true, validate composed messages
8. ✅ First real send: one trigger, DRY_RUN=false

### Sprint 2 (Week 2): Optimization — AutoResearch Live
9. Wire AutoResearch loop into scheduler
10. AutoResearch variant assignment in message pipeline
11. Outcome tracking for AutoResearch cycles
12. Memory manager initialization in main engine
13. Test full AutoResearch cycle end-to-end

### Sprint 3 (Week 3): Intelligence — Nightly Sweep
14. Nightly sweep implementation
15. New prompt templates (nightly_sweep.j2, propose_new_triggers.j2)
16. COMPILER.md auto-generation
17. CLI commands: `research`, `sweep`, `intelligence`, `health`

### Sprint 4 (Week 4): Self-Hosting + Polish
18. Prompt optimizer (self-hosting pass)
19. WAL listener implementation
20. Event source auto-detection in onboarding
21. CLI rebrand: growthclaw → autogrow
22. Updated README with compiler framing
23. Full test suite updates
24. Webhook handler for Resend events

---

## Part 12: Success Criteria

V1 is done when:

1. `autogrow onboard` runs against Jeevz and correctly discovers the business
2. `autogrow start` begins polling for new events (read-only, no DB writes)
3. Real SMS and email sends fire for approved triggers
4. AutoResearch runs automatically every 6 hours, testing variants
5. Nightly sweep runs at 2 AM, finds patterns, proposes new triggers
6. Semantic memory accumulates learnings across experiments
7. 113+ tests pass (existing + new)
8. DRY_RUN works as a global safety switch
9. Suppression/unsubscribe handling is complete
10. The system can run unattended for 7 days without human intervention

**The Jeevz test:** After one week of running, AutoGrow should have:
- Sent 1,000+ messages across SMS + email
- Run 5+ AutoResearch experiment cycles
- Completed 7 nightly sweeps
- Accumulated 20+ memory entries
- Measurably moved the 81.7% activation drop-off

That's the case study. That's the launch story.

---

*Spec version: 1.0 · March 26, 2026 · Douglas Feirstein + Polly*
