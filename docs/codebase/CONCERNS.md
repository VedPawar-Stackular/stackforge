# Concerns

## Core Sections (Required)

### 1) Technical Debt

| Concern | Location | Severity | Impact |
|---------|----------|----------|--------|
| **Chunk overlap not implemented** | `poc/pipeline/chunker.py` + `poc/config.py:19` | HIGH | Requirements spanning chunk boundaries are missed; `CHUNK_OVERLAP_WORDS=35` defined but not used |
| **Vector search disabled** | `poc/pipeline/embedder.py`, `poc/rag/search.py` | HIGH | `rag_chunks.embedding` always NULL; semantic RAG non-functional; BM25 only |
| **Batch API not used** | All pipeline LLM calls | HIGH | Groq free tier is synchronous; Anthropic Batch API (50% cheaper) is planned but not implemented |
| **BM25 corpus rebuilt per query** | `poc/rag/search.py:25-48` | MEDIUM | All `rag_chunks` fetched and BM25 index built in-memory on every search call; does not scale |
| **`api/models.py` is monolithic** | `poc/api/models.py` | MEDIUM | Single file for all Pydantic schemas across all routes; will grow unwieldy |
| **`sys.path.insert` path hack** | `poc/api/main.py:7` | MEDIUM | Brittle; breaks if working directory changes; no proper package install |
| **No connection pooling** | `poc/db.py` | MEDIUM | Fresh connection per DB block; PostgreSQL connection overhead per request |
| **Module-level `asyncio.Semaphore`** | `poc/pipeline/summarizer.py:20` | LOW | Module-level semaphore may not belong to the active event loop in some async contexts; `epic_generator.py` creates semaphore inside the function instead (the correct pattern) |

### 2) Known Gaps (from CLAUDE.md)

Confirmed architectural gaps documented in `CLAUDE.md`:

| Gap | Impact |
|-----|--------|
| No RAG retrieval before skill loading | Stage 4 loads all skills for every task; no relevance filtering |
| Orchestrator not in completion flow | `status=completed` fires without SE approval; no review gate |
| No timeout/watchdog on daemon (Multica) | Hung CLI agent = stuck task forever |
| `CleanupRuntimeConfig()` only on happy path (Multica) | `CLAUDE.md` left dirty if daemon crashes |
| Workspace isolation not confirmed under concurrency (Multica) | Concurrent tasks from same repo may share directory |
| No token budget enforcement mid-execution | Runaway tasks burn unlimited tokens |
| Model routing absent | All tasks go to same model; no per-task tier selection |
| `BuildPrompt()` output not logged | Cannot reproduce or debug prompt changes |
| Lark integration bidirectionality unconfirmed | SE replies may not come back into Multica |

### 3) Security Concerns

| Issue | Location | Severity |
|-------|----------|----------|
| **CORS wildcard** | `poc/api/main.py:24` (`allow_origins=["*"]`) | HIGH — must restrict before production |
| **No authentication on API** | All `poc/api/routes/*.py` | HIGH — no auth middleware; any caller can trigger pipeline or read data |
| **ADO PAT stored in `.env`** | `poc/config.py:53` | MEDIUM — no rotation policy; PAT has read+write work item scope |
| **Raw exception messages may leak** | Pipeline error propagation | MEDIUM — internal errors may appear in HTTP responses |
| **File upload type check by extension only** | `poc/api/routes/documents.py` | MEDIUM — file content not validated; only extension checked |

### 4) Performance Bottlenecks

| Bottleneck | Location | Notes |
|-----------|----------|-------|
| BM25 in-memory rebuild per query | `poc/rag/search.py:25-48` | Fetch all chunks + build index on every search; cache or pre-index needed |
| No connection pooling | `poc/db.py` | One connection per DB block; PostgreSQL connection overhead per request |
| Sequential ADO push | `poc/pipeline/stage2_runner.py::push_to_ado` | Epics then stories pushed sequentially; could be parallelised |
| Synchronous doc generation in async pipeline | `poc/pipeline/runner.py:178-185` | `doc_writer` runs synchronously; blocks event loop during pipeline |

### 5) High-Churn Files (Last 90 Days)

Files with highest modification rate:
- `poc/api/main.py` (2 commits)
- `poc/api/models.py` (2 commits)
- `poc/api/routes/documents.py` (2 commits)
- `poc/api/routes/projects.py` (2 commits)
- `poc/config.py` (2 commits)
- `poc/ui/app.py` (2 commits)

Note: All files show 2 commits — git history is very short (3 total commits). High-churn patterns will emerge after more development.

### 6) Files Over Complexity Threshold

| File | Size | Concern |
|------|------|---------|
| `poc/ui/app.py` | 85.1KB | Entire 6-tab Streamlit UI in one file; high coupling between UI logic and API calls |
| `sample_client_docs/gen_docs.py` | 85.8KB | Document generation script; not production code |

### 7) Evidence

- `CLAUDE.md` (known gaps list)
- `poc/api/main.py:24` (CORS wildcard)
- `poc/rag/search.py:25-48` (BM25 rebuild per query)
- `poc/pipeline/chunker.py` + `poc/config.py:19` (chunk overlap gap)
- scan output (high-churn files, file sizes)
