# GrowthClaw Phase 2 — Claude Code Implementation Prompt

## CONTEXT: What Phase 1 Built

Phase 1 is complete and working. Here's what exists:

**Discovery Engine** (`discovery/`): schema_scanner, data_sampler, concept_mapper, relationship_resolver, funnel_analyzer, schema_store. Connects to any PostgreSQL, introspects the full schema, uses LLM to classify tables into business concepts, analyzes the customer lifecycle funnel, and persists everything to `growthclaw.schema_map`.

**Trigger System** (`triggers/`): trigger_proposer, trigger_installer, trigger_evaluator, cdc_listener, trigger_store. LLM proposes trigger rules from the discovered funnel. Triggers are installed as PG NOTIFY functions. CDC listener consumes events in real time. Evaluator enforces cooldowns, consent, quiet hours, max fires.

**Intelligence** (`intelligence/`): profile_builder, profile_analyzer, profile_store. Builds a 360° customer profile from LLM-generated SQL queries. LLM produces an IntelligenceBrief (segment, engagement, tone, CTA, risks). Profiles cached with 24h TTL.

**Outreach** (`outreach/`): message_composer, channel_resolver, journey_store, sms_sender. LLM composes personalized messages. SMS length enforced at 160 chars with retry + truncation. Channel resolver finds contact info from discovered schema. Journeys logged with full provenance.

**Experiments** (`experiments/`): experiment_manager, experiment_store, outcome_checker. A/B tests on trigger delay (3 arms). Deterministic arm assignment. Outcome polling every 5 minutes.

**LLM Layer** (`llm/`): Unified client with NVIDIA NIM primary, Anthropic Claude fallback. JSON parsing with retry. Jinja2 prompt templates in `prompts/`.

**CLI** (`cli.py`): 8 commands — onboard, discover, triggers list/approve, start, stop, status, journeys, experiments, export, migrate.

**Models** (`models/`): Pydantic v2 schemas for SchemaMap, BusinessConcepts, TriggerRule, CustomerProfile, IntelligenceBrief, Journey, Experiment.

**Tests**: 6 test modules, 100+ test cases, 3 schema fixtures (ecommerce, SaaS, driver_service).

**Key Architecture Decisions:**
- Zero hardcoded business logic — everything discovered via LLM at runtime
- `concepts` JSON is the single source of truth
- Customer DB is read-only (only NOTIFY triggers installed)
- All GrowthClaw state in `growthclaw` schema
- DRY_RUN=true by default
- All LLM prompts in `prompts/*.j2`, never inline

---

## GOAL: What Phase 2 Adds

Phase 2 adds four capabilities that take GrowthClaw from "single-trigger SMS nudge" to "multi-channel autonomous marketing platform":

1. **Email Channel** — SendGrid integration with HTML email composition
2. **Multi-Trigger Orchestration** — Multiple triggers running simultaneously with cross-trigger frequency capping
3. **AutoResearch Loop** — Karpathy-pattern autonomous experimentation that tests message content, tone, offers, and channels (not just delay)
4. **Dashboard** — Streamlit web UI showing live triggers, journeys, experiments, and funnel metrics

---

## PHASE 2A: Email Channel

### New Files

```
growthclaw/outreach/email_sender.py        # SendGrid integration
growthclaw/prompts/compose_email.j2        # Email-specific prompt (subject + HTML body)
```

### Changes to Existing Files

**config.py** — Add SendGrid settings:
```python
# SendGrid Email
sendgrid_api_key: str | None = Field(default=None, alias="SENDGRID_API_KEY")
sendgrid_from_email: str | None = Field(default=None, alias="SENDGRID_FROM_EMAIL")
sendgrid_from_name: str | None = Field(default=None, alias="SENDGRID_FROM_NAME")
```

**pyproject.toml** — Add dependency:
```
"sendgrid>=6.11.0",
```

**.env.example** — Add:
```bash
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxx
SENDGRID_FROM_EMAIL=hello@yourbusiness.com
SENDGRID_FROM_NAME=GrowthClaw
```

### email_sender.py Implementation

```python
"""SendGrid email delivery."""

import structlog
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent

logger = structlog.get_logger()


class EmailSender:
    def __init__(self, api_key: str | None, from_email: str | None, from_name: str | None, dry_run: bool = True):
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self.dry_run = dry_run
        self._client: SendGridAPIClient | None = None

    @property
    def client(self) -> SendGridAPIClient:
        if self._client is None:
            if not self.api_key:
                raise ValueError("SENDGRID_API_KEY is required to send email")
            self._client = SendGridAPIClient(api_key=self.api_key)
        return self._client

    async def send(self, to_email: str, subject: str, html_body: str, plain_text: str | None = None) -> str | None:
        """Send email via SendGrid. Returns message ID or None if dry run."""
        if self.dry_run:
            logger.info("email.dry_run", to=to_email, subject=subject, body_length=len(html_body))
            return None

        message = Mail(
            from_email=Email(self.from_email, self.from_name),
            to_emails=To(to_email),
            subject=subject,
            html_content=HtmlContent(html_body),
        )
        if plain_text:
            message.add_content(Content("text/plain", plain_text))

        try:
            response = self.client.send(message)
            message_id = response.headers.get("X-Message-Id", "unknown")
            logger.info("email.sent", to=to_email, subject=subject, message_id=message_id,
                        status_code=response.status_code)
            return message_id
        except Exception:
            logger.exception("email.send_failed", to=to_email, subject=subject)
            raise
```

### compose_email.j2 Prompt Template

Create `growthclaw/prompts/compose_email.j2`:

```
You are writing a personalized email to a customer of {{ business_name }},
a {{ business_type }} business: {{ business_description }}.

SITUATION: {{ trigger.message_context }}

CUSTOMER INTELLIGENCE:
{{ intelligence_brief | tojson(indent=2) }}

CUSTOMER DATA:
{{ profile_data | tojson(indent=2) }}

CTA LINK: {{ cta_link }}

RULES:
- Write a subject line (under 60 characters) and an HTML email body
- The body should be 3-6 sentences, warm and personal
- Use simple HTML: <p> tags, one <a> tag for the CTA, optional <strong> for emphasis
- DO NOT use complex HTML layouts, tables, or images
- DO NOT include unsubscribe links (those are added by SendGrid automatically)
- Sound like a helpful human, not a marketing bot
- Reference specific things we know about the customer from their profile
- DO NOT mention AI, algorithms, or data analysis
- Recommended tone: {{ intelligence_brief.recommended_tone }}
- Recommended CTA: {{ intelligence_brief.recommended_cta }}

Respond with JSON:
{
  "subject": "the subject line",
  "html_body": "<p>The email body in simple HTML</p>",
  "plain_text": "Plain text version of the email"
}
```

### Changes to message_composer.py

Add an `compose_email` function that uses the new template:

```python
async def compose_email(
    trigger: TriggerRule,
    profile_data: dict,
    intelligence_brief: IntelligenceBrief,
    concepts: BusinessConcepts,
    llm_client: LLMClient,
    cta_link: str,
    business_name: str,
) -> dict:
    """Compose a personalized email. Returns {"subject": str, "html_body": str, "plain_text": str}."""
    prompt = render_template(
        "compose_email.j2",
        trigger=trigger,
        profile_data=profile_data,
        intelligence_brief=intelligence_brief.model_dump(),
        business_type=concepts.business_type or "business",
        business_description=concepts.business_description or "",
        cta_link=cta_link,
        business_name=business_name,
    )
    result = await llm_client.call_json(prompt, temperature=0.7)
    return result
```

### Changes to main.py (_delayed_evaluate)

After the compose step, branch on channel:

```python
if contact.channel == "sms" and contact.is_reachable:
    # existing SMS flow
    ...
elif contact.channel == "email" and contact.is_reachable:
    email_result = await compose_email(trigger, profile_data, analysis, concepts, self.llm, ...)
    journey = Journey(
        channel="email",
        message_body=email_result["html_body"],
        ...
    )
    journey_id = await journey_store.create(internal_conn, journey)
    msg_id = await self.email_sender.send(
        to_email=contact.value,
        subject=email_result["subject"],
        html_body=email_result["html_body"],
        plain_text=email_result.get("plain_text"),
    )
    await journey_store.update_sent(internal_conn, journey_id, msg_id or "dry_run")
```

### Changes to channel_resolver.py

Update `resolve()` to support email as a first-class channel. If trigger.channel is "email", look up the customer's email column from concepts. No consent check required for email (CAN-SPAM relies on unsubscribe, not pre-consent — but we should still check a suppression list if one exists).

Add a `growthclaw.suppressions` table (see migration below) and check it before sending:

```python
async def is_suppressed(conn, user_id: str, channel: str) -> bool:
    """Check if user has opted out of this channel."""
    row = await conn.fetchrow(
        "SELECT 1 FROM growthclaw.suppressions WHERE user_id = $1 AND channel = $2",
        user_id, channel
    )
    return row is not None
```

---

## PHASE 2B: Multi-Trigger Orchestration

### Problem

Phase 1 runs one trigger at a time. Phase 2 needs to run 4-6 triggers simultaneously without over-messaging customers.

### New: Global Frequency Cap

Add a **cross-trigger frequency cap** that prevents any customer from receiving more than N messages per channel per time window, regardless of which triggers fire.

**New table** (add to migration):
```sql
CREATE TABLE growthclaw.suppressions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    channel         TEXT NOT NULL,           -- 'sms', 'email', 'push'
    reason          TEXT NOT NULL,           -- 'unsubscribed', 'complained', 'bounced', 'manual'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, channel)
);

CREATE TABLE growthclaw.global_frequency (
    user_id         TEXT NOT NULL,
    channel         TEXT NOT NULL,
    sent_at         TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_gc_freq_user_channel ON growthclaw.global_frequency(user_id, channel, sent_at DESC);
```

**New file: `triggers/frequency_manager.py`**

```python
"""Cross-trigger frequency capping."""

import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger()


async def check_global_frequency(
    conn, user_id: str, channel: str,
    max_per_day: int = 2, max_per_week: int = 5
) -> bool:
    """Return True if user is WITHIN frequency limits (OK to send)."""
    day_count = await conn.fetchval(
        "SELECT COUNT(*) FROM growthclaw.global_frequency "
        "WHERE user_id = $1 AND channel = $2 AND sent_at > NOW() - INTERVAL '24 hours'",
        user_id, channel
    )
    if day_count >= max_per_day:
        logger.info("frequency.daily_cap_hit", user_id=user_id, channel=channel, count=day_count)
        return False

    week_count = await conn.fetchval(
        "SELECT COUNT(*) FROM growthclaw.global_frequency "
        "WHERE user_id = $1 AND channel = $2 AND sent_at > NOW() - INTERVAL '7 days'",
        user_id, channel
    )
    if week_count >= max_per_week:
        logger.info("frequency.weekly_cap_hit", user_id=user_id, channel=channel, count=week_count)
        return False

    return True


async def record_send(conn, user_id: str, channel: str) -> None:
    """Record a send for frequency tracking."""
    await conn.execute(
        "INSERT INTO growthclaw.global_frequency (user_id, channel, sent_at) VALUES ($1, $2, NOW())",
        user_id, channel
    )
```

### Changes to config.py

```python
# Frequency caps (global, across all triggers)
max_sms_per_day: int = Field(default=2, alias="GROWTHCLAW_MAX_SMS_PER_DAY")
max_sms_per_week: int = Field(default=5, alias="GROWTHCLAW_MAX_SMS_PER_WEEK")
max_email_per_day: int = Field(default=2, alias="GROWTHCLAW_MAX_EMAIL_PER_DAY")
max_email_per_week: int = Field(default=7, alias="GROWTHCLAW_MAX_EMAIL_PER_WEEK")
```

### Changes to main.py (_delayed_evaluate)

Before sending, add two checks:
1. `is_suppressed()` — has the user unsubscribed from this channel?
2. `check_global_frequency()` — are we within the daily/weekly cap?

If either fails, log the journey as `status='suppressed'` and skip sending.

### Changes to trigger_store.py

The `get_active()` function already returns all active triggers. No changes needed — the CDC listener already dispatches events to all matching triggers. But verify that when multiple triggers watch the same table, each event is matched to the correct trigger by `trigger_id` in the NOTIFY payload.

### Changes to trigger_installer.py

Currently, each trigger installs a separate PG function per table. If two triggers watch the same table (e.g., `signup_no_activation` and `signup_no_booking` both watch `users` INSERT), they'd install two functions with the same name, overwriting each other.

**Fix:** Install ONE function per table that includes ALL trigger IDs for that table, and fire a separate NOTIFY per trigger:

```python
async def install_triggers_for_table(customer_conn, internal_conn, triggers_for_table: list[TriggerRule], concepts):
    """Install a SINGLE PG function for all triggers on this table."""
    table_name = triggers_for_table[0].watch_table
    function_name = f"growthclaw_notify_{table_name}"

    # Build the function body with one NOTIFY per trigger
    notify_blocks = []
    for trigger in triggers_for_table:
        condition = f"IF {trigger.watch_condition} THEN" if trigger.watch_condition else ""
        end_if = "END IF;" if trigger.watch_condition else ""
        user_id_expr = _resolve_user_id_expr(trigger, concepts)

        notify_blocks.append(f"""
        {condition}
        PERFORM pg_notify('growthclaw_events', json_build_object(
            'table', TG_TABLE_NAME, 'op', TG_OP, 'ts', NOW(),
            'row_id', NEW.id::text,
            'user_id', {user_id_expr}::text,
            'trigger_id', '{trigger.id}'
        )::text);
        {end_if}
        """)

    function_sql = f"""
    CREATE OR REPLACE FUNCTION growthclaw.{function_name}()
    RETURNS TRIGGER AS $$
    BEGIN
      {''.join(notify_blocks)}
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    # ... create trigger as before
```

---

## PHASE 2C: AutoResearch Loop

### The Big Upgrade

Phase 1 experiments only test delay timing (15/30/60 min). Phase 2 implements the full Karpathy AutoResearch pattern: the system autonomously generates hypotheses, creates test variants, deploys them, measures results, and promotes winners — continuously.

### New Files

```
growthclaw/autoresearch/__init__.py
growthclaw/autoresearch/loop.py                 # The main AutoResearch loop
growthclaw/autoresearch/hypothesis_generator.py  # LLM proposes what to test next
growthclaw/autoresearch/variant_creator.py       # LLM creates test content variants
growthclaw/autoresearch/evaluator.py             # Statistical significance testing
growthclaw/prompts/generate_hypothesis.j2        # "Given these results, what should we test?"
growthclaw/prompts/create_variant.j2             # "Create a new message variant testing X"
growthclaw/prompts/evaluate_experiment.j2        # "Here are results — what's the conclusion?"
```

### New Tables (add to migration)

```sql
-- AutoResearch experiment cycles (replaces simple experiments table for advanced use)
CREATE TABLE growthclaw.autoresearch_cycles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_id      UUID REFERENCES growthclaw.triggers(id),
    cycle_number    INTEGER NOT NULL,
    hypothesis      TEXT NOT NULL,
    variable        TEXT NOT NULL,           -- 'message_tone', 'offer', 'channel', 'send_time', 'delay'
    control_desc    TEXT NOT NULL,           -- Description of control variant
    test_desc       TEXT NOT NULL,           -- Description of test variant
    control_template TEXT,                   -- The actual message template (control)
    test_template   TEXT,                    -- The actual message template (test)
    metric          TEXT NOT NULL DEFAULT 'conversion_rate',
    min_sample_size INTEGER NOT NULL DEFAULT 100,
    status          TEXT DEFAULT 'running',  -- running | evaluating | completed
    decision        TEXT,                    -- promote_test | keep_control | inconclusive
    control_sends   INTEGER DEFAULT 0,
    control_conversions INTEGER DEFAULT 0,
    test_sends      INTEGER DEFAULT 0,
    test_conversions INTEGER DEFAULT 0,
    uplift_pct      FLOAT,
    confidence      FLOAT,                  -- p-value
    reasoning       TEXT,                   -- LLM explanation of result
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

-- Track which variant each journey used
ALTER TABLE growthclaw.journeys ADD COLUMN autoresearch_cycle_id UUID REFERENCES growthclaw.autoresearch_cycles(id);
ALTER TABLE growthclaw.journeys ADD COLUMN autoresearch_arm TEXT;  -- 'control' or 'test'
```

### autoresearch/loop.py — The Core Loop

```python
"""
The AutoResearch Loop — Karpathy pattern for marketing.

Cycle: OBSERVE → HYPOTHESIZE → CREATE VARIANTS → DEPLOY → EVALUATE → REPEAT

Runs on a schedule (e.g., every 6 hours) for each active trigger.
"""

import structlog
from growthclaw.autoresearch.hypothesis_generator import generate_hypothesis
from growthclaw.autoresearch.variant_creator import create_variant
from growthclaw.autoresearch.evaluator import evaluate_cycle

logger = structlog.get_logger()


class AutoResearchLoop:
    def __init__(self, llm_client, internal_conn, settings):
        self.llm = llm_client
        self.conn = internal_conn
        self.settings = settings

    async def run_cycle(self, trigger_id: str):
        """Run one AutoResearch cycle for a trigger."""

        # STEP 1: OBSERVE — Get current performance + experiment history
        current_metrics = await self._get_trigger_metrics(trigger_id)
        history = await self._get_cycle_history(trigger_id, limit=10)

        # If there's a running cycle, check if it has enough data to evaluate
        running = await self._get_running_cycle(trigger_id)
        if running:
            if running.control_sends >= running.min_sample_size and running.test_sends >= running.min_sample_size:
                # EVALUATE the running cycle
                decision = await evaluate_cycle(running, self.llm)
                await self._complete_cycle(running.id, decision)
                if decision.decision == "promote_test":
                    await self._promote_variant(running)
                logger.info("autoresearch.cycle_completed",
                            trigger_id=trigger_id,
                            cycle=running.cycle_number,
                            decision=decision.decision,
                            uplift=decision.uplift_pct)
            else:
                # Not enough data yet — wait for more sends
                logger.info("autoresearch.waiting_for_data",
                            trigger_id=trigger_id,
                            control_sends=running.control_sends,
                            test_sends=running.test_sends,
                            min_needed=running.min_sample_size)
                return

        # STEP 2: HYPOTHESIZE — LLM proposes what to test next
        hypothesis = await generate_hypothesis(
            current_metrics=current_metrics,
            history=history,
            llm_client=self.llm,
        )

        # STEP 3: CREATE VARIANTS — LLM generates the test content
        variant = await create_variant(
            hypothesis=hypothesis,
            trigger_id=trigger_id,
            llm_client=self.llm,
        )

        # STEP 4: DEPLOY — Save the new cycle (events will be routed to control/test)
        cycle_number = (history[0].cycle_number + 1) if history else 1
        await self._save_cycle(trigger_id, cycle_number, hypothesis, variant)

        logger.info("autoresearch.new_cycle",
                    trigger_id=trigger_id,
                    cycle=cycle_number,
                    hypothesis=hypothesis.hypothesis,
                    variable=hypothesis.variable)

    async def _promote_variant(self, cycle):
        """When a test wins, update the trigger's default message context."""
        # The winning variant's template becomes the new baseline
        # Update the trigger's message_context to reflect the winning approach
        await self.conn.execute(
            "UPDATE growthclaw.triggers SET message_context = $1 WHERE id = $2",
            cycle.test_desc + " (promoted from cycle " + str(cycle.cycle_number) + ")",
            cycle.trigger_id,
        )
```

### autoresearch/hypothesis_generator.py

```python
"""LLM generates hypotheses about what to test next."""

from growthclaw.llm.client import LLMClient, render_template


async def generate_hypothesis(current_metrics: dict, history: list, llm_client: LLMClient) -> dict:
    """
    LLM analyzes past experiments and current performance,
    then proposes the next thing to test.
    """
    prompt = render_template(
        "generate_hypothesis.j2",
        current_metrics=current_metrics,
        experiment_history=history,
    )
    return await llm_client.call_json(prompt, temperature=0.3)
```

### generate_hypothesis.j2

```
You are an expert marketing scientist running autonomous experiments.

Review the current performance and experiment history, then propose ONE specific
change to test in the next experiment cycle.

CURRENT TRIGGER PERFORMANCE:
{{ current_metrics | tojson(indent=2) }}

EXPERIMENT HISTORY (most recent first):
{% for cycle in experiment_history %}
Cycle {{ cycle.cycle_number }}: Tested {{ cycle.variable }} — {{ cycle.hypothesis }}
  Control: {{ cycle.control_sends }} sends, {{ cycle.control_conversions }} conversions ({{ "%.1f"|format((cycle.control_conversions / cycle.control_sends * 100) if cycle.control_sends > 0 else 0) }}%)
  Test: {{ cycle.test_sends }} sends, {{ cycle.test_conversions }} conversions ({{ "%.1f"|format((cycle.test_conversions / cycle.test_sends * 100) if cycle.test_sends > 0 else 0) }}%)
  Decision: {{ cycle.decision }}{% if cycle.uplift_pct %} ({{ "%.1f"|format(cycle.uplift_pct) }}% uplift){% endif %}
{% endfor %}

TESTABLE VARIABLES:
- message_tone: casual, professional, urgent, warm, playful
- offer: none, percentage discount, free trial, credit, bonus
- personalization_depth: name only, name+city, name+city+usage_data
- send_time_preference: morning (8-10am), midday (11am-1pm), afternoon (2-5pm), evening (6-8pm)
- cta_style: direct ("Add your card"), soft ("Learn more"), urgent ("Don't miss out")
- message_length: short (1 sentence), medium (2-3 sentences)
- channel: sms, email (if both available)

RULES:
- Do NOT re-test a variable + value combination that already lost
- If a variable has never been tested, prioritize it
- Focus on the variable with highest expected impact
- Each test should change exactly ONE variable (controlled experiment)

Respond with JSON:
{
  "hypothesis": "Human-readable hypothesis (e.g., 'Adding the customer's city to the SMS will increase open rate')",
  "variable": "the variable being tested (from list above)",
  "control_value": "current/default value",
  "test_value": "proposed new value",
  "expected_uplift": "low | medium | high",
  "reasoning": "2-3 sentences explaining why this test is worth running",
  "min_sample_size": 100
}
```

### Changes to main.py (_delayed_evaluate)

When composing a message, check if there's a running AutoResearch cycle for this trigger:

```python
# After profile analysis, before message composition:
cycle = await self._get_running_autoresearch_cycle(trigger.id)
if cycle:
    # Assign to control or test (50/50 random)
    arm = "control" if random.random() < 0.5 else "test"
    # Use the cycle's template to guide message composition
    if arm == "test":
        # Modify the compose prompt to use the test variant's parameters
        message_context = cycle.test_desc
    else:
        message_context = cycle.control_desc
    # ... compose with modified context ...
    # Record arm assignment on the journey
    journey.autoresearch_cycle_id = cycle.id
    journey.autoresearch_arm = arm
```

### Changes to outcome_checker.py

When a journey with an `autoresearch_cycle_id` converts, update the cycle's counters:

```python
if journey.autoresearch_cycle_id:
    arm_col = "control_conversions" if journey.autoresearch_arm == "control" else "test_conversions"
    await conn.execute(
        f"UPDATE growthclaw.autoresearch_cycles SET {arm_col} = {arm_col} + 1 WHERE id = $1",
        journey.autoresearch_cycle_id,
    )
```

### AutoResearch Scheduler

In `main.py`, add a scheduled job that runs the AutoResearch loop:

```python
# In start(), after starting CDC listener:
self.scheduler.add_job(
    self._run_autoresearch,
    trigger="interval",
    hours=6,
    id="autoresearch_loop",
    name="AutoResearch Loop",
)

async def _run_autoresearch(self):
    """Run one AutoResearch cycle for each active trigger."""
    async with self.internal_pool.acquire() as conn:
        triggers = await trigger_store.get_active(conn)
        for trigger in triggers:
            try:
                await self.autoresearch.run_cycle(trigger.id)
            except Exception:
                logger.exception("autoresearch.cycle_failed", trigger_id=str(trigger.id))
```

---

## PHASE 2D: Streamlit Dashboard

### New Files

```
growthclaw/dashboard/__init__.py
growthclaw/dashboard/app.py                # Streamlit main app
growthclaw/dashboard/pages/overview.py     # Funnel + key metrics
growthclaw/dashboard/pages/triggers.py     # Trigger status + config
growthclaw/dashboard/pages/journeys.py     # Recent outreach log
growthclaw/dashboard/pages/experiments.py  # AutoResearch results
growthclaw/dashboard/queries.py            # SQL queries for dashboard data
```

### pyproject.toml Addition

```
"streamlit>=1.45.0",
"plotly>=6.1.0",
"pandas>=2.2.3",
```

### CLI Addition

```python
@cli.command()
def dashboard():
    """Open the GrowthClaw dashboard."""
    import subprocess
    subprocess.Popen(["streamlit", "run", "growthclaw/dashboard/app.py", "--server.port", "8501"])
    click.echo("Dashboard running at http://localhost:8501")
```

### Dashboard Pages

**Overview** (`pages/overview.py`):
- Funnel visualization (stages with conversion rates between each)
- Key metrics cards: total customers, activated, conversion rate, MRR
- Sends today / this week / this month
- Conversion rate trend (line chart, last 30 days)

**Triggers** (`pages/triggers.py`):
- Table of all triggers: name, status, channel, delay, fires today, conversion rate
- Toggle to pause/resume triggers
- "Approve All" button for proposed triggers

**Journeys** (`pages/journeys.py`):
- Scrollable table of recent journeys: timestamp, user_id (masked), trigger, channel, message preview, status, outcome
- Filter by trigger, channel, outcome
- Expandable rows showing full message + LLM reasoning

**Experiments** (`pages/experiments.py`):
- AutoResearch cycle history per trigger
- Bar chart: control vs test conversion rates per cycle
- Cumulative uplift tracker
- Current running experiment status + sample size progress

### queries.py — All Dashboard SQL

Keep all SQL in one file for maintainability:

```python
FUNNEL_QUERY = """
    SELECT * FROM growthclaw.schema_map
    ORDER BY discovered_at DESC LIMIT 1
"""

DAILY_SENDS = """
    SELECT DATE(sent_at) as day, channel, COUNT(*) as sends,
           COUNT(*) FILTER (WHERE outcome = 'converted') as conversions
    FROM growthclaw.journeys
    WHERE sent_at >= NOW() - INTERVAL '30 days'
    GROUP BY 1, 2 ORDER BY 1
"""

TRIGGER_PERFORMANCE = """
    SELECT t.name, t.channel, t.status,
           COUNT(j.id) as total_sends,
           COUNT(j.id) FILTER (WHERE j.outcome = 'converted') as conversions,
           ROUND(COUNT(j.id) FILTER (WHERE j.outcome = 'converted')::numeric /
                 NULLIF(COUNT(j.id), 0) * 100, 1) as conversion_rate
    FROM growthclaw.triggers t
    LEFT JOIN growthclaw.journeys j ON j.trigger_id = t.id AND j.status = 'sent'
    GROUP BY t.id, t.name, t.channel, t.status
    ORDER BY total_sends DESC
"""

RECENT_JOURNEYS = """
    SELECT j.created_at, j.user_id, t.name as trigger_name,
           j.channel, LEFT(j.message_body, 80) as message_preview,
           j.status, j.outcome, j.llm_reasoning,
           j.autoresearch_arm
    FROM growthclaw.journeys j
    JOIN growthclaw.triggers t ON t.id = j.trigger_id
    ORDER BY j.created_at DESC LIMIT $1
"""

AUTORESEARCH_HISTORY = """
    SELECT ac.cycle_number, ac.hypothesis, ac.variable,
           ac.control_sends, ac.control_conversions,
           ac.test_sends, ac.test_conversions,
           ac.decision, ac.uplift_pct, ac.confidence,
           ac.started_at, ac.completed_at
    FROM growthclaw.autoresearch_cycles ac
    WHERE ac.trigger_id = $1
    ORDER BY ac.cycle_number DESC
"""
```

---

## PHASE 2 MIGRATION

Create `growthclaw/migrations/002_phase2_tables.sql`:

```sql
-- Phase 2: Email channel, frequency capping, AutoResearch, suppressions

-- Suppressions (unsubscribes, bounces, complaints)
CREATE TABLE IF NOT EXISTS growthclaw.suppressions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    channel         TEXT NOT NULL,
    reason          TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, channel)
);

-- Global frequency tracking (cross-trigger)
CREATE TABLE IF NOT EXISTS growthclaw.global_frequency (
    user_id         TEXT NOT NULL,
    channel         TEXT NOT NULL,
    sent_at         TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gc_freq_user_channel
    ON growthclaw.global_frequency(user_id, channel, sent_at DESC);

-- AutoResearch experiment cycles
CREATE TABLE IF NOT EXISTS growthclaw.autoresearch_cycles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_id      UUID REFERENCES growthclaw.triggers(id),
    cycle_number    INTEGER NOT NULL,
    hypothesis      TEXT NOT NULL,
    variable        TEXT NOT NULL,
    control_desc    TEXT NOT NULL,
    test_desc       TEXT NOT NULL,
    control_template TEXT,
    test_template   TEXT,
    metric          TEXT NOT NULL DEFAULT 'conversion_rate',
    min_sample_size INTEGER NOT NULL DEFAULT 100,
    status          TEXT DEFAULT 'running',
    decision        TEXT,
    control_sends   INTEGER DEFAULT 0,
    control_conversions INTEGER DEFAULT 0,
    test_sends      INTEGER DEFAULT 0,
    test_conversions INTEGER DEFAULT 0,
    uplift_pct      FLOAT,
    confidence      FLOAT,
    reasoning       TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_gc_ar_trigger ON growthclaw.autoresearch_cycles(trigger_id, status);

-- Add AutoResearch columns to journeys
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'growthclaw' AND table_name = 'journeys'
                   AND column_name = 'autoresearch_cycle_id') THEN
        ALTER TABLE growthclaw.journeys ADD COLUMN autoresearch_cycle_id UUID
            REFERENCES growthclaw.autoresearch_cycles(id);
        ALTER TABLE growthclaw.journeys ADD COLUMN autoresearch_arm TEXT;
    END IF;
END $$;

-- Frequency cleanup job: delete records older than 30 days (run periodically)
-- (This is a maintenance query, not a table — implement in outcome_checker.py)
```

---

## BUILD ORDER

1. **Migration 002** — New tables (suppressions, global_frequency, autoresearch_cycles, journeys columns)
2. **config.py** — Add SendGrid settings + frequency cap settings
3. **outreach/email_sender.py** — SendGrid integration
4. **prompts/compose_email.j2** — Email prompt template
5. **outreach/message_composer.py** — Add `compose_email()` function
6. **outreach/channel_resolver.py** — Add `is_suppressed()` check
7. **triggers/frequency_manager.py** — Global frequency capping
8. **triggers/trigger_installer.py** — Multi-trigger-per-table fix
9. **main.py** — Email sending path + frequency checks + suppression checks
10. **Tests** for email sender, frequency manager, suppression checks
11. **autoresearch/hypothesis_generator.py** + prompt template
12. **autoresearch/variant_creator.py** + prompt template
13. **autoresearch/evaluator.py** + prompt template
14. **autoresearch/loop.py** — The main loop
15. **main.py** — AutoResearch scheduler integration + journey arm tracking
16. **outcome_checker.py** — AutoResearch cycle counter updates
17. **Tests** for AutoResearch loop, hypothesis generator, evaluator
18. **dashboard/queries.py** — All dashboard SQL
19. **dashboard/app.py** — Streamlit main app
20. **dashboard/pages/** — All 4 dashboard pages
21. **cli.py** — Add `dashboard` command
22. **README.md** — Update with Phase 2 features
23. **pyproject.toml** — Add new dependencies

## IMPORTANT CONSTRAINTS (Same as Phase 1, plus:)

9. **AutoResearch cycles are append-only.** Never modify a completed cycle. Each cycle is a historical record.
10. **One running AutoResearch cycle per trigger at a time.** Don't start a new cycle until the current one is evaluated or times out.
11. **Frequency caps are global.** A user who got 2 SMS from the signup_no_activation trigger counts toward the daily cap for the subscription_rescue trigger too.
12. **Email HTML must be simple.** No complex layouts — SendGrid handles responsive rendering. Use `<p>`, `<a>`, `<strong>` only.
13. **Streamlit dashboard reads from the internal DB only.** It never touches the customer DB. All data it needs is in `growthclaw.*` tables.
14. **The dashboard must work with DRY_RUN data.** Even if no real messages were sent, the dashboard should show composed journeys and experiment assignments.
