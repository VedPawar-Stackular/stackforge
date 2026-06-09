# StackForge — AI-Powered SDLC Automation POC

Built by **Stackular Technologies**. This POC demonstrates Stages 1 and 2 of the StackForge pipeline: ingesting raw client requirements and automatically generating structured epics and user stories, ready to push to Azure DevOps.

---

## What This Does

```
Client Documents (PDF / DOCX / TXT)
        ↓
[Stage 1] Requirement Ingestion
  • Chunks documents into ~275-word segments
  • Cheap model summarises each chunk in parallel
  • Capable model extracts structured requirements from summaries
  • Generates clarification questions for ambiguous requirements
  • Stores everything in PostgreSQL + BM25 knowledge base
        ↓
[Stage 2] Epic & User Story Generation
  • Cheap model decomposes requirements into epic themes
  • Mid-tier model generates user stories per epic (with acceptance criteria)
  • Shows token cost savings vs naive single-model approach (~87% reduction)
  • Pushes epics and stories to Azure DevOps as work items
```

**Token optimisation is built into every step.** Two model tiers, strict JSON outputs, parallel batch calls, and a content-hash deduplication layer keep API costs at ~3–5% of what a naive implementation would spend.

---

## Project Structure

```
poc/
├── README.md                   ← you are here
├── run_demo.py                 ← CLI entry point: runs full Stage 1 pipeline
├── config.py                   ← shared config: model names, chunking, RAG, pricing
├── requirements.txt            ← Python deps (unpinned for 3.14 compat)
├── .env.example                ← copy to .env and fill in your keys
│
├── api/                        ← FastAPI REST layer
│   ├── main.py                 ← app entrypoint, CORS, router mounts
│   ├── models.py               ← all Pydantic request/response schemas
│   └── routes/
│       ├── projects.py         ← CRUD: clients & projects
│       ├── documents.py        ← file upload → pipeline trigger
│       ├── requirements.py     ← list extracted requirements
│       ├── clarifications.py   ← Q&A management
│       ├── docs.py             ← SDLC topic documents (read/edit)
│       ├── stitch.py           ← Google Stitch UI generation
│       └── epics.py            ← Stage 2: epic/story generation + ADO push
│
├── pipeline/                   ← AI orchestration modules
│   ├── runner.py               ← Stage 1 orchestrator (parse→chunk→summarise→extract→clarify→embed)
│   ├── stage2_runner.py        ← Stage 2 orchestrator (decompose→generate→metrics)
│   ├── parser.py               ← PDF / DOCX / TXT → plain text
│   ├── chunker.py              ← ~275-word chunks at paragraph boundaries
│   ├── summarizer.py           ← cheap model parallel summarisation (rate-limited, with retry)
│   ├── extractor.py            ← capable model: summaries → structured requirements JSON
│   ├── clarifier.py            ← cheap model: requirements → clarification questions
│   ├── embedder.py             ← stores text in rag_chunks (vector column NULL; BM25 active)
│   ├── epic_generator.py       ← cheap model: requirements → epic themes
│   ├── story_generator.py      ← mid model: per-epic user stories with acceptance criteria
│   ├── metrics_calculator.py   ← token cost comparison: actual vs naive approach
│   ├── ado_client.py           ← Azure DevOps REST API wrapper
│   ├── doc_writer.py           ← AI-generated SDLC topic markdown documents
│   ├── doc_editor.py           ← LLM-powered document editing
│   ├── stitch_designer.py      ← Google Stitch UI design generation
│   └── workspace_prep.py       ← injects design assets into Multica agent workspaces
│
├── rag/                        ← knowledge base retrieval
│   ├── search.py               ← BM25 keyword search (semantic search disabled — no torch on 3.14)
│   ├── reranker.py             ← cross-encoder reranker (passthrough until torch available)
│   └── pinecone_client.py      ← Pinecone vector store (optional, disabled if no API key)
│
├── db/                         ← database layer
│   ├── db.py                   ← pg8000 connection context manager
│   ├── init.sql                ← Stage 1 schema: clients, projects, documents, requirements, rag_chunks
│   ├── stage2.sql              ← Stage 2 schema: epics, stories, ado_work_items
│   ├── migrate_stage2.py       ← migration script: applies stage2.sql to existing DB
│   └── seed.py                 ← creates demo client/project and sample documents
│
├── ui/                         ← Streamlit frontend
│   └── app.py                  ← 6-tab UI (Setup / Upload / Requirements / Docs / Clarifications / Epics & Stories)
│
├── docs/                       ← integration and architecture notes
│   └── MULTICA_INTEGRATION.md  ← how to wire Stitch design assets into the Multica Go daemon
│
└── scripts/                    ← development utilities (not production code)
    └── debug_stitch.py         ← MCP diagnostic: lists Stitch tools, tests create_project flow
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| API | FastAPI | async, fast, auto-docs |
| Database | PostgreSQL via pg8000 | pure-Python adapter — psycopg2 has no Python 3.14 wheels |
| AI provider | Groq (free tier) | llama-3.1-8b-instant (cheap) + llama-3.3-70b-versatile (capable); swap to Anthropic by changing base_url + model strings only |
| Knowledge base | BM25 (rank_bm25) | sentence-transformers requires torch — no 3.14 wheels yet; schema has embedding column ready |
| Frontend | Streamlit | rapid iteration; dark design system with cards, badges, pipeline tracker |

---

## Setup

### Prerequisites

- Python 3.14+
- Docker (for PostgreSQL)
- A [Groq](https://console.groq.com) API key (free)

### 1. Start the database

```powershell
docker start stackforge-db
```

If first time:
```powershell
docker run --name stackforge-db -e POSTGRES_PASSWORD=password -e POSTGRES_DB=stackforge -p 5432:5432 -d postgres:16
```

### 2. Configure environment

```powershell
Copy-Item poc\.env.example poc\.env
# Edit poc\.env — add GROQ_API_KEY and DATABASE_URL
```

### 3. Install dependencies

```powershell
cd poc
pip install -r requirements.txt
```

### 4. Initialise the schema

```powershell
# Stage 1 schema
psql $env:DATABASE_URL -f db/init.sql

# Stage 2 schema (epics, stories, ADO work items)
python db/migrate_stage2.py
```

### 5. Seed demo data

```powershell
python db/seed.py
```

---

## Running

```powershell
# Terminal demo (Stage 1 only — CLI output with rich formatting)
python run_demo.py

# API server
python -m uvicorn api.main:app --reload

# Streamlit UI (separate terminal)
python -m streamlit run ui/app.py
```

API docs available at `http://localhost:8000/docs` when the server is running.

---

## Demo

Sample client documents for CareFlow (HIPAA telehealth platform) are in `../sample_client_docs/` at the repo root — SOW, FRS, and meeting transcript. Use these for demos.

**Typical results on CareFlow docs:**
- 130 requirements extracted across 4 types (functional, non-functional, constraint, assumption)
- 18 clarification questions generated
- Stage 1 pipeline: ~2 minutes end-to-end
- Stage 2 token savings: ~87% vs naive single-model approach

---

## Current Status

| Stage | Status | Notes |
|-------|--------|-------|
| Stage 1 — Requirement Ingestion | ✅ Built & validated | Tested on real CareFlow client docs |
| Stage 2 — Epic & Story Generation | ✅ Built | ADO push requires `ADO_PAT` in `.env` |
| Stage 3 — Sprint Planning | Not started | RAG-based estimation planned |
| Stage 4 — AI Development | Integration | Multica Go daemon — see `docs/MULTICA_INTEGRATION.md` |
| Stage 5 — QA & Bug Loop | Not started | Per-AC test generation planned |
| Stage 6 — PR Generation & RAG KB | Not started | Diff summarisation + embedding planned |

### Known limitations in this POC

- **Chunk overlap not implemented** — config has `CHUNK_OVERLAP_WORDS=35` but `chunker.py` does not yet use it; requirements spanning chunk boundaries may be missed
- **Vector search disabled** — `sentence-transformers` has no Python 3.14 wheels; BM25 active instead; `rag_chunks.embedding` column stays NULL until torch is available
- **Batch API not used** — Groq free tier is synchronous; switch to Anthropic Batch API for 50% cost reduction in production
- **ADO push optional** — leave `ADO_PAT` blank to skip ADO and still see epics/stories in the UI

---

## Configuration Reference

Key values in `config.py` (all overridable via `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_CHEAP` | `llama-3.1-8b-instant` | Haiku-tier model (classification, extraction, routing) |
| `MODEL_CAPABLE` | `llama-3.3-70b-versatile` | Sonnet-tier model (code gen, story gen, extraction) |
| `CHUNK_SIZE_WORDS` | `275` | Target chunk size for document splitting |
| `BM25_TOP_K` | `20` | Candidates retrieved before reranking |
| `RERANK_TOP_K` | `5` | Final chunks passed to the model |
| `ADO_ORG` | — | Azure DevOps organisation name |
| `ADO_PROJECT` | — | Azure DevOps project name |
| `ADO_PAT` | — | Personal Access Token (Work Items: Read & Write) |
