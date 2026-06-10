# Conventions

## Core Sections (Required)

### 1) File Naming

- All Python source files: `snake_case.py` — e.g., `epic_generator.py`, `stage2_runner.py`, `ado_client.py`
- SQL schema files: `snake_case.sql` — e.g., `init.sql`, `stage2.sql`
- No camelCase or PascalCase in filenames

Evidence: `poc/pipeline/`, `poc/api/routes/`, `poc/db/` directory listings

### 2) Function and Variable Naming

- Functions and variables: `snake_case` — e.g., `generate_epics()`, `run_stage2()`, `content_hash`
- Private helpers (module-internal): `_underscore_prefix` — e.g., `_call_with_retry()`, `_bm25_search()`, `_auth_header()`, `_text_array_literal()`
- Module-level singletons: `_underscore_prefix` — e.g., `_client` (AsyncOpenAI), `_semaphore`, `_SYSTEM_PROMPT`
- Constants in config: `UPPER_SNAKE_CASE` — e.g., `MODEL_CHEAP`, `BM25_TOP_K`, `ADO_API_VERSION`

Evidence: `poc/pipeline/summarizer.py`, `poc/pipeline/epic_generator.py`, `poc/config.py`

### 3) Type Annotations

- All public function signatures use type annotations — e.g., `async def generate_epics(requirements: list[dict]) -> tuple[list[dict], int, int, int]`
- Return types annotated on all functions
- Modern union syntax used (`dict | None`, `int | None`) requiring Python 3.10+

Evidence: `poc/pipeline/epic_generator.py:95`, `poc/db.py:59`, `poc/pipeline/stage2_runner.py:27`

### 4) Error Handling

- Pipeline stages: `try/except Exception` in orchestrators (`runner.py`, `stage2_runner.py`) — catch all, update DB status to `'failed'`, then re-raise
- LLM calls: retry with exponential backoff on `RateLimitError` (4 attempts, `2^n + jitter` seconds)
- ADO push: per-epic and per-story try/except — errors appended to `errors[]` list, not raised; entire push does not abort on single failure
- JSON parse failures: default to `[]` or `{}` — no exceptions propagated for malformed LLM responses
- `doc_writer` failure is caught and logged as warning (non-blocking) — pipeline still completes

Evidence: `poc/pipeline/runner.py:197-202`, `poc/pipeline/stage2_runner.py:152-158`, `poc/pipeline/epic_generator.py:59-91`, `poc/pipeline/stage2_runner.py:222-229`

### 5) Logging

- Standard `logging` module used for pipeline warnings (e.g., `doc_writer` failure in `runner.py:184`)
- No structured logging format configured; no log level set globally
- `rich` used for CLI demo terminal output (`run_demo.py`)
- [TODO] Audit for stray `print()` statements vs `logging` usage

Evidence: `poc/pipeline/runner.py:183-185`

### 6) Import Organization

- `sys.path.insert(0, ...)` in `api/main.py` patches `poc/` as root — no package install required
- Imports grouped: stdlib → third-party → local (convention followed; not enforced by tooling)
- `config.py` values imported directly by name in each module — no global config object passed around
- `DB` class imported at call site inside functions in some modules to avoid circular import issues

Evidence: `poc/api/main.py:7`, `poc/pipeline/epic_generator.py:29-31`, `poc/pipeline/stage2_runner.py:168`

### 7) LLM Call Conventions

- Every LLM call specifies: `model`, `max_tokens` cap, `response_format={"type": "json_object"}`, JSON schema in system prompt
- System prompts are module-level string constants (`_SYSTEM_PROMPT`) — static and cacheable
- All LLM calls return `(content, input_tokens, output_tokens, duration_ms)` tuple for metrics logging
- Token usage logged to `stage2_metrics` table after every generation step

Evidence: `poc/pipeline/epic_generator.py:36-56`, `poc/pipeline/summarizer.py:22-28`, `poc/pipeline/stage2_runner.py:241-266`

### 8) Database Conventions

- UUID primary keys everywhere, generated at application layer (`str(uuid.uuid4())`)
- PostgreSQL array literals for `UUID[]`/`TEXT[]` columns: `"{uuid}"` or `{"item1","item2"}` — pg8000 cannot auto-cast
- Status columns use string enums: `'pending'|'processing'|'done'|'failed'` for documents; `'pending'|'generating'|'ready'|'failed'` for stage2
- `content_hash` columns (SHA-256 hex) on `documents` and `rag_chunks` enable idempotent re-runs
- `DB` context manager: one connection per `with DB() as db:` block — short-lived, explicit commits

Evidence: `poc/db/init.sql`, `poc/db/stage2.sql`, `poc/db.py`, `poc/pipeline/runner.py:126-143`

### 9) Evidence

- `poc/pipeline/epic_generator.py` (LLM conventions, naming)
- `poc/pipeline/runner.py` (error handling, DB conventions)
- `poc/config.py` (constant naming)
- `poc/db.py` (DB pattern)
- `poc/db/init.sql` (schema conventions)
