# AutoGrow — Product Requirements Document

## The Vision

AutoGrow is a **compiler for growth marketing**. Raw business data goes in. Optimized customer interactions come out. Every pass makes it smarter.

Just like GCC takes source code through lexing → parsing → optimization → machine code, AutoGrow takes any PostgreSQL database through recursive compilation passes that discover the business, identify growth opportunities, execute personalized outreach, and self-optimize based on real-world outcomes.

Three product tiers, one architecture:

1. **Open Source (free)** — Self-hosted. BYO keys. Isolated intelligence. MIT license.
2. **Managed Service ($3K/mo)** — We run AutoGrow for you. 89% margins. Zero employees.
3. **Cloud Intelligence ($99-499/mo)** — Shared experiment network. Every customer makes every other customer smarter.

---

## The Compiler Architecture

```
PASS 1 — PARSE         Schema scanner + data sampler
                        Reads any PostgreSQL database like a lexer reads source code.
                        Discovers tables, columns, types, foreign keys, row counts,
                        data distributions. Zero business-specific logic.

PASS 2 — UNDERSTAND     LLM concept mapper
                        Semantic analysis — classifies tables into business concepts:
                        customer table, activation events, transactions, subscriptions,
                        attribution. Outputs BusinessConcepts (the IR).

PASS 3 — MODEL          Funnel analyzer + relationship resolver
                        Builds the intermediate representation: customer lifecycle
                        stages, conversion rates, biggest drop-off, activation window,
                        reachability by channel.

PASS 4 — COMPILE        Trigger proposer + message composer
                        Generates the output: trigger rules prioritized by revenue
                        impact, personalized messages composed per-recipient using
                        360° customer profiles.

PASS 5 — OPTIMIZE       AutoResearch loop
                        Profile-Guided Optimization — runs on REAL outcomes.
                        Tests hypotheses (tone, timing, offers, channels).
                        Measures conversions. Promotes winners. Updates semantic memory.
                        Runs continuously, every 6 hours.

PASS 6 — SELF-HOST      Prompt rewriter
                        The compiler rewrites its own compilation passes.
                        Analyzes which prompt templates produced the best outcomes.
                        Proposes rewrites. Tests them via AutoResearch.
                        The human wrote Pass 1. By Day 100, the system bears no
                        resemblance to what a human would have built.
```

---

## What Phase 1 Built (COMPLETE — in production)

```
growthclaw/
├── discovery/           ✅ Schema scanner, data sampler, concept mapper,
│                           relationship resolver, funnel analyzer, schema store
├── triggers/            ✅ Trigger proposer, installer, evaluator, CDC listener,
│                           trigger store, frequency manager
├── intelligence/        ✅ Profile builder, profile analyzer, profile store
├── outreach/            ✅ Message composer, channel resolver, journey store,
│                           SMS sender (Twilio), email sender (Resend/SendGrid)
├── experiments/         ✅ Experiment manager, experiment store, outcome checker
├── autoresearch/        ✅ Loop, hypothesis generator, evaluator, variant creator
│                           (code exists but NOT wired into main engine)
├── memory/              ✅ LanceDB semantic memory manager, embedder, schemas
│                           (code exists but NOT wired into main engine)
├── llm/                 ✅ Unified client (NVIDIA NIM primary, Claude fallback),
│                           JSON parsing with retry, usage tracker
├── dashboard/           ✅ Streamlit app (overview, triggers, journeys, experiments)
├── models/              ✅ Pydantic v2: SchemaMap, BusinessConcepts, TriggerRule,
│                           CustomerProfile, IntelligenceBrief, Journey, Experiment
├── prompts/             ✅ 11 Jinja2 templates (classify, funnel, triggers,
│                           compose message/email, profile, hypothesis, variants, etc.)
├── tests/               ✅ 6 modules, 113 tests, 3 schema fixtures
├── cli.py               ✅ onboard, triggers, start/stop, status, journeys,
│                           experiments, export, migrate
├── main.py              ✅ Full pipeline: event → evaluate → profile → compose → send
├── config.py            ✅ Pydantic Settings with .env loading
├── daemon.py            ✅ Claude Code agent launcher (tmux)
├── channels.py          ✅ Telegram/Discord/Slack channel setup
├── workspace.py         ✅ Workspace file generation (BUSINESS.md, etc.)
├── migrate.py           ✅ SQL migration runner
└── setup_wizard.py      ✅ Interactive setup wizard
```

**Key facts:**
- 9,400 lines of production Python
- 113 tests passing across 3 business types (ecommerce, SaaS, driver_service)
- Zero hardcoded business logic — everything discovered via LLM at runtime
- `BusinessConcepts` is the single source of truth (the IR)
- Customer DB is read-only
- DRY_RUN=true by default
- All LLM prompts in `prompts/*.j2`, never inline
- Battle-tested on Jeevz: 77K users, 66 tables, 962 columns

---

## What V1 Adds (BUILD THIS)

### Priority 1: Event Source Abstraction (Week 1)

The current CDC listener requires write access to install pg_notify triggers. This blocks adoption. We need three event source modes behind a common interface.

**1a. Event Source Interface**

New file: `growthclaw/triggers/event_source.py`

```python
from abc import ABC, abstractmethod

class EventSource(ABC):
    @abstractmethod
    async def start(self) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
    @property
    @abstractmethod
    def mode(self) -> str: ...  # "poll" | "cdc" | "wal"
```

All three listeners implement this. `main.py` instantiates based on `settings.event_mode`.

**1b. Polling Listener (DEFAULT)**

New file: `growthclaw/triggers/polling_listener.py`

- Default mode. Truly read-only. Zero setup on customer DB.
- Polls watched tables every N seconds (default 30) using indexed timestamp queries
- Tracks high-water marks in `growthclaw.polling_watermarks`
- Emits identical `TriggerEvent` objects — rest of pipeline unchanged
- Reconnection with exponential backoff

Config additions to `config.py`:
```python
event_mode: str = Field(default="poll", alias="EVENT_MODE")  # "poll" | "cdc" | "wal"
poll_interval_seconds: int = Field(default=30, alias="POLL_INTERVAL_SECONDS")
```

New migration: `migrations/004_polling_watermarks.sql`

**1c. WAL Logical Replication Listener (RECOMMENDED)**

New file: `growthclaw/triggers/wal_listener.py`

- For databases with `wal_level=logical` (most managed Postgres)
- Consumes WAL stream via logical replication slot
- Uses `wal2json` output plugin
- Zero load on customer DB, real-time (millisecond latency), read-only
- Falls back to polling if WAL unavailable

**1d. Update main.py `start()`**

Auto-detect capabilities during onboarding:
```python
wal_level = await conn.fetchval("SHOW wal_level")
if wal_level == 'logical':
    # Recommend WAL mode
else:
    # Default to polling
```

Instantiate correct listener based on `event_mode` config.

**1e. Update onboarding output**

Add step [2/7] "Detecting event source capabilities..." showing what mode was selected and why.

### Priority 2: Wire AutoResearch into Main Engine (Week 2)

The AutoResearch code EXISTS in `autoresearch/` but is NOT connected to the scheduler or the send pipeline.

**2a. Schedule AutoResearch in `main.py start()`**

```python
self.scheduler.add_job(self._run_autoresearch, "interval", hours=6, id="autoresearch_loop")
```

Runs one cycle for each active trigger: observe → evaluate running cycle → hypothesize → create variants → deploy new cycle.

**2b. Variant assignment in send pipeline**

In `_delayed_evaluate()`, before message composition:
- Check if trigger has a running AutoResearch cycle
- If yes, assign user to control or test arm (deterministic hash on user_id + cycle_id)
- Use the appropriate template (control or test) for message composition
- Track sends per arm in `growthclaw.autoresearch_cycles`

**2c. Wire semantic memory**

Initialize `MemoryManager` in the main engine. AutoResearch loop already uses it for recall/store — just needs the manager passed in during initialization.

### Priority 3: Email Hardening (Week 1-2)

**3a. Suppression management**

New migration: `migrations/005_suppressions.sql`
```sql
CREATE TABLE growthclaw.suppressions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    reason TEXT NOT NULL,  -- 'unsubscribe', 'bounce', 'complaint'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, channel)
);
```

Check suppressions in `_delayed_evaluate()` before sending (add after consent check).

**3b. Unsubscribe link injection**

Every email MUST include a one-click unsubscribe link. Update `compose_email.j2` to instruct LLM to include unsubscribe text. Also programmatically append unsubscribe URL to HTML body in `email_sender.py` as a safety net.

**3c. Resend webhook handler**

New file: `growthclaw/outreach/webhook_handler.py`

Simple HTTP endpoint (can use aiohttp or FastAPI) that receives Resend webhook events:
- `email.bounced` → insert suppression (reason='bounce')
- `email.complained` → insert suppression (reason='complaint')  
- `email.unsubscribed` → insert suppression (reason='unsubscribe')

### Priority 4: Nightly Strategic Sweep (Week 3)

**New file:** `growthclaw/intelligence/nightly_sweep.py`

Runs at 2 AM. Scans the customer database for patterns the trigger system hasn't found:

1. **Cohort analysis** — which signup sources retain best?
2. **Timing patterns** — when do converters convert? (hour, day, week)
3. **Dormancy detection** — who's slipping away that no current trigger targets?
4. **Whale identification** — highest-value customers, what do they have in common?
5. **Referral patterns** — organic referral rates, who's bringing new customers?

Compares findings against semantic memory (what's new vs already known). Proposes new triggers or strategy adjustments via LLM. Stores findings in memory.

**New prompt template:** `prompts/nightly_sweep.j2`

**Schedule:** `self.scheduler.add_job(..., "cron", hour=2, id="nightly_sweep")`

### Priority 5: Self-Hosting Compiler Pass (Week 4)

**New file:** `growthclaw/autoresearch/prompt_optimizer.py`

The "self-hosting" pass: the compiler rewrites its own compilation passes.

1. Query all journeys with outcomes from the past 30 days
2. Group by trigger, compute conversion rates per message pattern
3. Ask LLM to identify what makes winning messages different from losing ones
4. Ask LLM to rewrite the prompt template to bias toward winning patterns
5. Save new template version in `growthclaw.prompt_versions`
6. AutoResearch tests the new template against the current one

**New prompt template:** `prompts/optimize_prompts.j2`

**New migration:** `migrations/007_compiler_state.sql` (prompt_versions table)

**Schedule:** Weekly (Sunday 3 AM), after enough data accumulates (minimum 30 days of outcomes).

### Priority 6: CLI Updates

**New commands:**
- `autogrow research` — Show AutoResearch status and latest cycle results
- `autogrow sweep` — Manually trigger nightly sweep  
- `autogrow intelligence` — Show memory contents (top insights, patterns, guardrails)
- `autogrow health` — Extended health check: DB connectivity, event source, triggers, experiments

**Rebrand:**
- Add `autogrow` as CLI entry point in `pyproject.toml` (keep `growthclaw` as backward compat alias)
- Default workspace: `~/.autogrow/` (symlink from `~/.growthclaw/`)

### Priority 7: Auto-Generated COMPILER.md

New workspace file auto-generated after each nightly sweep:

```markdown
# AutoGrow Compiler Status

## Compilation Passes
| Pass | Status | Last Run | Result |
|------|--------|----------|--------|
| Parse | ✅ | Mar 25 | 66 tables, 962 columns |
| Understand | ✅ | Mar 25 | driver_service |
| Model | ✅ | Mar 25 | 4-stage funnel, 81.7% drop-off |
| Compile | ✅ Active | Continuous | 5 triggers running |
| Optimize | ✅ Active | 6h cycle | Cycle #47 |
| Self-Host | ⏳ Pending | Day 30 | Needs 30 days of data |

## Latest Findings
- [date] finding description
```

---

## Database Migrations (V1)

```
migrations/004_polling_watermarks.sql   — Watermark tracking for polling listener
migrations/005_suppressions.sql         — Email/SMS suppression management
migrations/006_autoresearch_memory.sql  — Semantic memory persistence table
migrations/007_compiler_state.sql       — Compiler pass state + prompt versioning
```

---

## New Prompt Templates (V1)

```
prompts/nightly_sweep.j2          — Strategic intelligence sweep
prompts/optimize_prompts.j2       — Self-hosting: rewrite prompt templates
prompts/propose_new_triggers.j2   — Propose triggers from sweep findings
```

---

## New Test Files (V1)

```
tests/test_polling_listener.py    — Polling listener unit tests
tests/test_nightly_sweep.py       — Nightly sweep tests
tests/test_prompt_optimizer.py    — Self-hosting pass tests
tests/test_suppressions.py        — Email suppression tests
```

Add a WAL fixture: `tests/fixtures/driver_service_wal.json`

Update existing tests for new CLI commands and suppression checking.

---

## Configuration (.env)

```bash
# === Event Source ===
EVENT_MODE=poll                  # poll | cdc | wal
POLL_INTERVAL_SECONDS=30

# === AutoResearch ===
AUTORESEARCH_INTERVAL_HOURS=6
NIGHTLY_SWEEP_HOUR=2
PROMPT_OPTIMIZATION_DAY=0        # 0=Monday

# === Safety ===
DRY_RUN=true
MAX_SMS_PER_DAY=2
MAX_SMS_PER_WEEK=5
MAX_EMAIL_PER_DAY=3
MAX_EMAIL_PER_WEEK=10
QUIET_HOURS_START=21
QUIET_HOURS_END=9

# === Cloud Intelligence (future — not V1) ===
# AUTOGROW_CLOUD_KEY=ag_...
```

---

## The Managed Service (Post-V1 — Context Only)

Once V1 is running on Jeevz, the managed service works like this:

- **Multi-tenant deployment** — one platform, multiple customers. Each customer = a row in a tenants table, not a server.
- **Customer provides:** read-only Postgres URL + Resend API key + Twilio creds (optional)
- **We provide:** full AutoGrow operation, monitoring, optimization
- **Pricing:** $3,000/month. Our cost: ~$300 LLM tokens + ~$50 infra = 89% margin.
- **Customer pays their own Twilio/Resend** — we never touch send infrastructure.
- **Operator interface:** Telegram/Slack bot per customer (lightweight, not Claude Code session per customer)
- **Human time per customer:** ~1 hour/month monitoring

Architecture for multi-tenant is NOT in V1 scope. V1 runs as a single-tenant instance on Jeevz. Multi-tenant is a post-V1 engineering project.

---

## The Cloud Intelligence Layer (Post-V1 — Context Only)

The network effect moat. Not built in V1 but the architecture should support it.

**How it works:**
- Each AutoGrow instance generates experiment results (trigger type, channel, variable tested, uplift %, business_type)
- Anonymized — no customer data, no message content, no PII
- Results feed a shared intelligence API
- New customers query the API: "What works for e-commerce businesses re-engaging after 7 days?"
- API returns aggregated patterns from the network

**What V1 needs to enable this (future-proofing):**
- Experiment results table should include `business_type` and enough metadata to be useful when anonymized
- AutoResearch cycle results should be exportable (`autogrow export` already exists — ensure it includes experiment data)
- Memory entries should be taggable by category and importance

**Pricing (future):**
- Free for first 500 customers (cold start — build the corpus)
- $99/mo Pro (community intelligence + benchmarks)
- $499/mo Scale (priority intelligence + custom playbook training)
- Enterprise: private intelligence pool (only your org's data)

---

## The Product Positioning

**We are NOT building:**
- A better Klaviyo/Customer.io/Braze
- A marketing automation platform with AI features
- A workflow builder

**We ARE building:**
- A compiler that takes databases as input and produces customer growth as output
- An autonomous system that replaces the growth team, not assists it
- A self-improving engine where Day 100 is unrecognizably better than Day 1
- A network where every customer makes every other customer smarter

**The key analogy:**
- Marketing automation tools = manually writing assembly code
- AutoGrow = a compiler that generates optimized machine code from high-level source (your database)
- Nobody writes assembly anymore. Soon, nobody writes marketing flows.

**The Sequoia frame:**
- For every $1 on marketing software, $6 is spent on marketing teams
- AutoGrow captures the $6 (labor budget), not the $1 (software budget)
- A $300K growth team gets replaced by a $36K autonomous engine

---

## V1 Success Criteria

V1 is done when all of the following are true:

1. `autogrow onboard` runs against Jeevz, correctly discovers the business, maps the funnel, identifies the 81.7% drop-off
2. `autogrow start` begins polling for events (read-only, zero DB writes on customer side)
3. Real SMS and email sends fire for approved triggers with proper suppression/unsubscribe handling
4. AutoResearch runs automatically every 6 hours, testing message variants
5. Nightly sweep runs at 2 AM, finds patterns, proposes new triggers
6. Semantic memory accumulates learnings across experiments
7. All tests pass (113 existing + new tests for V1 features)
8. DRY_RUN works as a global safety switch
9. The system runs unattended for 7 days without human intervention

**The Jeevz test:** After one week of running, AutoGrow should have:
- Sent 1,000+ messages across SMS + email
- Run 5+ AutoResearch experiment cycles  
- Completed 7 nightly sweeps
- Accumulated 20+ memory entries
- Measurably moved the 81.7% activation drop-off

That data becomes the case study. That case study launches AutoGrow.

---

## Implementation Order

| Sprint | Week | What | Why First |
|--------|------|------|-----------|
| 1 | 1 | Polling listener + event source interface + suppressions + email hardening | Unblocks live sends on Jeevz |
| 2 | 2 | Wire AutoResearch into engine + memory initialization + variant assignment | Enables self-optimization |
| 3 | 3 | Nightly sweep + new prompt templates + CLI commands | Enables strategic intelligence |
| 4 | 4 | Self-hosting pass + WAL listener + rebrand + README + full test suite | Polish and launch prep |

---

## Constraints (ALWAYS follow these)

1. **NEVER hardcode business logic** — no table names, column names, or SQL specific to any business
2. **NEVER write to customer database** — read-only always. All state in `growthclaw` schema.
3. **ALL LLM prompts in `prompts/*.j2`** — never inline prompt strings in Python
4. **DRY_RUN=true by default** — must explicitly enable real sends
5. **Every LLM call logged** — prompt, response, latency, tokens
6. **Pydantic v2 everywhere** — `model_validate()`, `model_dump()`, Field with alias
7. **asyncpg context managers** — never hold connections outside `async with pool.acquire()`
8. **APScheduler v3.11.x** — v4 is alpha, don't upgrade
9. **SMS ≤ 160 chars** — re-prompt LLM if over limit
10. **Test every business type** — fixtures must cover ecommerce, SaaS, driver_service

---

*PRD version: 1.0 · March 26, 2026 · autogrow.bot*
