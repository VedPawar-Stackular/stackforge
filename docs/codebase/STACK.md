# Technology Stack

## Core Sections (Required)

### 1) Runtime Summary

| Area | Value | Evidence |
|------|-------|----------|
| Primary language | Python | `poc/requirements.txt`, all source files |
| Runtime + version | Python 3.14+ (constraint: no `psycopg2`, no `torch` wheels on 3.14) | `poc/README.md` |
| Package manager | pip (unpinned `>=` constraints for 3.14 compat) | `poc/requirements.txt` |
| Module/build system | None — flat package imports via `sys.path.insert` | `poc/api/main.py:7` |

### 2) Production Frameworks and Dependencies

| Dependency | Version | Role in system | Evidence |
|------------|---------|----------------|----------|
| fastapi | >=0.115.5 | REST API layer — all HTTP routing | `poc/api/main.py` |
| uvicorn[standard] | >=0.32.1 | ASGI server for FastAPI | `poc/README.md` |
| streamlit | >=1.40.2 | 6-tab Streamlit frontend UI | `poc/ui/app.py` |
| openai | >=1.56.0 | LLM client — OpenAI-compatible SDK pointed at Groq base URL | `poc/pipeline/summarizer.py:16`, `poc/config.py:11` |
| pg8000 | >=1.31.2 | Pure-Python PostgreSQL adapter (psycopg2 has no 3.14 wheels) | `poc/db.py` |
| pydantic | >=2.11.0 | Request/response schema validation for FastAPI | `poc/api/models.py` |
| rank_bm25 | >=0.2.2 | BM25 keyword search over `rag_chunks` table | `poc/rag/search.py` |
| httpx | >=0.28.0 | Sync HTTP client for Azure DevOps REST API calls | `poc/pipeline/ado_client.py` |
| pdfplumber | >=0.11.4 | PDF text extraction | `poc/pipeline/parser.py` |
| python-docx | >=1.1.2 | DOCX text extraction | `poc/pipeline/parser.py` |
| python-dotenv | >=1.0.1 | `.env` loading into `os.environ` | `poc/config.py:6` |
| python-multipart | >=0.0.12 | Multipart file upload support in FastAPI | `poc/api/routes/documents.py` |
| pinecone | >=5.0.0 | Optional Pinecone vector store for semantic search | `poc/rag/pinecone_client.py`, `poc/config.py:35-41` |
| mcp | >=1.0.0 | Model Context Protocol client for Google Stitch integration | `poc/pipeline/stitch_designer.py` |
| rich | >=13.0.0 | Terminal output formatting for CLI demo | `poc/run_demo.py` |
| plotly | >=5.24.0 | Charts in Streamlit UI (token cost comparisons) | `poc/ui/app.py` |

### 3) Development Toolchain

| Tool | Purpose | Evidence |
|------|---------|----------|
| Docker (postgres:16) | Local PostgreSQL via `docker start stackforge-db` | `poc/README.md` |
| Groq (free tier) | LLM provider during development (swap to Anthropic in prod) | `poc/config.py:11-14` |
| [TODO] | No linter/formatter config found in repo | scan output |
| [TODO] | No test runner configured | scan output |

### 4) Key Commands

```bash
# Start database
docker start stackforge-db

# Install deps
cd poc && pip install -r requirements.txt

# Apply Stage 1 schema
psql $DATABASE_URL -f db/init.sql

# Apply Stage 2 schema
python db/migrate_stage2.py

# Seed demo data
python db/seed.py

# CLI pipeline demo (Stage 1)
python run_demo.py

# API server
python -m uvicorn api.main:app --reload

# Streamlit UI
python -m streamlit run ui/app.py
```

### 5) Environment and Config

- Config source: `poc/.env` (not committed); template at `poc/.env.example`
- Central config module: `poc/config.py` — all values loaded once at import via `os.environ`
- Required env vars:
  - `DATABASE_URL` — PostgreSQL connection string
  - `GROQ_API_KEY` — LLM provider (dev/POC)
  - `ADO_ORG`, `ADO_PROJECT`, `ADO_PAT` — Azure DevOps push (optional; skip = no ADO sync)
  - `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` — optional Pinecone semantic search
  - `STITCH_API_KEY` — optional Google Stitch UI generation
- Runtime constraint: Python 3.14+ required; `sentence-transformers` (local embeddings) and `psycopg2` are blocked until their wheels ship for 3.14
- No Docker Compose, no CI/CD pipeline configured

### 6) Evidence

- `poc/requirements.txt`
- `poc/config.py`
- `poc/.env.example`
- `poc/README.md`
