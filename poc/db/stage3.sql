-- Stage 3: Sprint & Task Planning schema
-- Apply via: python poc/db/migrate_stage3.py

-- Stage 3 generation status column on projects
ALTER TABLE projects ADD COLUMN IF NOT EXISTS
    stage3_status TEXT NOT NULL DEFAULT 'idle';

-- Sprints: capacity-based groups of user stories
CREATE TABLE IF NOT EXISTS sprints (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sprint_number    INTEGER NOT NULL,
    name             TEXT NOT NULL,
    capacity_points  INTEGER NOT NULL DEFAULT 20,
    total_points     INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'planned',
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- Junction table: which stories are assigned to which sprint
CREATE TABLE IF NOT EXISTS sprint_stories (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sprint_id      UUID NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
    story_id       UUID NOT NULL REFERENCES user_stories(id) ON DELETE CASCADE,
    project_id     UUID NOT NULL,
    priority_order INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- Tasks: development tasks decomposed from user stories by the LLM
CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id        UUID NOT NULL REFERENCES user_stories(id) ON DELETE CASCADE,
    project_id      UUID NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    task_type       TEXT NOT NULL,
    estimated_hours REAL NOT NULL DEFAULT 4.0,
    assignee        TEXT,
    status          TEXT NOT NULL DEFAULT 'todo',
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Token cost log for Stage 3 LLM calls
CREATE TABLE IF NOT EXISTS stage3_metrics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    step            TEXT NOT NULL,
    model           TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    thinking_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sprints_project_idx        ON sprints(project_id);
CREATE INDEX IF NOT EXISTS sprint_stories_sprint_idx  ON sprint_stories(sprint_id);
CREATE INDEX IF NOT EXISTS sprint_stories_story_idx   ON sprint_stories(story_id);
CREATE INDEX IF NOT EXISTS tasks_story_idx            ON tasks(story_id);
CREATE INDEX IF NOT EXISTS tasks_project_idx          ON tasks(project_id);
CREATE INDEX IF NOT EXISTS stage3_metrics_project_idx ON stage3_metrics(project_id);
