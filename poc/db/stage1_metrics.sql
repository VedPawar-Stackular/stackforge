-- Stage 1 metrics: token usage for every LLM call in the ingestion pipeline
-- (summarization, extraction, clarification). Mirrors stage2_metrics so the
-- shared metrics calculator can read both with the same shape.
CREATE TABLE IF NOT EXISTS stage1_metrics (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    step            TEXT        NOT NULL,    -- 'summarization' | 'extraction' | 'clarification'
    model           TEXT        NOT NULL,
    input_tokens    INTEGER     NOT NULL,
    output_tokens   INTEGER     NOT NULL,
    thinking_tokens INTEGER     NOT NULL DEFAULT 0,
    duration_ms     INTEGER     NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS stage1_metrics_project_idx ON stage1_metrics(project_id);

-- Backfill thinking_tokens onto the existing Stage 2 metrics table.
-- Reasoning models populate this column. Current Groq llama models leave it 0.
ALTER TABLE stage2_metrics ADD COLUMN IF NOT EXISTS thinking_tokens INTEGER NOT NULL DEFAULT 0;
