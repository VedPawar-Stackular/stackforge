-- StackForge POC — Stage 1 schema
-- Run once: psql -U postgres -d stackforge -f init.sql

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Core tables ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    -- pending | processing | ready | failed
    status TEXT NOT NULL DEFAULT 'pending',
    -- Google Stitch design project (set after Stitch generation runs)
    stitch_project_id VARCHAR(255),
    stitch_project_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    -- pdf | docx | txt
    file_type TEXT NOT NULL,
    -- SHA-256 of raw file bytes; skip re-processing if hash unchanged
    content_hash TEXT NOT NULL,
    -- pending | processing | done | failed
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    uploaded_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS doc_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    -- Populated after Haiku/llama summarization pass
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    -- functional | non_functional | constraint | assumption
    req_type TEXT NOT NULL,
    -- requirements | design | technical | timeline | budget | testing | integrations | team_and_process
    sdlc_topic TEXT NOT NULL DEFAULT 'requirements',
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    -- UUIDs of source documents this requirement was derived from
    source_document_ids UUID[] DEFAULT '{}',
    -- 0.0–1.0 model confidence
    confidence REAL NOT NULL DEFAULT 0.8,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clarifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    -- Which requirement or area this targets
    context TEXT,
    -- high | medium | low
    priority TEXT NOT NULL DEFAULT 'medium',
    answer TEXT,
    -- open | answered
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─── RAG store ───────────────────────────────────────────────────────────────
-- Stores embeddings for: chunk summaries, requirements, answered clarifications
-- all-MiniLM-L6-v2 produces 384-dim vectors

CREATE TABLE IF NOT EXISTS rag_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    -- chunk_summary | requirement | clarification
    content_type TEXT NOT NULL,
    -- FK to the source row (doc_chunks.id, requirements.id, or clarifications.id)
    content_id UUID,
    text TEXT NOT NULL,
    embedding vector(384),
    -- {doc_type, client_id, project_id, source_format, priority, ...}
    metadata JSONB NOT NULL DEFAULT '{}',
    -- SHA-256 of text; skip re-embedding if unchanged
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- IVFFlat index for approximate nearest-neighbour search
-- lists=50 is appropriate for POC scale (<100k rows)
CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
    ON rag_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

CREATE INDEX IF NOT EXISTS rag_chunks_project_idx ON rag_chunks (project_id);
CREATE INDEX IF NOT EXISTS rag_chunks_content_hash_idx ON rag_chunks (content_hash);
