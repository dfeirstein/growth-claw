-- Phase 3: LLM usage tracking for BYOC (Bring Your Own Claude) cost visibility

CREATE TABLE IF NOT EXISTS growthclaw.llm_usage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider        TEXT NOT NULL,           -- 'subscription', 'anthropic', 'nvidia', 'nvidia_local'
    model           TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    cost_cents      INTEGER DEFAULT 0,       -- estimated cost in cents
    purpose         TEXT NOT NULL,            -- 'onboard', 'compose', 'autoresearch', 'operator', etc.
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gc_llm_usage_created
    ON growthclaw.llm_usage(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gc_llm_usage_provider
    ON growthclaw.llm_usage(provider, created_at DESC);
