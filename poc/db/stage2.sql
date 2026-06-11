-- Stage 2 schema migration: Epics, User Stories, and metrics tracking.

-- Track generation status on the project row
ALTER TABLE projects ADD COLUMN IF NOT EXISTS stage2_status TEXT NOT NULL DEFAULT 'idle';
-- Values: idle | generating | ready | failed

CREATE TABLE IF NOT EXISTS epics (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title            TEXT        NOT NULL,
    description      TEXT        NOT NULL,
    theme            TEXT        NOT NULL,
    requirement_ids  UUID[]      NOT NULL DEFAULT '{}',
    ado_work_item_id INTEGER,
    ado_work_item_url TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_stories (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    epic_id              UUID        NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    project_id           UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title                TEXT        NOT NULL,
    description          TEXT        NOT NULL,
    acceptance_criteria  TEXT[]      NOT NULL DEFAULT '{}',
    story_points         INTEGER,
    assignee             TEXT,
    ado_work_item_id     INTEGER,
    ado_work_item_url    TEXT,
    status               TEXT        NOT NULL DEFAULT 'draft',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every LLM call in Stage 2 is logged here for the metrics calculator
CREATE TABLE IF NOT EXISTS stage2_metrics (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id     UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    step           TEXT        NOT NULL,    -- 'epic_decomposition' | 'story_generation_epic_N'
    model          TEXT        NOT NULL,
    input_tokens   INTEGER     NOT NULL,
    output_tokens  INTEGER     NOT NULL,
    thinking_tokens INTEGER    NOT NULL DEFAULT 0,
    duration_ms    INTEGER     NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS epics_project_idx        ON epics(project_id);
CREATE INDEX IF NOT EXISTS user_stories_epic_idx    ON user_stories(epic_id);
CREATE INDEX IF NOT EXISTS user_stories_project_idx ON user_stories(project_id);
CREATE INDEX IF NOT EXISTS stage2_metrics_project_idx ON stage2_metrics(project_id);
