# AutoGrow — The Growth Compiler

> Point it at your database. It figures out your business, finds where customers
> drop off, sends personalized outreach, and gets smarter every day — on its own.

AutoGrow is a **compiler for growth**. Your database is the source code. Customer growth is the output.

It connects to any PostgreSQL database, discovers what your business does, maps the customer journey, finds the biggest opportunities, and starts sending personalized SMS and email — all without you writing a single rule. Then it runs experiments, learns what works, and rewrites its own playbook.

The human sets it up. After that, the system improves itself.

[![MIT License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue)
![Tests](https://img.shields.io/badge/tests-137%20passing-green)
![Claude Code](https://img.shields.io/badge/runtime-Claude_Code_Opus_4.6-blueviolet)

## How the Compiler Works

AutoGrow processes your database through six passes. The first four happen during onboarding (minutes). The last two run forever — getting smarter with every send.

```
PASS 1 — PARSE         Scan the database
                        Reads every table, column, type, foreign key, row count.
                        Works on any PostgreSQL database. No configuration needed.

PASS 2 — UNDERSTAND    Figure out the business
                        Uses AI to classify what it found — customer tables,
                        activation events, transactions, subscriptions, attribution.
                        Works for e-commerce, SaaS, marketplaces, anything.

PASS 3 — MODEL         Map the funnel
                        Computes the customer lifecycle: how many people sign up,
                        how many activate, where the biggest drop-off is,
                        what channels can reach them.

PASS 4 — COMPILE       Propose triggers + send messages
                        Generates growth triggers ranked by impact. Composes
                        personalized messages for each customer using everything
                        it knows about them — their activity, timing, segment.

PASS 5 — OPTIMIZE      Run experiments, learn, repeat (every 6 hours)
                        Tests different tones, offers, timing, and channels
                        (SMS, email, push, in-app). Measures what actually
                        converts. Promotes winners. Stores learnings in memory.

PASS 6 — SELF-HOST     Rewrite its own prompts (weekly)
                        Analyzes which messages produced the best outcomes.
                        Rewrites the templates that generated them.
                        Tests the rewrite against the original.
                        The system evolves beyond what any human would build.
```

## The Nightly Sweep

Every night at 2 AM, AutoGrow steps back and looks at the big picture:

- **Cohort analysis** — Which signup sources produce customers that actually stick around?
- **Timing patterns** — When do your best customers convert? What day, what hour?
- **Dormancy detection** — Who's slipping away that no current trigger is catching?
- **Whale identification** — What do your highest-value customers have in common?

Findings get stored in semantic memory. The next morning, AutoResearch uses them to design better experiments. Over weeks, AutoGrow builds an institutional knowledge base about your business that no human team could maintain.

## The Intelligence Network

Every AutoGrow instance generates experiment results — what tone worked, what timing converted, what offer moved the needle. Anonymized and aggregated, these results feed a shared intelligence layer.

A new e-commerce store on Day 1 already knows that "casual tone + 15min delay + free shipping offer" converts 3.2x better for cart abandonment — because 200 other e-commerce stores already tested it.

**Every customer makes every other customer smarter.** The network effect compounds. The 500th customer gets dramatically better results than the 5th.

## Claude Code is the Brain

The key insight: **Claude Code is the brain, Python is the nervous system.**

Python handles the fast, mechanical work — polling for events every 30 seconds, checking cooldowns, enforcing send limits. No AI needed, zero cost. Claude Code handles everything that requires judgment — writing messages in your brand's voice, designing experiments, analyzing patterns.

```
Your Database  →  Python (fast loop)  →  Event Queue  →  Claude Code (brain)  →  Send
                  poll, evaluate,         pending          reads your VOICE.md,     SMS
                  frequency caps          events           composes message,        Email
                  zero cost                                runs experiments
```

Claude Code wakes up every 15 minutes, reads your brand voice and business context, processes the queue, and goes back to sleep. Same session across every wake-up — it remembers everything it's learned.

| What Happens | Who Does It | Why |
|------|-----|-----|
| Detect new signups, purchases, events | Python | Runs 2,880x/day, instant, free |
| Enforce cooldowns, consent, quiet hours | Python | Pure logic, no thinking needed |
| Track conversions | Python | SQL queries, no reasoning |
| **Write the perfect message for each customer** | **Claude Code** | **Reads your voice guide, knows the customer** |
| **Design the next A/B test** | **Claude Code** | **Remembers every past experiment** |
| **Run the nightly strategic analysis** | **Claude Code** | **Sees patterns humans miss** |
| **Rewrite its own message templates** | **Claude Code** | **The compiler improves itself** |

## Quick Start

```bash
# Install
curl -sSL https://raw.githubusercontent.com/dfeirstein/growth-claw/main/scripts/install.sh | bash

# Set up + discover your business
growthclaw init                       # Create workspace
growthclaw onboard                    # Connect to your database

# Review what it found, then start
growthclaw triggers approve --all     # Approve proposed triggers
growthclaw daemon start --harness     # Start the compiler
```

## What Onboarding Looks Like

```
🐾 AutoGrow — Connecting to your database...

[1/7] Scanning database schema...
  Found 66 tables, 962 columns

[2/7] Detecting event source capabilities...
  ✅ wal_level = logical (real-time streaming available!)
  Using: poll mode (change with EVENT_MODE env var)

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
  Business profile written to: ~/.growthclaw/BUSINESS.md

✅ AutoGrow discovery complete!

  Compilation passes initialized:
  ├── PASS 1 (Parse)      ✅ Schema scanned
  ├── PASS 2 (Understand) ✅ Business concepts mapped
  ├── PASS 3 (Model)      ✅ Funnel analyzed
  ├── PASS 4 (Compile)    ✅ 5 triggers proposed
  ├── PASS 5 (Optimize)   ⏳ Starts after first sends
  └── PASS 6 (Self-Host)  ⏳ Starts after 30 days of data
```

## The Workspace

AutoGrow builds a workspace at `~/.growthclaw/` that shapes everything it does. These aren't config files — they're the agent's personality, knowledge, and memory.

```
~/.growthclaw/
├── SOUL.md              # Who the agent is — personality, principles
├── BUSINESS.md          # What it learned about YOUR business (auto-generated)
├── VOICE.md             # How to sound — your brand's tone and style
├── OWNER.md             # Who you are, what you care about
├── COMPILER.md          # Current status of all compilation passes
├── skills/              # Domain expertise (copywriting, analysis, experiments)
├── data/memory/         # Everything it's learned from experiments (LanceDB)
└── .mcp.json            # 14 tools Claude Code uses to interact with the system
```

## How It Learns

AutoGrow's learning is recursive and compounding:

1. **Send messages** → observe what converts
2. **AutoResearch** (every 6h) → design experiments based on outcomes + memory
3. **Nightly sweep** (2 AM) → find patterns across all customers, store in memory
4. **Self-hosting** (weekly) → rewrite the prompts that compose messages
5. **Cloud intelligence** (continuous) → learn from every other AutoGrow instance

Each layer feeds the next. Experiment results inform the sweep. Sweep findings shape the next experiment. Prompt rewrites get tested by AutoResearch. Network intelligence seeds new hypotheses.

**Day 1:** Generic messages based on funnel position.
**Day 30:** Personalized messages tuned by tone, timing, and offer — based on 100+ experiments.
**Day 100:** A system that knows your business better than your growth team does.

## Event Sources

AutoGrow watches your database for changes. Three modes, auto-detected during setup:

| Mode | How It Works | Setup Required |
|------|-------------|-----------|
| **Polling** (default) | Checks for new rows every 30 seconds | Nothing — fully read-only |
| **CDC** | Real-time PostgreSQL LISTEN/NOTIFY | Trigger install permission |
| **WAL** | Streams changes via logical replication | Replication permission |

Polling is the safest default — zero database modifications, works everywhere.

## Channels

| Channel | Status | Provider |
|---------|--------|----------|
| SMS | Live | Twilio |
| Email | Live | Resend / SendGrid |
| Push Notifications | Coming soon | FCM / APNs |
| In-App Messaging | Coming soon | WebSocket / SDK |

AutoGrow's AutoResearch loop tests across channels automatically — once push and in-app are live, the system will learn which channel converts best for each customer segment.

## CLI Reference

| Command | What It Does |
|---------|-------------|
| `growthclaw init` | Create workspace + setup wizard |
| `growthclaw onboard` | Discover your database (Passes 1-4) |
| `growthclaw daemon start --harness` | Start the compiler |
| `growthclaw daemon stop` | Stop |
| `growthclaw triggers list` | See proposed + active triggers |
| `growthclaw triggers approve --all` | Approve triggers |
| `growthclaw research` | See what AutoResearch is testing (Pass 5) |
| `growthclaw sweep` | Manually run the nightly sweep |
| `growthclaw intelligence` | See what it's learned (memory) |
| `growthclaw dashboard` | Open the web dashboard |
| `growthclaw health` | Full system health check |
| `growthclaw journeys` | See recent messages + outcomes |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.13+ |
| Runtime | Claude Code (Opus 4.6 for creative, Sonnet 4.6 for analytical) |
| Database | PostgreSQL (asyncpg) |
| Event Detection | Polling / CDC / WAL |
| SMS | Twilio |
| Email | Resend (default) / SendGrid |
| Push Notifications | Coming soon |
| In-App Messaging | Coming soon |
| Memory | LanceDB (semantic search over experiment learnings) |
| Dashboard | Streamlit |
| Scheduling | APScheduler 3.11 |

## Requirements

- **Python 3.13+**
- **PostgreSQL** — your database (read-only access) + an internal database for AutoGrow's state
- **Claude Code** — Max plan for the harness runtime
- **Twilio** — for SMS (optional — dry run mode works without it)
- **Resend** — for email (optional — dry run mode works without it)

## The Vision

AutoGrow is not a marketing tool with AI features. It's an autonomous system that replaces the growth team.

Three tiers, one codebase:

- **Open Source (free)** — Self-hosted. Bring your own keys. Full compiler. MIT license.
- **Managed ($3K/mo)** — We run it for you. Connect your database, we handle everything.
- **Cloud Intelligence ($99-499/mo)** — Tap into the shared experiment network. Every customer makes every other customer smarter.

## Deployment

```bash
# Mac Mini (recommended for first deployment)
growthclaw daemon start --harness

# VPS
bash <(curl -sSL https://raw.githubusercontent.com/dfeirstein/growth-claw/main/scripts/install-vps.sh)

# Docker
docker build -t autogrow .
docker run -e CUSTOMER_DATABASE_URL=... -e GROWTHCLAW_DATABASE_URL=... autogrow
```

## Contributing

```bash
git clone https://github.com/dfeirstein/growth-claw.git
cd growth-claw
python3.13 -m venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest                    # 137 tests
ruff check growthclaw/    # Lint
```

## License

[MIT](LICENSE)
