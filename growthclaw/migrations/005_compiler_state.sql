-- Compiler state tracking and prompt version management

CREATE TABLE IF NOT EXISTS growthclaw.compiler_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pass_name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    last_run_at TIMESTAMPTZ,
    result JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS growthclaw.prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_name TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    content TEXT NOT NULL,
    performance_score FLOAT,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(template_name, version)
);
