# Integrations

## Core Sections (Required)

### 1) LLM Provider — Groq (dev/POC) / Anthropic (production target)

| Detail | Value |
|--------|-------|
| SDK | `openai` Python SDK (OpenAI-compatible) |
| Base URL | `https://api.groq.com/openai/v1` (`LLM_BASE_URL` in `config.py`) |
| Cheap model | `llama-3.1-8b-instant` (maps to Haiku tier) |
| Capable model | `llama-3.3-70b-versatile` (maps to Sonnet tier) |
| Auth | `GROQ_API_KEY` env var |
| Switch to Anthropic | Change `LLM_BASE_URL` + model name strings in `config.py` only |
| Rate limit | 30 req/min (free tier); enforced via `asyncio.Semaphore(5)` + exponential backoff |
| Client type | `AsyncOpenAI` (module-level singleton in each pipeline module) |

Evidence: `poc/config.py:10-14`, `poc/pipeline/summarizer.py:17`, `poc/pipeline/epic_generator.py:33`

### 2) PostgreSQL Database

| Detail | Value |
|--------|-------|
| Adapter | `pg8000` (pure Python; psycopg2 blocked on Python 3.14) |
| Connection | `DATABASE_URL` env var — parsed by `_conn_kwargs()` in `db.py` |
| Extensions | `vector` (pgvector for 384-dim embeddings), `pgcrypto` (gen_random_uuid) |
| SSL | Auto-enabled when `sslmode=require` in connection string (Neon-compatible) |
| Connection model | One new connection per `with DB() as db:` block — no connection pooling |
| Schema init | `poc/db/init.sql` (Stage 1), `poc/db/stage2.sql` (Stage 2) |

Evidence: `poc/db.py`, `poc/db/init.sql:1-4`, `poc/config.py:8`

### 3) Azure DevOps (ADO)

| Detail | Value |
|--------|-------|
| API version | `7.1` (`ADO_API_VERSION` in `config.py`) |
| Auth | HTTP Basic with base64(`:PAT`) — colon-prefixed PAT, base64-encoded |
| Work item types | `$Epic`, `$User Story` (Agile process template) |
| Hierarchy link | `System.LinkTypes.Hierarchy-Reverse` (child→parent direction) |
| AC format | HTML rich-text (`<ul><li>...</li></ul>`) for `Microsoft.VSTS.Common.AcceptanceCriteria` |
| HTTP client | `httpx.Client` (synchronous) |
| Config | `ADO_ORG`, `ADO_PROJECT`, `ADO_PAT` env vars |
| Optional | Leave `ADO_PAT` blank to skip ADO; epics/stories still generated locally |
| Idempotency | `ado_work_item_id` column checked before each push — skips already-pushed items |

Evidence: `poc/pipeline/ado_client.py`, `poc/config.py:51-55`, `poc/db/stage2.sql`

### 4) Pinecone Vector Store (Optional)

| Detail | Value |
|--------|-------|
| SDK | `pinecone` >=5.0.0 |
| Embed model | `multilingual-e5-large` (1024-dim, Pinecone Inference) |
| Index | `PINECONE_INDEX_NAME` (default: `stackforge-poc`) |
| Enabled | `PINECONE_ENABLED = bool(PINECONE_API_KEY)` — auto-disabled if key absent |
| Fallback | BM25-only search when Pinecone not configured |
| Cloud/region | `aws / us-east-1` (configurable via env) |

Evidence: `poc/rag/pinecone_client.py`, `poc/config.py:34-41`, `poc/rag/search.py:38-39`

### 5) Google Stitch (Optional)

| Detail | Value |
|--------|-------|
| Protocol | MCP (Model Context Protocol) client |
| SDK | `mcp` >=1.0.0 |
| Auth | `STITCH_API_KEY` env var |
| Purpose | AI-generated UI wireframes/design systems from project requirements |
| Output | Design files stored in `poc/output/{uuid}/stitch/` |
| Disabled | Silently skipped if `STITCH_API_KEY` not set |

Evidence: `poc/pipeline/stitch_designer.py`, `poc/config.py:43-44`, `poc/api/routes/stitch.py`

### 6) Multica (Stage 4 — External, Not Yet Integrated)

| Detail | Value |
|--------|-------|
| Purpose | AI coding agent platform; runs Claude Code under the hood |
| Interface | CLI (`multica issue assign`), local daemon, browser board |
| Workspace path | `~/multica_workspaces/{issue-id}/` |
| Integration status | Design docs exist; not yet wired into Stage 4 completion flow |
| Integration notes | `poc/docs/MULTICA_INTEGRATION.md`, `poc/pipeline/workspace_prep.py` |

Evidence: `poc/docs/MULTICA_INTEGRATION.md`, `poc/pipeline/workspace_prep.py`, `CLAUDE.md`

### 7) Credentials Storage

- All credentials in `poc/.env` (not committed)
- Template at `poc/.env.example`
- Loaded via `python-dotenv` at `config.py` import
- No secrets manager integration — POC only

### 8) Evidence

- `poc/pipeline/ado_client.py`
- `poc/rag/pinecone_client.py`
- `poc/rag/search.py`
- `poc/config.py`
- `poc/pipeline/stitch_designer.py`
- `poc/docs/MULTICA_INTEGRATION.md`
