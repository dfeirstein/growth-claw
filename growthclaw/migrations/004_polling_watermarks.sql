-- Polling listener: watermark tracking for high-water mark polling

CREATE TABLE IF NOT EXISTS growthclaw.polling_watermarks (
    table_name      TEXT PRIMARY KEY,
    trigger_id      UUID REFERENCES growthclaw.triggers(id),
    timestamp_col   TEXT NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
