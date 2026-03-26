# GrowthClaw

## What This Is
- Language: Python 3.13+ | Build: `uv pip install -e ".[dev]"`
- Key deps: asyncpg 0.31, pydantic 2.12, pydantic-settings 2.13, APScheduler 3.11, twilio 9.10, resend 2.0, httpx 0.28, anthropic 0.52+, Jinja2 3.1, lancedb 0.15, click 8.1
- Architecture: **dual-mode** — Python fast loop (poll/evaluate/queue) + Claude Code brain (compose/research/optimize)
- Two runtime modes:
  - **Harness mode** (default): `growthclaw daemon start --harness` — Python handles mechanical work, Claude Code handles creative/strategic work via cron wake-ups
  - **Standalone mode**: `STANDALONE_MODE=true` — Python engine does everything including direct LLM API calls (fallback if Claude Code unavailable)

### Directory Map
```
growthclaw/
├── discovery/         # LLM schema introspection + business concept mapping
├── triggers/          # CDC/polling/WAL listeners, evaluation, frequency caps
├── intelligence/      # Profile building, analysis, nightly sweep
├── outreach/          # SMS (Twilio), email (Resend/SendGrid), channel resolution
├── experiments/       # A/B testing + outcome checking
├── autoresearch/      # Karpathy-pattern autonomous experimentation
├── llm/               # Unified client: NVIDIA NIM primary, Anthropic fallback
│   └── anthropic_fallback.py  # Per-task model routing: Opus 4.6 (creative) / Sonnet 4.6 (analytical)
├── models/            # Pydantic v2 data models
├── prompts/           # Jinja2 .j2 templates (NEVER inline prompts in Python)
├── memory/            # LanceDB semantic memory
├── dashboard/         # Streamlit web UI
├── templates/         # Workspace .md templates (SOUL, VOICE, BUSINESS, etc.)
├── migrations/        # SQL migrations 001-006 for growthclaw.* schema
├── harness.py         # Unified daemon: Python fast loop + Claude Code cron
├── workspace_context.py  # Loads/caches workspace .md files for MCP tools
├── mcp_server.py      # 14 MCP tools for Claude Code (gc_* namespace)
├── config.py          # Pydantic Settings from ~/.growthclaw/.env
└── cli.py             # Click CLI (growthclaw / autogrow commands)
```

## Why Things Are This Way
- GrowthClaw works with ANY PostgreSQL database — zero hardcoded business logic
- `concepts` JSON is the single source of truth for all downstream components
- **Claude Code is the brain**: composes messages reading VOICE.md/SOUL.md, runs AutoResearch with memory, does strategic analysis. Python is the nervous system: fast, cheap, mechanical.
- Per-task model routing: Opus 4.6 for creative work (compose, hypothesize), Sonnet 4.6 for analytical (classify, evaluate)
- Customer DB is READ-ONLY — GrowthClaw only writes to its own `growthclaw` schema
- Event queue (`growthclaw.event_queue`) decouples evaluation (Python) from composition (Claude Code)
- `DRY_RUN=true` by default — must explicitly enable real sends
- Three event source modes: `poll` (default, read-only), `cdc` (LISTEN/NOTIFY), `wal` (logical replication)

### Hard Rules
- NEVER reference specific business table/column names in code
- NEVER write to customer tables
- NEVER inline LLM prompts — use `prompts/*.j2`
- Every LLM call logged with provider, purpose, latency, token estimate
- LLM JSON parsing retries once with fix prompt before failing

## How to Work Here
```bash
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
pytest                          # 137 tests
ruff check .                    # Lint
ruff format .                   # Format
mypy growthclaw/                # Type check
python -m growthclaw.migrate    # Run migrations
growthclaw onboard              # Discover a database
growthclaw daemon start --harness  # Start unified harness
```

### Before Submitting
1. `pytest` passes (137 tests, 3 business type fixtures)
2. `ruff check .` clean
3. `mypy growthclaw/` clean (pre-existing asyncpg stub warnings OK)
4. No business-specific logic (table names, column names, hardcoded SQL)
5. All LLM prompts in `prompts/*.j2`, not inline
6. New LLM calls include `purpose=` parameter for model routing

## Gotchas
- APScheduler v4 is alpha-only — pin to v3.11.x, use `AsyncIOScheduler`
- asyncpg: always use `async with pool.acquire() as conn:` — never hold connections outside the context manager
- Pydantic v2: `model_validate()` not `parse_obj()`, `model_dump()` not `.dict()`
- pg_notify payload limit: 8000 bytes — keep trigger payloads minimal
- Twilio SMS: 160 chars/segment — `message_composer.py` re-prompts LLM if over limit
- Claude model IDs have NO date suffix: `claude-sonnet-4-6`, `claude-opus-4-6`
- `concepts` JSON must match Pydantic model exactly — always validate after LLM returns
- Test fixtures must cover 3 business types (ecommerce, SaaS, driver_service) to prove genericity
- The `ruff` line length is 120 (set in `pyproject.toml`)
- `workspace_context.py` caches for 5min — call `.invalidate()` to force reload

## Reference Docs
async-postgres|.claude-docs/async-postgres.md|asyncpg patterns, connection pooling, LISTEN/NOTIFY, polling listener
llm-integration|.claude-docs/llm-integration.md|NVIDIA NIM + Anthropic fallback, per-task model routing, JSON retry, call logging
pydantic-patterns|.claude-docs/pydantic-patterns.md|Pydantic v2 models, settings, JSONB serialization
testing|.claude-docs/testing.md|pytest-asyncio setup, mock LLM fixtures, 3 schema fixtures
triggers-cdc|.claude-docs/triggers-cdc.md|PG trigger functions, pg_notify, CDC/polling/WAL event patterns
harness-architecture|.claude-docs/harness-architecture.md|Dual-mode harness, event queue, Claude Code cron, session management
mcp-tools|.claude-docs/mcp-tools.md|All 14 MCP tools (gc_* namespace), input schemas, usage patterns
