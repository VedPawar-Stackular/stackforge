# Architecture

## Core Sections (Required)

### 1) Architectural Style

- Primary style: Pipeline / layered (API → pipeline modules → DB)
- Why: System is a multi-stage AI processing pipeline. Each stage is an independent orchestrator (`runner.py`, `stage2_runner.py`) that calls specialised modules (parser, chunker, summarizer, extractor, etc.) in sequence. No dependency injection container; modules are imported directly.
- Primary constraints:
  1. Token cost optimization at every AI call — model tier selection, structured JSON outputs, `max_tokens` caps
  2. Python 3.14 compatibility — blocks `sentence-transformers`, `psycopg2`, and `torch`; shapes library choices throughout
  3. Groq free-tier rate limit (30 req/min) — `asyncio.Semaphore(5)` + exponential backoff in all LLM call modules

### 2) System Flow

#### Stage 1 — Document Ingestion

```text
HTTP POST /documents (file upload)
  → FastAPI BackgroundTask → pipeline/runner.py::ingest_document()
  → parser.py (PDF/DOCX/TXT → plain text)
  → chunker.py (~275-word chunks at paragraph boundaries)
  → summarizer.py (cheap model, parallel, semaphore 5, retry on 429) → summaries[]
  → extractor.py (capable model, summaries → structured requirements JSON)
  → DB: INSERT requirements, doc_chunks
  → embedder.py (text → rag_chunks; embedding NULL; BM25 indexed)
  → clarifier.py (cheap model → clarification questions)
  → doc_writer.py (writes SDLC topic .md docs to poc/output/{uuid}/)
  → DB: UPDATE documents SET status='done'
```

#### Stage 2 — Epic & Story Generation

```text
HTTP POST /epics/generate/{project_id}
  → api/routes/epics.py (BackgroundTask)
  → pipeline/stage2_runner.py::run_stage2()
  → DB: SELECT requirements WHERE project_id
  → epic_generator.py (cheap model, titles-only input, ~3k tokens, JSON output)
  → DB: INSERT epics
  → story_generator.py (mid model, per-epic parallel, JSON output)
  → DB: INSERT user_stories
  → DB: UPDATE projects SET stage2_status='ready'

HTTP POST /epics/push-to-ado/{project_id} (on-demand, separate from generation)
  → stage2_runner.py::push_to_ado()
  → ado_client.py (httpx sync client, PAT auth, ADO REST v7.1)
  → DB: UPDATE epics/user_stories SET ado_work_item_id, ado_work_item_url
```

#### RAG Query

```text
HTTP GET /requirements/search?query=...
  → rag/search.py::hybrid_search()
  → BM25 over all rag_chunks for project (rank_bm25, in-memory corpus)
  → [if PINECONE_ENABLED] rag/pinecone_client.py::semantic_search()
  → RRF merge of BM25 + Pinecone results
  → rag/reranker.py (passthrough; cross-encoder disabled)
  → top RERANK_TOP_K chunks returned
```

### 3) Layer / Module Responsibilities

| Layer or module | Owns | Must not own | Evidence |
|-----------------|------|--------------|----------|
| `api/routes/*.py` | HTTP request parsing, response shaping, BackgroundTask dispatch | Business logic, DB queries | `api/routes/epics.py`, `api/routes/documents.py` |
| `api/models.py` | All Pydantic request/response schemas | Runtime logic | `poc/api/models.py` |
| `pipeline/runner.py` | Stage 1 orchestration (step sequence, error handling, status updates) | Parsing, chunking, LLM calls | `poc/pipeline/runner.py` |
| `pipeline/stage2_runner.py` | Stage 2 orchestration + ADO push logic | LLM calls, HTTP | `poc/pipeline/stage2_runner.py` |
| `pipeline/*.py` (individual modules) | Single-responsibility AI tasks (parse, chunk, summarize, extract, etc.) | DB writes, orchestration | each module |
| `db.py` | pg8000 connection lifecycle, query helpers | Business logic | `poc/db.py` |
| `rag/search.py` | Hybrid BM25 + Pinecone search + RRF merge | Embedding, reranking | `poc/rag/search.py` |
| `config.py` | All configuration loaded from env | Runtime state | `poc/config.py` |

### 4) Reused Patterns

| Pattern | Where found | Why it exists |
|---------|-------------|---------------|
| Content-hash deduplication | `pipeline/runner.py:66-76`, `pipeline/embedder.py` | Skip re-processing unchanged documents; `rag_chunks.content_hash` index |
| Semaphore + exponential backoff | `pipeline/summarizer.py:20`, `pipeline/epic_generator.py:58` | Groq free-tier rate limit (30 req/min); 5 concurrent calls max |
| Strict JSON schema + max_tokens cap | Every LLM call (summarizer, extractor, clarifier, epic_generator, story_generator) | Token cost control; prevents model padding and free-form prose |
| Two-tier model routing (cheap + capable) | `config.py:13-14`, all pipeline modules | `MODEL_CHEAP` for classification/summarisation; `MODEL_CAPABLE` for structured extraction/generation |
| pg8000 UUID/TEXT array literals | `pipeline/runner.py:139`, `pipeline/stage2_runner.py:27-36` | pg8000 cannot auto-cast Python lists to PostgreSQL `UUID[]`/`TEXT[]`; must use `"{uuid}"` / `"item"` literal format |
| BackgroundTask (fire-and-forget) | `api/routes/documents.py`, `api/routes/epics.py` | Pipeline runs are long; HTTP response returns immediately while pipeline runs async |
| Idempotent ADO push | `stage2_runner.py:192-193` | Skip epics/stories already pushed (`ado_work_item_id` NOT NULL check) to prevent duplicates on re-push |
| Module-level singleton LLM client | `pipeline/summarizer.py:17`, `pipeline/epic_generator.py:33` | `AsyncOpenAI` instance created once at import; reused across all calls |

### 5) Known Architectural Risks

- **No RAG before skill/context loading** — all pipeline context is loaded regardless of relevance; no pre-filtering. Impact: unnecessary token spend at Stage 4 (Multica agent tasks).
- **Orchestrator not in completion flow** — `stage2_status=completed` fires without Senior Engineer review gate. Impact: Stage 4→5 transition has no human checkpoint in current code.
- **No watchdog on async tasks** — if a BackgroundTask LLM call hangs, there is no timeout to kill it and mark the document/project failed. Impact: stuck jobs with no recovery path.
- **BM25 corpus loaded in-memory per query** — `hybrid_search()` fetches all `rag_chunks` for a project and builds a BM25 index on every call. Impact: scales poorly as knowledge base grows; no caching between requests.
- **CORS wildcard in production** — `allow_origins=["*"]` in `api/main.py:24`. Impact: POC-only — must be restricted before production.
- **Chunk overlap not implemented** — `config.py` defines `CHUNK_OVERLAP_WORDS=35` but `chunker.py` does not use it. Impact: requirements spanning chunk boundaries may be missed.

### 6) Evidence

- `poc/api/main.py` (entry point, router mounts)
- `poc/pipeline/runner.py` (Stage 1 flow)
- `poc/pipeline/stage2_runner.py` (Stage 2 flow)
- `poc/rag/search.py` (hybrid search + RRF)
- `poc/config.py` (model routing, pricing)
- `poc/db.py` (connection pattern)
