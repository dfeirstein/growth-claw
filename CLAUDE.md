# GrowthClaw

## What This Is
- Language: Python 3.13+
- Key deps: asyncpg 0.31, pydantic 2.12, pydantic-settings 2.13, APScheduler 3.11, twilio 9.10, httpx 0.28, Jinja2 3.1, anthropic 0.52+
- Architecture: async event-driven pipeline — discover schema → propose triggers → listen for CDC events → build profiles → send outreach
- Structure:
  - `growthclaw/discovery/` -- LLM-powered schema introspection and business concept mapping
  - `growthclaw/triggers/` -- CDC trigger proposal, installation, listening, evaluation
  - `growthclaw/intelligence/` -- Customer profile building and LLM analysis
  - `growthclaw/outreach/` -- Message composition and SMS/email delivery
  - `growthclaw/experiments/` -- A/B testing on trigger delay timing
  - `growthclaw/llm/` -- Unified LLM client (NVIDIA NIM primary, Anthropic fallback)
  - `growthclaw/models/` -- Pydantic v2 data models
  - `growthclaw/prompts/` -- Jinja2 prompt templates (never inline prompts in Python)
  - `growthclaw/migrations/` -- SQL migrations for growthclaw.* internal tables

## Why Things Are This Way
- GrowthClaw is a PRODUCT that works with ANY PostgreSQL database — zero hardcoded business logic
- `discovery/` uses LLM to classify tables and map business concepts at runtime
- `concepts` JSON is the single source of truth — every downstream component reads from it
- Key decisions:
  - NVIDIA NIM (Nemotron) as primary LLM, Anthropic Claude as fallback — cost optimization
  - PostgreSQL LISTEN/NOTIFY for real-time CDC — no external message queue needed
  - All LLM prompts in Jinja2 .j2 files — never inline prompt strings in Python
  - Customer DB is READ-ONLY — GrowthClaw only writes to its own `growthclaw` schema
  - DRY_RUN=true by default — must explicitly enable real sends
- Constraints:
  - NEVER reference specific business table/column names in code
  - NEVER write to customer tables (only install NOTIFY triggers)
  - Every LLM call must be logged (prompt, response, latency)
  - LLM JSON parsing must retry once with a fix prompt before failing gracefully

## How to Work Here
- Setup: `uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"`
- Test: `pytest`
- Lint: `ruff check .`
- Format: `ruff format .`
- Type check: `mypy growthclaw/`
- Run migrations: `python -m growthclaw.migrate`
- Onboard a DB: `python -m growthclaw.cli onboard`
- Start listener: `python -m growthclaw.cli start`

### Before Submitting
1. `pytest` passes
2. `ruff check .` passes
3. `mypy growthclaw/` passes
4. No business-specific logic introduced (table names, column names, SQL)
5. All LLM prompts are in `prompts/*.j2`, not inline

## Gotchas
- APScheduler v4 is alpha-only — use v3.11.x with AsyncIOScheduler
- asyncpg requires `await pool.acquire()` context manager — never hold connections outside async with
- Pydantic v2 uses `model_validate()` not `parse_obj()`, `model_dump()` not `.dict()`
- pg_notify payload is limited to 8000 bytes — keep trigger payloads minimal
- Twilio SMS must be ≤160 chars per segment — re-prompt LLM if over limit
- The `concepts` JSON structure must match exactly what downstream components expect — validate with Pydantic model after LLM returns it
- Test fixtures must cover 3 business types (ecommerce, SaaS, driver service) to prove genericity

## Reference Docs
async-postgres|.claude-docs/async-postgres.md|asyncpg patterns, connection pooling, LISTEN/NOTIFY for CDC
llm-integration|.claude-docs/llm-integration.md|NVIDIA NIM + Anthropic fallback, JSON retry, call logging
pydantic-patterns|.claude-docs/pydantic-patterns.md|Pydantic v2 models, settings, JSONB serialization
testing|.claude-docs/testing.md|pytest-asyncio setup, mock LLM fixtures, schema fixtures
triggers-cdc|.claude-docs/triggers-cdc.md|PG trigger functions, pg_notify, CDC event patterns
