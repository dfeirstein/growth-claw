# GrowthClaw

**AI marketing engine that learns any business from its database.**

Point GrowthClaw at any PostgreSQL database. It discovers your schema, maps your customer funnel, identifies the biggest drop-off, and sends personalized SMS/email to convert more customers — autonomously.

![MIT License](https://img.shields.io/badge/license-MIT-blue)
![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue)
![Tests](https://img.shields.io/badge/tests-113%20passing-green)

## How It Works

```
Your Database  →  GrowthClaw Discovers  →  Proposes Triggers  →  Sends Outreach
                                                                        ↓
  PostgreSQL       66 tables, 962 cols      5 growth triggers     SMS / Email
  Any industry     Customer funnel          Auto-approved         Personalized
  Read-only        81% drop-off found       CDC real-time         A/B tested
```

GrowthClaw uses an LLM to understand your database at runtime. **Zero hardcoded business logic.** It works equally well with an e-commerce store, a SaaS platform, a driver service, or a healthcare CRM.

## Features

- **Schema Discovery** — Introspects any PostgreSQL database: tables, columns, types, foreign keys, row counts, data distributions
- **LLM Business Classification** — Identifies customer tables, activation events, transactions, subscriptions, attribution — all at runtime
- **Funnel Analysis** — Maps the customer lifecycle, calculates conversion rates, finds the biggest drop-off
- **Trigger Proposals** — LLM proposes 3-5 real-time marketing triggers prioritized by revenue impact
- **Real-Time CDC** — PostgreSQL LISTEN/NOTIFY captures events the moment they happen
- **Personalized Outreach** — LLM composes messages using 360° customer profiles (SMS via Twilio, Email via Resend)
- **AutoResearch** — Karpathy-pattern autonomous A/B testing: tests tone, offers, timing, personalization, and promotes winners
- **Semantic Memory** — LanceDB-backed memory that learns from experiments and informs future hypotheses
- **Multi-Provider LLM** — NVIDIA NIM (Nemotron) primary, Anthropic Claude fallback, with usage tracking
- **Streamlit Dashboard** — Live funnel, trigger performance, journey log, experiment results
- **Claude Code Agent** — Operator talks to GrowthClaw via Telegram, Discord, Slack, or CLI

## Quick Start

```bash
# Install (one command — no Python knowledge needed)
curl -sSL https://raw.githubusercontent.com/dfeirstein/growth-claw/main/scripts/install.sh | bash

# In a new terminal:
growthclaw init           # Create workspace + setup wizard
growthclaw onboard        # Discover your database (auto-runs migrations)
growthclaw triggers list  # Review proposed triggers
growthclaw dashboard      # Open web dashboard
```

## What Onboarding Looks Like

```
🐾 GrowthClaw — Connecting to your database...

[1/6] Scanning database schema...
  Found 66 tables, 962 columns

[2/6] Sampling data distributions...
  Sampled 56 tables with data

[3/6] Understanding your business...
  Business type: driver_service
  Customer table: users
  Activation event: Customer completes their first ride booking

[4/6] Analyzing customer funnel...
  Funnel stages: Registration -> Activation -> First Payment -> Subscription
  Biggest drop-off: 81.7% of registered customers never complete their first ride

[5/6] Proposing growth triggers...
  1. [SMS] registration_immediate_booking_nudge (5min delay, ~1500/week)
  2. [EMAIL] registration_24hour_email_sequence (24h delay, ~1200/week)
  3. [SMS] incomplete_booking_recovery (30min delay, ~200/week)
  4. [EMAIL] payment_method_activation_blocker (2h delay, ~150/week)
  5. [SMS] weekend_activation_opportunity (7d delay, ~300/week)

[6/6] Saving configuration...
  Business profile written to: ~/.growthclaw/BUSINESS.md

✅ GrowthClaw discovery complete!
```

## Architecture

```
~/.growthclaw/                          GrowthClaw Engine
├── SOUL.md          ┐                  ┌─────────────────────────┐
├── BUSINESS.md      │ Agent            │  Discovery Engine       │
├── VOICE.md         │ Context          │  ├── Schema Scanner     │
├── TOOLS.md         │ (loaded every    │  ├── Data Sampler       │
├── SECURITY.md      │  session)        │  ├── Concept Mapper     │
├── OWNER.md         ┘                  │  └── Funnel Analyzer    │
├── skills/                             │                         │
│   ├── copywriter.md                   │  Trigger System         │
│   ├── data-analyst.md                 │  ├── CDC Listener       │
│   ├── experiment-scientist.md         │  ├── Evaluator          │
│   ├── email-designer.md              │  └── Frequency Manager  │
│   └── growth-strategist.md           │                         │
├── .env             # Credentials      │  Outreach               │
├── .mcp.json        # MCP tools        │  ├── SMS (Twilio)       │
├── CLAUDE.md        # Master context   │  ├── Email (Resend)     │
└── data/                               │  └── Message Composer   │
    ├── memory/      # LanceDB          │                         │
    └── logs/        # Tool calls       │  AutoResearch Loop      │
                                        │  └── Hypothesis → Test  │
                                        │     → Evaluate → Learn  │
                                        └─────────────────────────┘
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `growthclaw init` | Create workspace at `~/.growthclaw/` + setup wizard |
| `growthclaw setup` | Re-run setup wizard (DB, keys, channels, permissions) |
| `growthclaw migrate` | Create/update internal database tables |
| `growthclaw onboard` | Discover schema + propose triggers (auto-migrates) |
| `growthclaw triggers list` | Show all triggers with status and metrics |
| `growthclaw triggers approve --all` | Approve proposed triggers |
| `growthclaw start` | Install CDC triggers and start event listener |
| `growthclaw stop` | Stop listener and remove CDC triggers |
| `growthclaw status` | Health check: DB, triggers, events, journeys |
| `growthclaw dashboard` | Open Streamlit web dashboard |
| `growthclaw daemon start --claude` | Start Claude Code agent in tmux |
| `growthclaw daemon stop` | Stop the agent |
| `growthclaw channels telegram` | Set up Telegram operator channel |
| `growthclaw channels discord` | Set up Discord operator channel |
| `growthclaw channels slack` | Set up Slack operator channel |
| `growthclaw journeys` | Show recent outreach log |
| `growthclaw experiments` | Show AutoResearch results |
| `growthclaw export` | Export all data as JSON |

## Requirements

- **Python 3.13+** (installer handles this)
- **PostgreSQL** — customer database (read-only) + internal database (read-write)
- **Anthropic API key** — for LLM calls (or NVIDIA NIM key)
- **Twilio** — for SMS (optional, dry run works without it)
- **Resend** — for email (optional, dry run works without it)

## Email Provider

GrowthClaw defaults to **Resend** but supports **SendGrid** for enterprise customers:

```bash
# In ~/.growthclaw/.env
GROWTHCLAW_EMAIL_PROVIDER=resend    # or "sendgrid"
RESEND_API_KEY=re_xxxxxxxxxxxx
# SENDGRID_API_KEY=SG.xxxxxxxxxxxx  # if using sendgrid
```

## VPS Deployment

```bash
# One-line server setup
bash <(curl -sSL https://raw.githubusercontent.com/dfeirstein/growth-claw/main/scripts/install-vps.sh)

# Or with Docker
docker build -t growthclaw .
docker run -e ANTHROPIC_API_KEY=... -e CUSTOMER_DATABASE_URL=... growthclaw
```

## How CDC Works

GrowthClaw installs lightweight PostgreSQL triggers on your tables (AFTER INSERT/UPDATE). When a customer signs up, the trigger fires `pg_notify()` — GrowthClaw's listener picks it up in real-time, waits the configured delay, evaluates cooldowns/consent/quiet hours, builds a profile, composes a personalized message, and sends it. No Kafka, no Debezium, no webhooks — just built-in PostgreSQL.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.13+ |
| Database | PostgreSQL (asyncpg) |
| Real-time | PostgreSQL LISTEN/NOTIFY |
| LLM Primary | NVIDIA NIM (Nemotron 3 Super 120B) |
| LLM Fallback | Anthropic Claude (Sonnet 4) |
| SMS | Twilio |
| Email | Resend (default) / SendGrid |
| Scheduling | APScheduler |
| Data Models | Pydantic v2 |
| Memory | LanceDB |
| Dashboard | Streamlit |
| Templates | Jinja2 |
| Agent | Claude Code CLI |

## Contributing

```bash
git clone https://github.com/dfeirstein/growth-claw.git
cd growth-claw
python3.13 -m venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest                    # 113 tests
ruff check growthclaw/    # Lint
```

## License

[MIT](LICENSE)
