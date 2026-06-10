# Testing

## Core Sections (Required)

### 1) Test Framework

- **No test framework configured.** No `pytest.ini`, `setup.cfg [tool:pytest]`, `pyproject.toml [tool.pytest]`, or `tests/` directory found.
- No `scripts.test` entry in any manifest.
- No test files detected in the codebase scan.

Evidence: scan output (no CI/CD pipelines, no test configs), directory tree (no `tests/` directory)

### 2) Current Test Coverage

**0% — no tests exist.**

The POC was built for rapid validation against real client documents (CareFlow). No automated test suite has been written.

### 3) What Would Need Tests (Priority Order)

Based on the code, highest-value test targets:

| Module | Test type | Why |
|--------|-----------|-----|
| `pipeline/chunker.py` | Unit | Paragraph-boundary chunking logic; `CHUNK_OVERLAP_WORDS` config not yet used |
| `pipeline/runner.py::ingest_document` | Integration | 7-step pipeline; content-hash deduplication; status state machine |
| `pipeline/stage2_runner.py::run_stage2` | Integration | Epic + story generation; DB writes; status state machine |
| `pipeline/stage2_runner.py::push_to_ado` | Integration (mocked ADO) | Idempotency check; error accumulation; partial failure handling |
| `rag/search.py::hybrid_search` | Unit | BM25 scoring; RRF merge correctness; Pinecone fallback path |
| `pipeline/epic_generator.py` | Unit (mocked LLM) | JSON parse fallback; requirement_id validation; default key injection |
| `db.py` | Integration | Connection lifecycle; rollback on exception; UUID array literal format |

### 4) Recommended Test Setup

```bash
pip install pytest pytest-asyncio pytest-cov

# Run tests
pytest tests/ -v --cov=poc --cov-report=term-missing

# Run async tests
pytest tests/ -v --asyncio-mode=auto
```

Required pytest config for async tests:
```ini
# pytest.ini or pyproject.toml [tool.pytest.ini_options]
asyncio_mode = auto
```

### 5) Mocking Strategy (Recommended)

- LLM calls (`AsyncOpenAI.chat.completions.create`): mock via `unittest.mock.AsyncMock` — prevents real API calls in unit tests
- Database: use a test PostgreSQL database (`DATABASE_URL` pointing to `stackforge_test`) — do NOT mock DB; the pg8000 UUID array literal pattern is a known gotcha that only a real DB can catch
- ADO API (`httpx.Client.post`): mock via `pytest-httpx` or `unittest.mock.patch` — prevents real work item creation
- Pinecone: mock `pinecone_client.semantic_search` — controlled result sets

### 6) Evidence

- scan output (no test configs, no `tests/` directory found)
- `poc/README.md` (no test commands listed)

### [ASK USER]

1. Should tests go in `poc/tests/` (alongside source) or `tests/` at the repo root?
2. Is pytest the preferred framework, or is there a team standard?
3. Should integration tests run against the real Docker PostgreSQL database, or a separate test container?
