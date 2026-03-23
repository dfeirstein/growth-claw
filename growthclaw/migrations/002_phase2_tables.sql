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
CREATE INDEX IF NOT EXISTS idx_gc_ar_trigger
    ON growthclaw.autoresearch_cycles(trigger_id, status);

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
