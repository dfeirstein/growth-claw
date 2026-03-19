-- GrowthClaw internal schema — business-agnostic state tables
-- No customer-specific SQL. No hardcoded table/column names.

CREATE SCHEMA IF NOT EXISTS growthclaw;

-- Schema discovery results
CREATE TABLE IF NOT EXISTS growthclaw.schema_map (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version         INTEGER NOT NULL DEFAULT 1,
    database_url_hash TEXT NOT NULL,
    business_name   TEXT,
    business_type   TEXT,
    tables          JSONB NOT NULL,
    concepts        JSONB NOT NULL,
    relationships   JSONB NOT NULL,
    funnel          JSONB NOT NULL,
    raw_statistics  JSONB,
    discovered_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger configurations (LLM-proposed, human-approved)
CREATE TABLE IF NOT EXISTS growthclaw.triggers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    watch_table     TEXT NOT NULL,
    watch_event     TEXT NOT NULL,
    watch_condition TEXT,
    delay_minutes   INTEGER NOT NULL DEFAULT 30,
    check_sql       TEXT NOT NULL,
    profile_queries JSONB NOT NULL,
    message_context TEXT NOT NULL,
    channel         TEXT NOT NULL DEFAULT 'sms',
    max_fires       INTEGER NOT NULL DEFAULT 3,
    cooldown_hours  INTEGER NOT NULL DEFAULT 24,
    status          TEXT NOT NULL DEFAULT 'proposed',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- CDC trigger install log
CREATE TABLE IF NOT EXISTS growthclaw.installed_triggers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name      TEXT NOT NULL,
    trigger_name    TEXT NOT NULL,
    function_name   TEXT NOT NULL,
    installed_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(table_name, trigger_name)
);

-- Real-time event log
CREATE TABLE IF NOT EXISTS growthclaw.events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    table_name      TEXT NOT NULL,
    operation       TEXT NOT NULL,
    trigger_id      UUID REFERENCES growthclaw.triggers(id),
    payload         JSONB NOT NULL,
    processed       BOOLEAN DEFAULT FALSE,
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gc_events_unprocessed
    ON growthclaw.events(processed, created_at) WHERE processed = FALSE;

-- Customer profiles (cached)
CREATE TABLE IF NOT EXISTS growthclaw.profiles (
    user_id         TEXT PRIMARY KEY,
    raw_data        JSONB NOT NULL,
    analysis        JSONB NOT NULL,
    computed_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Journey log (every outreach)
CREATE TABLE IF NOT EXISTS growthclaw.journeys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    trigger_id      UUID REFERENCES growthclaw.triggers(id),
    event_id        UUID REFERENCES growthclaw.events(id),
    channel         TEXT NOT NULL,
    contact_info    TEXT,
    message_body    TEXT NOT NULL,
    provider_id     TEXT,
    status          TEXT DEFAULT 'composed',
    experiment_id   UUID,
    experiment_arm  TEXT,
    llm_reasoning   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    sent_at         TIMESTAMPTZ,
    outcome         TEXT,
    outcome_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_gc_journeys_user
    ON growthclaw.journeys(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gc_journeys_outcome_pending
    ON growthclaw.journeys(outcome, sent_at)
    WHERE outcome IS NULL AND sent_at IS NOT NULL;

-- Trigger cooldown state
CREATE TABLE IF NOT EXISTS growthclaw.trigger_state (
    user_id         TEXT NOT NULL,
    trigger_id      UUID NOT NULL REFERENCES growthclaw.triggers(id),
    fire_count      INTEGER DEFAULT 0,
    last_fired_at   TIMESTAMPTZ,
    PRIMARY KEY (user_id, trigger_id)
);

-- Experiments
CREATE TABLE IF NOT EXISTS growthclaw.experiments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    trigger_id      UUID REFERENCES growthclaw.triggers(id),
    variable        TEXT NOT NULL,
    arms            JSONB NOT NULL,
    metric          TEXT NOT NULL,
    status          TEXT DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS growthclaw.experiment_results (
    experiment_id   UUID REFERENCES growthclaw.experiments(id),
    arm_name        TEXT NOT NULL,
    total_sent      INTEGER DEFAULT 0,
    total_converted INTEGER DEFAULT 0,
    conversion_rate FLOAT,
    last_updated    TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (experiment_id, arm_name)
);
