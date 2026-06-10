# Project Structure

## Core Sections (Required)

### 1) Top-Level Layout

```
c:\StackForge\
├── CLAUDE.md                   ← full project context + architectural decisions
├── architecture.md             ← [TODO: check contents]
├── poc/                        ← all source code lives here
├── sample_client_docs/         ← CareFlow demo documents (DOCX, PDF, TXT)
├── Exiladraw/                  ← architecture diagrams (.excalidraw)
├── docs/                       ← generated knowledge docs (this directory)
├── skills-lock.json            ← Claude Code agent skill registry
├── .claude/                    ← Claude Code config (settings, agents, skills)
└── .gitignore
```

### 2) `poc/` Directory (All Source Code)

```
poc/
├── run_demo.py             ← CLI entry point: Stage 1 full pipeline with rich output
├── config.py               ← all config: models, chunking, RAG params, pricing, ADO creds
├── db.py                   ← pg8000 DB context manager (module-level, not in db/ subdir)
├── requirements.txt        ← Python dependencies (unpinned >= for 3.14 compat)
├── .env / .env.example     ← secrets and config (not committed)
│
├── api/                    ← FastAPI REST layer
│   ├── main.py             ← app factory, CORS, all router mounts
│   ├── models.py           ← all Pydantic request/response schemas (single file)
│   └── routes/
│       ├── projects.py     ← CRUD: clients & projects
│       ├── documents.py    ← file upload → pipeline trigger via BackgroundTasks
│       ├── requirements.py ← list extracted requirements
│       ├── clarifications.py ← Q&A management (list, answer)
│       ├── docs.py         ← SDLC topic documents (read/edit)
│       ├── epics.py        ← Stage 2: generate epics/stories + ADO push
│       └── stitch.py       ← Google Stitch UI design generation
│
├── pipeline/               ← all AI orchestration modules
│   ├── runner.py           ← Stage 1 orchestrator (7 steps)
│   ├── stage2_runner.py    ← Stage 2 orchestrator (epic + story generation + ADO push)
│   ├── parser.py           ← PDF/DOCX/TXT → plain text
│   ├── chunker.py          ← ~275-word chunks at paragraph boundaries
│   ├── summarizer.py       ← cheap model parallel summarisation + retry
│   ├── extractor.py        ← capable model: summaries → structured requirements JSON
│   ├── clarifier.py        ← cheap model: requirements → clarification questions
│   ├── embedder.py         ← writes to rag_chunks (embedding column NULL; BM25 active)
│   ├── epic_generator.py   ← cheap model: requirements → epic themes
│   ├── story_generator.py  ← mid model: per-epic user stories with acceptance criteria
│   ├── metrics_calculator.py ← token cost comparison: actual vs naive approach
│   ├── ado_client.py       ← Azure DevOps REST API wrapper (sync, httpx)
│   ├── doc_writer.py       ← AI-generated SDLC topic markdown documents
│   ├── doc_editor.py       ← LLM-powered document editing
│   ├── stitch_designer.py  ← Google Stitch UI design generation via MCP
│   └── workspace_prep.py   ← injects design assets into Multica agent workspaces
│
├── rag/                    ← knowledge base retrieval
│   ├── search.py           ← BM25 + Pinecone hybrid search with RRF merge
│   ├── reranker.py         ← cross-encoder reranker (passthrough; torch disabled)
│   └── pinecone_client.py  ← Pinecone semantic search (active if PINECONE_API_KEY set)
│
├── db/                     ← database schema + migrations
│   ├── init.sql            ← Stage 1 schema: clients, projects, documents, requirements, rag_chunks
│   ├── stage2.sql          ← Stage 2 schema: epics, user_stories, ado_work_items, stage2_metrics
│   ├── migrate_stage2.py   ← migration: applies stage2.sql to existing DB
│   └── seed.py             ← creates demo client/project; copies sample docs to sample_docs/
│
├── ui/                     ← Streamlit frontend
│   └── app.py              ← 6-tab UI (Setup / Upload / Requirements / Docs / Clarifications / Epics & Stories)
│
├── docs/
│   └── MULTICA_INTEGRATION.md ← how to wire Stitch design assets into Multica Go daemon
│
├── output/                 ← generated SDLC docs per project (UUID-keyed dirs)
│   └── {project_uuid}/     ← budget.md, design.md, requirements.md, technical.md, etc.
│
├── sample_docs/            ← auto-generated sample docs for seeding
└── scripts/
    └── debug_stitch.py     ← MCP diagnostic for Stitch integration
```

### 3) Entry Points

| Entry point | How invoked | Purpose |
|------------|-------------|---------|
| `poc/run_demo.py` | `python run_demo.py` | CLI Stage 1 demo with rich terminal output |
| `poc/api/main.py` | `uvicorn api.main:app --reload` | FastAPI REST server (all stages) |
| `poc/ui/app.py` | `python -m streamlit run ui/app.py` | Streamlit 6-tab frontend |
| `poc/db/migrate_stage2.py` | `python db/migrate_stage2.py` | One-time Stage 2 schema migration |
| `poc/db/seed.py` | `python db/seed.py` | Create demo client/project |

### 4) Non-Obvious Layout Notes

- `poc/db.py` lives at the `poc/` root, not inside `poc/db/` — the `db/` subdirectory is schema only
- `poc/output/{uuid}/` directories are runtime-generated SDLC docs per project run; not source code
- `poc/api/models.py` is a monolithic Pydantic schema file — all request/response types for all routes
- `sys.path.insert(0, ...)` in `poc/api/main.py:7` patches the Python path so `poc/` is importable as the root; there is no package install step

### 5) Evidence

- `poc/README.md` (structure overview)
- scan output (directory tree)
- `poc/api/main.py` (router mounts)
- `poc/pipeline/runner.py` (Stage 1 entry)
- `poc/pipeline/stage2_runner.py` (Stage 2 entry)
