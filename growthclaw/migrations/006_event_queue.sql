-- Migration 006: Event queue table
-- Stores events approved by the Python fast loop (cooldowns, consent, quiet hours,
-- frequency caps) that are ready for Claude Code to compose messages for.
-- Claude Code wakes up periodically and processes pending items via MCP tools.

CREATE TABLE IF NOT EXISTS growthclaw.event_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    trigger_id      UUID NOT NULL REFERENCES growthclaw.triggers(id),
    event_id        UUID NOT NULL REFERENCES growthclaw.events(id),
    channel         TEXT NOT NULL,           -- 'sms' or 'email'
    contact_value   TEXT NOT NULL,           -- phone number or email
    profile_data    JSONB NOT NULL DEFAULT '{}',
    intelligence     JSONB NOT NULL DEFAULT '{}',
    ar_cycle_id     UUID REFERENCES growthclaw.autoresearch_cycles(id),
    ar_arm          TEXT,                    -- 'control' or 'test'
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | composing | composed | sent | failed
    message_body    TEXT,                    -- filled after Claude Code composes
    message_subject TEXT,                    -- email only
    provider_id     TEXT,                    -- filled after send
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    composed_at     TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_eq_status ON growthclaw.event_queue(status, created_at);
CREATE INDEX IF NOT EXISTS idx_eq_trigger ON growthclaw.event_queue(trigger_id);
