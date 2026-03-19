# GrowthClaw Phase 1 — Claude Code Implementation Prompt (v2)

Copy everything below the line into Claude Code.

---

# PROJECT: GrowthClaw Phase 1 — AI Marketing Engine That Learns Any Business

You are building GrowthClaw, an AI marketing engine that connects to any PostgreSQL database, autonomously learns the business, identifies growth opportunities, and sends personalized outreach via SMS/email. This is a PRODUCT, not an internal tool. Every component must be generic and configurable — no business-specific logic hardcoded anywhere.

The first customer deploying GrowthClaw is Jeevz (a premium personal driver service). Jeevz is used to validate the system, not to shape its architecture.

## CORE DESIGN PRINCIPLE

**Nothing about Jeevz should appear in the codebase.** No table names, no column names, no business logic. GrowthClaw discovers all of this at runtime by connecting to the database and using an LLM to understand what it finds. If you deleted every reference to "Jeevz" from this prompt, the system should still work when pointed at a Shopify database, a SaaS billing database, or a healthcare CRM.

## WHAT PHASE 1 DELIVERS

A working system that, given any PostgreSQL connection string:

1. **Discovers** the schema — tables, columns, types, relationships, row counts
2. **Classifies** each table's business role using an LLM (identity, transaction, payment, subscription, attribution, etc.)
3. **Maps** the critical business concepts: who is a "customer"? what is a "conversion"? what is a "payment method"? what is "churn"?
4. **Analyzes** the funnel — identifies the biggest drop-off points in the customer lifecycle
5. **Proposes** trigger rules based on the data patterns it finds
6. **Executes** the first trigger: when a new customer signs up and doesn't complete a key activation step within N minutes, build their profile and send a personalized nudge
7. **Experiments** on the trigger delay to find the optimal timing
8. **Tracks** outcomes and reports on what's working

## TECH STACK

- **Language:** Python 3.10+
- **Database:** PostgreSQL (customer DB: read-only; GrowthClaw internal: read-write)
- **Real-time:** PostgreSQL LISTEN/NOTIFY with auto-generated triggers
- **LLM:** NVIDIA NIM API (Nemotron 3 Super) via OpenAI-compatible endpoint at `https://integrate.api.nvidia.com/v1`, model `nvidia/nemotron-3-super-120b-a12b`. Fall back to Anthropic Claude API (`claude-sonnet-4-20250514`) if NVIDIA key not set.
- **SMS:** Twilio REST API
- **Task scheduling:** APScheduler (delayed trigger checks, outcome polling)
- **Data models:** Pydantic v2
- **Async:** asyncpg + asyncio

## DIRECTORY STRUCTURE

```
growthclaw/
├── README.md
├── pyproject.toml
├── .env.example
│
├── config.py                              # Load and validate env config
│
├── discovery/                             # PHASE 1A: Schema Discovery Engine
│   ├── __init__.py
│   ├── schema_scanner.py                  # Introspect PG: tables, columns, types, FKs, row counts
│   ├── data_sampler.py                    # Sample N rows per table, compute distributions
│   ├── concept_mapper.py                  # LLM classifies tables/columns into business concepts
│   ├── relationship_resolver.py           # Build entity relationship graph from FKs + LLM inference
│   ├── funnel_analyzer.py                 # LLM identifies the customer lifecycle funnel + drop-offs
│   └── schema_store.py                    # Persist discovery results to growthclaw.schema_map
│
├── triggers/                              # PHASE 1B: Trigger System
│   ├── __init__.py
│   ├── trigger_proposer.py                # LLM proposes trigger rules from discovered funnel
│   ├── trigger_installer.py               # Generate and install PG NOTIFY triggers on customer DB
│   ├── trigger_evaluator.py               # Evaluate if a CDC event is actionable (cooldowns, consent, quiet hours)
│   ├── cdc_listener.py                    # PostgreSQL LISTEN/NOTIFY consumer
│   └── trigger_store.py                   # Persist trigger configs to growthclaw.triggers
│
├── intelligence/                          # PHASE 1C: Customer Intelligence
│   ├── __init__.py
│   ├── profile_builder.py                 # Build 360° profile from discovered schema (generic SQL generation)
│   ├── profile_analyzer.py                # LLM analyzes profile and produces intelligence brief
│   └── profile_store.py                   # Cache profiles in growthclaw.profiles
│
├── outreach/                              # PHASE 1D: Message Composition + Delivery
│   ├── __init__.py
│   ├── message_composer.py                # LLM generates personalized message from profile + trigger context
│   ├── sms_sender.py                      # Twilio delivery
│   ├── channel_resolver.py                # Determine best channel + contact info from discovered schema
│   └── journey_store.py                   # Log all outreach to growthclaw.journeys
│
├── experiments/                           # PHASE 1E: A/B Testing
│   ├── __init__.py
│   ├── experiment_manager.py              # Create, assign arms, evaluate experiments
│   ├── outcome_checker.py                 # Poll for conversions (did user complete the activation step?)
│   └── experiment_store.py                # Persist experiments + results
│
├── llm/                                   # LLM abstraction layer
│   ├── __init__.py
│   ├── client.py                          # Unified interface: call(prompt, response_format) → str
│   ├── nvidia_nim.py                      # NVIDIA NIM (Nemotron) implementation
│   └── anthropic_fallback.py              # Claude fallback implementation
│
├── migrations/
│   └── 001_create_growthclaw_schema.sql   # GrowthClaw internal tables (NO customer-specific SQL)
│
├── models/                                # Pydantic models
│   ├── __init__.py
│   ├── schema_map.py                      # SchemaMap, TableInfo, ColumnInfo, BusinessConcept
│   ├── trigger.py                         # TriggerRule, TriggerEvent, TriggerState
│   ├── profile.py                         # CustomerProfile, IntelligenceBrief
│   ├── journey.py                         # Journey, JourneyOutcome
│   └── experiment.py                      # Experiment, ExperimentArm, ExperimentResult
│
├── prompts/                               # LLM prompt templates (Jinja2)
│   ├── classify_schema.j2                 # "Given this schema, classify each table's business role"
│   ├── map_concepts.j2                    # "Identify: customer table, conversion event, payment method, churn signal"
│   ├── analyze_funnel.j2                  # "Here's the data — what's the customer lifecycle and where are the drop-offs?"
│   ├── propose_triggers.j2               # "Based on this funnel, what real-time triggers would drive growth?"
│   ├── build_profile_queries.j2           # "Generate SQL queries to build a 360° profile for user X"
│   ├── analyze_profile.j2                # "Given this customer's data, who are they and what do they need?"
│   ├── compose_message.j2                # "Write a personalized SMS for this person in this situation"
│   └── analyze_experiment.j2              # "Here are the A/B test results — what's the conclusion?"
│
├── main.py                                # Entry point: onboard → discover → propose triggers → listen → act
├── cli.py                                 # CLI commands: onboard, discover, status, triggers, journeys
├── migrate.py                             # Run SQL migrations
│
└── tests/
    ├── test_schema_scanner.py
    ├── test_concept_mapper.py
    ├── test_funnel_analyzer.py
    ├── test_trigger_evaluator.py
    ├── test_profile_builder.py
    ├── test_message_composer.py
    └── fixtures/                          # Mock schemas for testing (e-commerce, SaaS, Jeevz-like)
        ├── ecommerce_schema.json
        ├── saas_schema.json
        └── driver_service_schema.json
```

## ENVIRONMENT VARIABLES (.env)

```bash
# Customer PostgreSQL (READ ONLY)
CUSTOMER_DATABASE_URL=postgresql://readonly:****@db.example.com:5432/myapp

# GrowthClaw internal PostgreSQL (can be same DB with different schema, or separate)
GROWTHCLAW_DATABASE_URL=postgresql://growthclaw:****@db.example.com:5432/myapp

# LLM providers
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxx           # Primary (Nemotron)
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx       # Fallback (Claude)

# SMS
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_FROM_NUMBER=+15550123456

# GrowthClaw settings
GROWTHCLAW_BUSINESS_NAME=                           # Optional: helps LLM context ("Jeevz", "Acme Shop")
GROWTHCLAW_BUSINESS_DESCRIPTION=                    # Optional: one-line description
GROWTHCLAW_CARD_LINK_URL=https://app.example.com    # Deep link for activation CTA
GROWTHCLAW_MAX_FIRES_PER_TRIGGER=3
GROWTHCLAW_COOLDOWN_HOURS=24
GROWTHCLAW_QUIET_HOURS_START=21
GROWTHCLAW_QUIET_HOURS_END=8
GROWTHCLAW_DRY_RUN=true                             # MUST default to true
GROWTHCLAW_SAMPLE_ROWS=500                           # Rows to sample per table during discovery
```

## MIGRATION 001: GrowthClaw Internal Tables

These tables are business-agnostic. They store GrowthClaw's own state, not the customer's data.

```sql
CREATE SCHEMA IF NOT EXISTS growthclaw;

-- Schema discovery results
CREATE TABLE growthclaw.schema_map (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version         INTEGER NOT NULL DEFAULT 1,
    database_url_hash TEXT NOT NULL,              -- SHA256 of connection string (for identity, not stored in clear)
    business_name   TEXT,
    business_type   TEXT,                         -- LLM-inferred: "driver_service", "ecommerce", "saas", etc.
    tables          JSONB NOT NULL,               -- Full table/column/type inventory
    concepts        JSONB NOT NULL,               -- Mapped business concepts (see below)
    relationships   JSONB NOT NULL,               -- Entity relationship graph
    funnel          JSONB NOT NULL,               -- Discovered customer lifecycle funnel
    raw_statistics  JSONB,                        -- Row counts, distributions, null rates
    discovered_at   TIMESTAMPTZ DEFAULT NOW()
);

/*
concepts JSONB structure:
{
  "customer_table": "users",
  "customer_id_column": "id",
  "customer_name_column": "name",
  "customer_email_column": "email",
  "customer_phone_column": "phone_number",
  "customer_created_at_column": "created_at",
  "customer_status_column": "status",
  "customer_timezone_column": "time_zone",
  "customer_type_column": "type",
  "customer_type_value": "Client",
  "soft_delete_column": "deleted_at",
  "sms_consent_column": "accepted_sms_at",
  "push_token_column": "expo_push_token",

  "activation_table": "cards",
  "activation_event": "card added",
  "activation_fk_column": "user_id",
  "activation_check_sql": "SELECT EXISTS(SELECT 1 FROM cards WHERE user_id = $1 AND deleted_at IS NULL AND (removed IS NULL OR removed = false))",

  "transaction_table": "bookings",
  "transaction_fk_column": "user_id",
  "transaction_amount_column": "estimated_price_cents",
  "transaction_status_column": "status",
  "transaction_completed_value": "completed",
  "transaction_date_column": "requested_start_time",

  "subscription_table": "subscriptions",
  "subscription_fk_column": "client_id",
  "subscription_status_column": "status",
  "subscription_active_value": "active",
  "subscription_cancelled_value": "cancelled",
  "subscription_amount_column": "billing_rate_cents",
  "subscription_frequency_column": "billing_frequency",

  "attribution_table": "utms",
  "attribution_fk_column": "user_id",
  "attribution_source_column": "source",
  "attribution_campaign_column": "campaign"
}

funnel JSONB structure:
{
  "stages": [
    {"name": "signup", "table": "users", "event": "INSERT", "description": "User creates account"},
    {"name": "activation", "table": "cards", "event": "INSERT", "description": "User adds payment card"},
    {"name": "first_transaction", "table": "bookings", "event": "INSERT WHERE status='completed'", "description": "User completes first booking"},
    {"name": "subscription", "table": "subscriptions", "event": "INSERT", "description": "User starts subscription"},
    {"name": "repeat_transaction", "table": "bookings", "event": "trips_count > 1", "description": "User books again"}
  ],
  "biggest_dropoff": {
    "from_stage": "signup",
    "to_stage": "activation",
    "conversion_rate": 0.13,
    "description": "87% of signups never add a payment card"
  }
}
*/

-- Trigger configurations (LLM-proposed, human-approved)
CREATE TABLE growthclaw.triggers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,                -- e.g., "signup_no_activation"
    description     TEXT NOT NULL,                -- Human-readable
    watch_table     TEXT NOT NULL,                -- Table to watch
    watch_event     TEXT NOT NULL,                -- INSERT, UPDATE, DELETE
    watch_condition TEXT,                         -- Optional SQL condition on NEW/OLD
    delay_minutes   INTEGER NOT NULL DEFAULT 30,
    check_sql       TEXT NOT NULL,                -- SQL to run after delay (has the user activated?)
    profile_queries JSONB NOT NULL,               -- SQL queries to build the customer profile
    message_context TEXT NOT NULL,                -- Context string for the LLM message composer
    channel         TEXT NOT NULL DEFAULT 'sms',
    max_fires       INTEGER NOT NULL DEFAULT 3,
    cooldown_hours  INTEGER NOT NULL DEFAULT 24,
    status          TEXT NOT NULL DEFAULT 'proposed',  -- proposed | approved | active | paused
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- CDC trigger install log (tracks what PG triggers we've installed on customer DB)
CREATE TABLE growthclaw.installed_triggers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name      TEXT NOT NULL,
    trigger_name    TEXT NOT NULL,
    function_name   TEXT NOT NULL,
    installed_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(table_name, trigger_name)
);

-- Real-time event log
CREATE TABLE growthclaw.events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,                -- Always stored as TEXT for portability
    table_name      TEXT NOT NULL,
    operation       TEXT NOT NULL,
    trigger_id      UUID REFERENCES growthclaw.triggers(id),
    payload         JSONB NOT NULL,
    processed       BOOLEAN DEFAULT FALSE,
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_gc_events_unprocessed ON growthclaw.events(processed, created_at) WHERE processed = FALSE;

-- Customer profiles (cached)
CREATE TABLE growthclaw.profiles (
    user_id         TEXT PRIMARY KEY,
    raw_data        JSONB NOT NULL,               -- The query results
    analysis        JSONB NOT NULL,               -- LLM intelligence brief
    computed_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Journey log (every outreach)
CREATE TABLE growthclaw.journeys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    trigger_id      UUID REFERENCES growthclaw.triggers(id),
    event_id        UUID REFERENCES growthclaw.events(id),
    channel         TEXT NOT NULL,
    contact_info    TEXT,                          -- Phone number or email (resolved at send time)
    message_body    TEXT NOT NULL,
    provider_id     TEXT,                          -- Twilio SID, SendGrid message ID, etc.
    status          TEXT DEFAULT 'composed',       -- composed | approved | sent | delivered | failed
    experiment_id   UUID,
    experiment_arm  TEXT,
    llm_reasoning   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    sent_at         TIMESTAMPTZ,
    outcome         TEXT,                          -- converted | ignored | unsubscribed
    outcome_at      TIMESTAMPTZ
);
CREATE INDEX idx_gc_journeys_user ON growthclaw.journeys(user_id, created_at DESC);
CREATE INDEX idx_gc_journeys_outcome_pending ON growthclaw.journeys(outcome, sent_at)
    WHERE outcome IS NULL AND sent_at IS NOT NULL;

-- Trigger cooldown state
CREATE TABLE growthclaw.trigger_state (
    user_id         TEXT NOT NULL,
    trigger_id      UUID NOT NULL REFERENCES growthclaw.triggers(id),
    fire_count      INTEGER DEFAULT 0,
    last_fired_at   TIMESTAMPTZ,
    PRIMARY KEY (user_id, trigger_id)
);

-- Experiments
CREATE TABLE growthclaw.experiments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    trigger_id      UUID REFERENCES growthclaw.triggers(id),
    variable        TEXT NOT NULL,
    arms            JSONB NOT NULL,
    metric          TEXT NOT NULL,
    status          TEXT DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE growthclaw.experiment_results (
    experiment_id   UUID REFERENCES growthclaw.experiments(id),
    arm_name        TEXT NOT NULL,
    total_sent      INTEGER DEFAULT 0,
    total_converted INTEGER DEFAULT 0,
    conversion_rate FLOAT,
    last_updated    TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (experiment_id, arm_name)
);
```

## THE DISCOVERY ENGINE (This is the heart of GrowthClaw)

### Step 1: schema_scanner.py

Connect to the customer database and extract everything:

```python
async def scan_schema(db_url: str) -> RawSchema:
    """
    Query information_schema and pg_catalog to extract:
    - All tables (excluding system tables)
    - All columns with types, nullability, defaults
    - All foreign key relationships
    - Row counts per table (pg_stat_user_tables or COUNT(*))
    - Primary key columns per table
    """
    # Query 1: Tables
    tables = await conn.fetch("""
        SELECT t.table_name,
               (SELECT reltuples::bigint FROM pg_class WHERE relname = t.table_name) as approx_rows
        FROM information_schema.tables t
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
    """)

    # Query 2: Columns per table
    columns = await conn.fetch("""
        SELECT table_name, column_name, data_type, udt_name,
               is_nullable, column_default, character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """)

    # Query 3: Foreign keys
    fks = await conn.fetch("""
        SELECT
            tc.table_name, kcu.column_name,
            ccu.table_name AS references_table,
            ccu.column_name AS references_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu USING (constraint_name, table_schema)
        JOIN information_schema.constraint_column_usage ccu USING (constraint_name, table_schema)
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
    """)

    # Query 4: Primary keys
    pks = await conn.fetch("""
        SELECT kcu.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu USING (constraint_name, table_schema)
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
    """)

    return RawSchema(tables=tables, columns=columns, foreign_keys=fks, primary_keys=pks)
```

### Step 2: data_sampler.py

For tables with >0 rows, sample data to understand distributions:

```python
async def sample_table(conn, table_name: str, sample_size: int = 500) -> TableSample:
    """
    For each column:
    - Distinct count
    - Null count / null rate
    - For text: top 10 most common values + counts
    - For numeric: min, max, avg, median
    - For timestamp: min, max, most recent
    - For boolean: true/false counts
    """
    # Use a single query with aggregate functions per column type
    # Build dynamic SQL based on column types
    ...
```

### Step 3: concept_mapper.py — THE KEY COMPONENT

This is where GrowthClaw becomes intelligent. Feed the full schema + sample data to the LLM and ask it to map business concepts.

**Prompt template (prompts/classify_schema.j2):**

```
You are a database analyst. You've been given the complete schema of a business's
PostgreSQL database. Your job is to classify each table's business role and identify
the key business concepts.

{% if business_name %}This database belongs to: {{ business_name }}{% endif %}
{% if business_description %}Business description: {{ business_description }}{% endif %}

SCHEMA:
{% for table in tables %}
Table: {{ table.name }} ({{ table.row_count }} rows)
Columns:
{% for col in table.columns %}
  - {{ col.name }} ({{ col.type }}{% if col.nullable == 'NO' %}, NOT NULL{% endif %}{% if col.default %}, default: {{ col.default }}{% endif %})
    {% if col.sample_values %}Sample values: {{ col.sample_values[:5] }}{% endif %}
    {% if col.null_rate is not none %}Null rate: {{ (col.null_rate * 100)|round(1) }}%{% endif %}
{% endfor %}
Foreign keys: {% for fk in table.foreign_keys %}{{ fk.column }} → {{ fk.references_table }}.{{ fk.references_column }}{% endfor %}

{% endfor %}

Respond with JSON:
{
  "business_type": "string — ecommerce | saas | marketplace | driver_service | healthcare | fintech | other",
  "business_description": "One sentence describing what this business does, inferred from the data",

  "customer_table": "table name where customers/users live",
  "customer_id_column": "primary key column",
  "customer_name_column": "name or full_name column, or null",
  "customer_email_column": "email column, or null",
  "customer_phone_column": "phone number column, or null",
  "customer_created_at_column": "signup/creation timestamp column",
  "customer_status_column": "status or state column, or null",
  "customer_timezone_column": "timezone column, or null",
  "customer_type_column": "column that distinguishes customer types (e.g., role, type), or null",
  "customer_type_value": "the value that means 'customer' (e.g., 'Client', 'customer', 'buyer'), or null",
  "soft_delete_column": "deleted_at or similar, or null",
  "exclude_filters": ["SQL conditions to exclude test/system accounts, e.g., 'system_account IS NOT TRUE'"],

  "sms_consent_column": "column indicating SMS opt-in (timestamp or boolean), or null",
  "sms_consent_check": "SQL expression that means 'this user consented to SMS', e.g., 'accepted_sms_at IS NOT NULL'",
  "push_token_column": "push notification token column, or null",

  "activation_table": "table where the key activation event lives (e.g., cards, payments, orders)",
  "activation_event": "human-readable description of what activation means",
  "activation_fk_column": "FK column pointing to customer",
  "activation_check_sql": "SQL that returns TRUE if customer has activated — use $1 as customer ID placeholder",
  "activation_soft_delete": "soft delete filter for activation table, or null",

  "transaction_table": "table where transactions/orders/bookings live, or null",
  "transaction_fk_column": "FK to customer, or null",
  "transaction_amount_column": "monetary amount column (cents or dollars), or null",
  "transaction_amount_is_cents": true,
  "transaction_status_column": "status column, or null",
  "transaction_completed_value": "value meaning completed, or null",
  "transaction_date_column": "date/time column, or null",

  "subscription_table": "recurring revenue table, or null",
  "subscription_fk_column": "FK to customer, or null",
  "subscription_status_column": "status column, or null",
  "subscription_active_value": "value meaning active, or null",
  "subscription_cancelled_value": "value meaning cancelled, or null",
  "subscription_amount_column": "price/rate column, or null",
  "subscription_frequency_column": "billing frequency column, or null",

  "attribution_table": "UTM or attribution tracking table, or null",
  "attribution_fk_column": "FK to customer, or null",
  "attribution_source_column": "source column, or null",
  "attribution_campaign_column": "campaign column, or null",

  "additional_profile_tables": [
    {
      "table": "table_name",
      "fk_column": "FK to customer",
      "useful_columns": ["col1", "col2"],
      "description": "why this table is useful for customer profiling"
    }
  ]
}
```

### Step 4: funnel_analyzer.py

**Prompt template (prompts/analyze_funnel.j2):**

```
You are analyzing a business's customer lifecycle funnel.

BUSINESS: {{ business_type }} — {{ business_description }}

CONCEPT MAP:
{{ concepts | tojson(indent=2) }}

DATA STATISTICS:
- Total customers: {{ customer_count }}
- Customers with activation ({{ activation_event }}): {{ activated_count }} ({{ activation_rate }}%)
- Customers with transactions: {{ transacted_count }}
- Customers with subscriptions: {{ subscribed_count }}
- Customers with SMS consent: {{ sms_consent_count }}

TIME ANALYSIS:
{{ time_to_activation_distribution | tojson(indent=2) }}

Respond with JSON:
{
  "funnel_stages": [
    {"name": "string", "table": "string", "event": "string", "count": number, "description": "string"}
  ],
  "biggest_dropoff": {
    "from_stage": "string",
    "to_stage": "string",
    "conversion_rate": number,
    "lost_customers": number,
    "description": "string — explain the business impact"
  },
  "activation_window": {
    "optimal_minutes": number,
    "reasoning": "string — based on the time-to-activation distribution"
  },
  "reachability": {
    "sms_reachable_in_dropoff": number,
    "email_reachable_in_dropoff": number,
    "push_reachable_in_dropoff": number
  }
}
```

### Step 5: trigger_proposer.py

**Prompt template (prompts/propose_triggers.j2):**

```
You are designing real-time marketing triggers for a {{ business_type }}.

BUSINESS: {{ business_description }}
FUNNEL: {{ funnel | tojson(indent=2) }}
CONCEPT MAP: {{ concepts | tojson(indent=2) }}
BIGGEST DROPOFF: {{ biggest_dropoff | tojson(indent=2) }}

Propose 3-5 trigger rules, prioritized by expected revenue impact.
For each trigger, generate the ACTUAL SQL that GrowthClaw will use.
Use $1 as the customer ID placeholder in all SQL.

Respond with JSON array:
[
  {
    "name": "snake_case_name",
    "description": "Human-readable description",
    "priority": 1,
    "watch_table": "table to watch for changes",
    "watch_event": "INSERT or UPDATE",
    "watch_condition": "SQL condition on NEW row, or null",
    "delay_minutes": number,
    "check_sql": "SQL returning TRUE if the user still hasn't done the thing — use $1 for user_id",
    "profile_queries": [
      {
        "name": "descriptive_name",
        "sql": "SELECT ... FROM ... WHERE user_id = $1 OR similar",
        "description": "what this query retrieves"
      }
    ],
    "message_context": "Context string for the LLM when composing the message. Describe the situation, what we know, and what we want the user to do.",
    "channel": "sms or email",
    "user_id_source": "How to extract user_id from the CDC event — e.g., 'NEW.id' for users table, 'NEW.user_id' for others",
    "expected_audience_per_week": number,
    "expected_conversion_lift": "low | medium | high",
    "reasoning": "Why this trigger, why this timing"
  }
]
```

### Step 6: trigger_installer.py

Dynamically generate and install PostgreSQL triggers based on the proposed trigger rules:

```python
async def install_trigger(conn, trigger: TriggerRule, concepts: dict) -> str:
    """
    Generate a PG trigger function + trigger for a specific table.
    The trigger fires pg_notify('growthclaw_events', payload).

    CRITICAL: The trigger function must extract user_id correctly
    based on the table. For the customer table, user_id = NEW.id.
    For other tables, user_id = NEW.{fk_column}.
    """
    function_name = f"growthclaw_notify_{trigger.watch_table}"
    trigger_name = f"gc_{trigger.watch_table}_change"

    # Determine how to extract user_id from this table
    if trigger.watch_table == concepts["customer_table"]:
        user_id_expr = f"NEW.{concepts['customer_id_column']}"
    else:
        user_id_expr = f"NEW.{trigger.user_id_source}"

    function_sql = f"""
    CREATE OR REPLACE FUNCTION growthclaw.{function_name}()
    RETURNS TRIGGER AS $
    BEGIN
      PERFORM pg_notify('growthclaw_events', json_build_object(
        'table', TG_TABLE_NAME,
        'op', TG_OP,
        'ts', NOW(),
        'row_id', NEW.{concepts.get('customer_id_column', 'id')}::text,
        'user_id', {user_id_expr}::text,
        'trigger_id', '{trigger.id}'
      )::text);
      RETURN NEW;
    END;
    $ LANGUAGE plpgsql;
    """

    trigger_sql = f"""
    DROP TRIGGER IF EXISTS {trigger_name} ON public.{trigger.watch_table};
    CREATE TRIGGER {trigger_name}
      AFTER {trigger.watch_event} ON public.{trigger.watch_table}
      FOR EACH ROW EXECUTE FUNCTION growthclaw.{function_name}();
    """

    await conn.execute(function_sql)
    await conn.execute(trigger_sql)
    return trigger_name
```

### Step 7: profile_builder.py (GENERIC — no hardcoded queries)

```python
async def build_profile(conn, user_id: str, trigger: TriggerRule, concepts: dict) -> dict:
    """
    Execute the profile queries defined in the trigger config.
    These queries were generated by the LLM during trigger proposal
    and are specific to the discovered schema.
    """
    profile_data = {}
    for query_def in trigger.profile_queries:
        try:
            rows = await conn.fetch(query_def["sql"], user_id)
            profile_data[query_def["name"]] = [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Profile query '{query_def['name']}' failed: {e}")
            profile_data[query_def["name"]] = None

    return profile_data
```

### Step 8: message_composer.py (GENERIC — business context from discovery)

**Prompt template (prompts/compose_message.j2):**

```
You are writing a single {{ channel }} message to a customer of {{ business_name }},
a {{ business_type }} business: {{ business_description }}.

SITUATION: {{ trigger.message_context }}

CUSTOMER PROFILE:
{{ profile_data | tojson(indent=2) }}

RULES:
{% if channel == 'sms' %}
- Under 160 characters total (STRICT)
- Include the CTA link: {{ cta_link }}
{% elif channel == 'email' %}
- Write subject line + 3-5 sentence body
{% endif %}
- Sound like a helpful human, not a marketing bot
- Reference specific things we know about them from the profile
- DO NOT mention AI, algorithms, or data analysis
- DO NOT use ALL CAPS or excessive punctuation
- Match the urgency: this person {{ trigger.description | lower }}

Return ONLY the message text. Nothing else.
```

## THE ONBOARDING FLOW (main.py / cli.py)

```python
async def onboard():
    """
    The complete onboarding sequence. Each step builds on the previous.
    Results are persisted so the system can restart without re-discovering.
    """
    print("🐾 GrowthClaw — Connecting to your database...\n")

    # Step 1: Scan schema
    print("[1/6] Scanning database schema...")
    raw_schema = await schema_scanner.scan(CUSTOMER_DATABASE_URL)
    print(f"  Found {len(raw_schema.tables)} tables, {sum(len(t.columns) for t in raw_schema.tables)} columns\n")

    # Step 2: Sample data
    print("[2/6] Sampling data distributions...")
    samples = await data_sampler.sample_all(raw_schema)
    print(f"  Sampled {len(samples)} tables with data\n")

    # Step 3: LLM classifies schema
    print("[3/6] Understanding your business...")
    concepts = await concept_mapper.map_concepts(raw_schema, samples)
    print(f"  Business type: {concepts.business_type}")
    print(f"  Customer table: {concepts.customer_table}")
    print(f"  Activation event: {concepts.activation_event}\n")

    # Step 4: Analyze funnel
    print("[4/6] Analyzing customer funnel...")
    funnel = await funnel_analyzer.analyze(concepts, raw_schema)
    print(f"  Funnel stages: {' → '.join(s.name for s in funnel.stages)}")
    print(f"  Biggest drop-off: {funnel.biggest_dropoff.description}\n")

    # Step 5: Propose triggers
    print("[5/6] Proposing growth triggers...")
    triggers = await trigger_proposer.propose(concepts, funnel)
    for i, t in enumerate(triggers, 1):
        print(f"  {i}. [{t.channel.upper()}] {t.name}: {t.description}")
        print(f"     Delay: {t.delay_minutes}min | Expected audience: ~{t.expected_audience_per_week}/week")
    print()

    # Step 6: Persist everything
    print("[6/6] Saving configuration...")
    await schema_store.save(raw_schema, concepts, funnel)
    await trigger_store.save_all(triggers)

    # Print summary
    print("\n✅ GrowthClaw discovery complete!\n")
    print(f"  Business: {concepts.business_type} — {concepts.business_description}")
    print(f"  Customers: {funnel.stages[0].count:,}")
    print(f"  Biggest opportunity: {funnel.biggest_dropoff.description}")
    print(f"  {len(triggers)} triggers proposed\n")
    print("Next steps:")
    print("  growthclaw triggers approve    # Review and approve proposed triggers")
    print("  growthclaw start               # Install CDC triggers and start listening")
    print("  growthclaw status              # Check system health")
```

## CLI COMMANDS (cli.py)

```
growthclaw onboard              Run full discovery + analysis + trigger proposal
growthclaw discover             Re-run schema discovery only
growthclaw triggers list        Show all proposed/active triggers
growthclaw triggers approve     Interactive approval of proposed triggers
growthclaw triggers approve --all   Approve all proposed triggers
growthclaw start                Install CDC triggers and start the event loop
growthclaw stop                 Stop listening (remove CDC triggers)
growthclaw status               Health check: DB connection, active triggers, recent events
growthclaw journeys             Show recent outreach with outcomes
growthclaw experiments          Show experiment results
growthclaw export               Export schema_map, triggers, and results as JSON
```

## BUILD ORDER

Implement in this exact order. Each step is testable independently:

1. **config.py** + **.env.example** — Load and validate all env vars with Pydantic Settings
2. **models/** — All Pydantic models (SchemaMap, TriggerRule, CustomerProfile, Journey, Experiment)
3. **llm/client.py** + **nvidia_nim.py** + **anthropic_fallback.py** — Unified LLM interface with provider selection
4. **migrations/001_create_growthclaw_schema.sql** + **migrate.py** — Create internal tables
5. **prompts/** — All Jinja2 prompt templates
6. **discovery/schema_scanner.py** — PG introspection (write test with mock schema)
7. **discovery/data_sampler.py** — Sample distributions
8. **discovery/concept_mapper.py** — LLM classification (write test with mock LLM response)
9. **discovery/funnel_analyzer.py** — LLM funnel analysis
10. **discovery/relationship_resolver.py** — FK graph building
11. **discovery/schema_store.py** — Persist to growthclaw.schema_map
12. **triggers/trigger_proposer.py** — LLM proposes triggers
13. **triggers/trigger_store.py** — Persist triggers
14. **triggers/trigger_installer.py** — Generate + install PG triggers
15. **triggers/cdc_listener.py** — LISTEN/NOTIFY consumer
16. **triggers/trigger_evaluator.py** — Cooldown/consent/quiet hour checks
17. **intelligence/profile_builder.py** — Execute profile queries from trigger config
18. **intelligence/profile_analyzer.py** — LLM profile analysis
19. **outreach/channel_resolver.py** — Determine contact channel + info from concepts
20. **outreach/message_composer.py** — LLM message generation
21. **outreach/sms_sender.py** — Twilio delivery
22. **outreach/journey_store.py** — Log outreach
23. **experiments/experiment_manager.py** — Arm assignment + experiment creation
24. **experiments/outcome_checker.py** — Poll for conversions
25. **experiments/experiment_store.py** — Persist results
26. **main.py** — Wire everything together: onboard → listen → act
27. **cli.py** — CLI commands
28. **tests/** — Tests for scanner, concept mapper, trigger evaluator, profile builder, message composer
29. **README.md** — Setup instructions, architecture overview, CLI reference

## IMPORTANT CONSTRAINTS

1. **ZERO hardcoded business logic.** No table names, column names, or SQL queries that reference a specific business. Everything is discovered at runtime or stored in growthclaw.triggers.
2. **NEVER write to customer tables.** Only write to the `growthclaw` schema. The only exception is installing trigger FUNCTIONS in the `growthclaw` schema and TRIGGERS on customer tables (which is read-only — triggers just fire NOTIFY).
3. **DRY_RUN=true by default.** Log everything, send nothing.
4. **LLM prompts are Jinja2 templates** stored in `prompts/`. Never inline prompt strings in Python code.
5. **Every LLM call is logged.** Store the prompt, response, and latency for debugging.
6. **Graceful degradation.** If the LLM produces invalid JSON, retry once with a "fix this JSON" prompt. If it fails again, log the error and skip (don't crash).
7. **Idempotent.** Re-running `onboard` should update existing records, not duplicate them. Re-running `start` should not install duplicate triggers.
8. **The concepts JSON is the single source of truth** for how GrowthClaw understands the customer's database. Every other component reads from it. If you change the concepts, everything downstream adapts.
9. **Test fixtures include three mock schemas** (e-commerce, SaaS, driver-service) so tests prove the system is truly generic.

## WHAT SUCCESS LOOKS LIKE

When you point GrowthClaw at the Jeevz database and run `growthclaw onboard`, it should:

1. Discover 60 tables and classify them correctly
2. Identify `users` as the customer table, `cards` as the activation table, `bookings` as the transaction table
3. Calculate that 87% of signups never activate
4. Determine that the optimal nudge window is ~30 minutes (based on the 72.3% within-1-hour conversion data)
5. Propose "signup_no_activation" as the #1 priority trigger
6. Generate correct SQL for profile queries and activation checks — without ever having seen the Jeevz schema before in its code

When you then point it at a Shopify-like database with `orders`, `customers`, and `checkouts`, it should work equally well — discovering that `checkouts` with `completed_at IS NULL` are abandoned carts, and proposing a cart abandonment trigger.
