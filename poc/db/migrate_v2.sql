-- Migration v2: add sdlc_topic column to requirements
-- Run once against an existing stackforge database:
--   psql -U postgres -d stackforge -f migrate_v2.sql

ALTER TABLE requirements
    ADD COLUMN IF NOT EXISTS sdlc_topic TEXT NOT NULL DEFAULT 'requirements';

-- Backfill existing rows with a reasonable default based on req_type
UPDATE requirements
SET sdlc_topic = CASE req_type
    WHEN 'functional'     THEN 'requirements'
    WHEN 'non_functional' THEN 'technical'
    WHEN 'constraint'     THEN 'technical'
    WHEN 'assumption'     THEN 'requirements'
    ELSE 'requirements'
END
WHERE sdlc_topic = 'requirements';
