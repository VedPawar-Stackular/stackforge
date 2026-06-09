# StackForge — Claude Code Context

You are working on **StackForge**, an AI-powered SDLC automation platform built by **Stackular Technologies**. This file transfers full project context from prior research sessions. Read it completely before doing anything.

---

## What This Project Is

StackForge ingests raw client requirements and automates the software development lifecycle through a 6-stage AI pipeline. It produces Azure DevOps work items, code drafts, QA test cases, PR descriptions, and a searchable RAG knowledge base. The platform handles multiple clients and concurrent projects simultaneously.

**Your specific research role:** Token cost optimization across every stage of the pipeline. Every architectural and implementation decision you make should account for minimising AI API token usage without sacrificing output quality.

The AI coding agent platform currently in use for Stage 4 is **[Multica](https://multica.ai/)** — open-source, runs Claude Code under the hood. Stackular plans to clone it. It uses a browser board, a local daemon, and a CLI (`multica issue assign`, `multica workspace list`, etc.). Workspaces are created at `~/multica_workspaces/{issue-id}/`.

---

## The Pipeline

```
[Stage 1] Requirement Ingestion
          ↓
[Stage 2] Epic & User Story Generation → pushed to Azure DevOps
          ↓
[Stage 3] Sprint & Task Planning
          ↓
[Stage 4] AI-Assisted Development (Multica / Claude Code agents)
          ↓
[Orchestrator Agent] ← SE review gate via Lark — loops until SE approves
          ↓
[Stage 5] QA Test Case Generation & Bug Loop
          ↓
[Stage 6] PR Generation + RAG Knowledge Base vectorisation
```

Every stage has a human checkpoint. No stage auto-progresses without human approval. Stages 4 and 5 are the highest token-cost stages.

---

## Foundational Rules (Apply Everywhere)

These are non-negotiable across the entire codebase. Every AI call must comply.

**1. Model routing.** Never use a premium model for a task a cheap model can handle.
- Cheap (`claude-haiku`): classification, extraction, formatting, routing, summarisation passes
- Mid (`claude-sonnet`): code generation, story generation, test case generation
- Premium (`claude-opus`): architectural decisions, novel security-sensitive code, cross-system reasoning only
- The router itself runs on the cheap model. Implement routing at the Go backend level between task loading and dispatch.

**2. Prompt caching.** All system prompts, static project context, and codebase files re-sent across turns must use Anthropic prompt caching. Same context re-read hundreds of times per day = 90% cost reduction on cache hits. Mark cacheable blocks explicitly in API calls.

**3. Batch API.** Every non-real-time generation step uses the Anthropic Batch API (50% cheaper than sync). Rule: sync API only when a human is actively waiting for the result in that same interaction. Everything else — test case generation, embedding, PR description writing, sprint estimation — is a batch job.

**4. Structured outputs.** All generation calls specify a strict JSON schema and a `max_tokens` cap. Models fill fields; they do not narrate. No free-form prose outputs except for PR descriptions and human-facing comments.

**Combined effect:** A call that applies all four — cheap model, cached prompt, batch, JSON output — costs ~3–5% of a naive unoptimised equivalent call.

---

## Stage-by-Stage Architecture Decisions

### Stage 1 — Requirement Ingestion

- **Never send full PDFs or transcripts to a capable model.** Always run a cheap summarisation pass first.
- **Map-reduce pattern:** Chunk document → cheap model summarises each chunk in parallel (batch) → summaries combined → capable model generates structured requirements from summaries only.
- Chunk size: 250–300 words at natural boundaries (paragraphs, section headers).
- Cache processed document extractions immediately after first use. Never re-process an unchanged document.
- **Chunk overlap:** Add ~35-word tail overlap between adjacent chunks (sliding window) so requirements that span a chunk boundary appear in full in at least one chunk's summary. Not yet implemented in POC — flag for production.

**POC status: built and validated.** See `poc/` directory. Ran against real CareFlow client documents (SOW, FRS, meeting transcript) — extracted 130 requirements across 4 types and generated 18 clarification questions. End-to-end pipeline takes ~2 minutes per project.

### Stage 2 — Epic & User Story Generation

- **Hierarchical generation:** cheap model decomposes requirements into epic themes first, then mid-tier model generates per-epic user stories.
- Use few-shot prompting with the company's own past user stories as examples. Format is demonstrated, not described in instructions — this shortens prompts and improves consistency.
- Every generation call returns strict JSON. Schema: `{ id, title, description, acceptanceCriteria: [], storyPoints, assignee }`.

### Stage 3 — Sprint & Task Planning

- Only send stories for the current sprint window. Never send the full backlog.
- Estimation uses RAG: retrieve the 3 most similar past user stories + their actual completion times from the Stage 6 knowledge base. Pass as context. More accurate than generating estimates from scratch, and cheaper.
- This stage's RAG retrieval queries the same KB that Stage 6 populates — self-referential and self-improving across sprints.

### Stage 4 — AI-Assisted Development (Multica)

**RAG on codebase (most important):**
- Embed the task description on receipt.
- Query the codebase index for top 5–10 relevant files via semantic search.
- Query the skill library for top 3 relevant skills.
- Write ONLY those files and skills to disk for the agent. Never load all skills for every task.

**Conversation history:**
- After 8–10 turns, compress older turns into a 2–3 sentence memory block. Drop raw history. Only the last few raw turns + the summary block travel forward.

**Session file cache:**
- Once a file has been fetched into context within a session, do not re-fetch it. Reference the cached version.

**Code pattern library:**
- Maintain a snippet library indexed by pattern type (auth wrapper, API client, error handler, etc.).
- Agent retrieves and adapts existing patterns rather than generating from scratch.

**Hierarchical agents for complex tasks:**
- Cheap orchestrator reads task, decomposes into 3–5 focused sub-tasks (~1,000 tokens).
- Each sub-agent receives only context relevant to its sub-task (~4,000–6,000 tokens).
- Premium model only for sub-tasks requiring complex reasoning.
- A naive monolithic approach costs ~15,000 tokens/turn. This architecture costs 4,000–6,000 total.

### Stage 5 — QA & Bug Loop

**Test case generation:**
- Generate per acceptance criterion, not per user story. Each AC = one focused batch call. All ACs for a story run in parallel.
- Before generating, check the test case library: embed the AC, retrieve top 3 similar past test cases, prompt the model to adapt them. Adaptation saves 60–70% output tokens vs fresh generation.
- Test case library is cumulative across ALL Stackular clients and projects.

**Bug fix calls:**
- When a test fails, automatically extract ONLY the specific failing function from the file. Do not send the full source file.
- Example: `verifyResetToken()` = 18 lines. Full `auth.service.ts` = 420 lines. Send 18 lines. ~95% token reduction.

**Selective re-testing:**
- Track which acceptance criteria are linked to which code modules.
- After a scoped bug fix, only re-run tests for ACs that touch the modified module. Unchanged ACs skip re-testing.

### Stage 6 — PR Generation & RAG Knowledge Base

**PR generation:**
- Never send the raw git diff to the PR generation model.
- Step 1: cheap model summarises the diff per-file (target: ~500 tokens total).
- Step 2: PR description generated from those summaries, not the ~8,000-token raw diff.

**RAG embedding:**
- Content-hash every document before embedding. If the hash matches the last run, skip embedding entirely.
- Embed summaries, not raw documents. Raw session logs, full code files, and unprocessed transcripts are never embedded.
- Embed user story ACs individually (not the whole story).

**RAG retrieval at query time:**
- Hybrid search: keyword (BM25) + semantic (embedding similarity) → 20–30 candidates.
- Cross-encoder re-ranker filters to top 3–5 most relevant chunks.
- Only those 3–5 chunks reach the main model.

---

## The Orchestrator Agent

A Multica agent that acts as a communication middleware between devs (Stage 4 completion) and Senior Engineers (review gate before Stage 5 begins).

**Flow:**
1. Dev/agent marks task complete → Orchestrator intercepts.
2. Generates a structured summary of what was done.
3. Sends to Senior Engineer via Lark.
4. SE responds → Orchestrator reads response.
5. Determines: approved / needs revision / needs clarification.
6. Routes feedback back to the developer.
7. Loop repeats until SE approves.
8. On approval: task proceeds to Stage 5.
9. Entire conversation stored in the Stage 6 RAG KB (not a separate store).

**Current config:** `claude-haiku-4-5-20251001`, concurrency 6, Lark integration bound.

**Critical issues not yet resolved:**
- The orchestrator is **not yet wired into the Stage 4 completion flow**. Currently Stage 4 ends and the backend immediately marks `status=completed` with no SE gate. This must be fixed before production.
- The Lark integration's **bidirectionality is unconfirmed**. It may only send outbound messages. SE replies need to come back into Multica via a webhook or polling — confirm this with the lead engineer.
- The orchestrator's conversation history **must go into the shared Stage 6 RAG KB**, not a separate isolated store. SE feedback and approval rationale are valuable project artifacts.

---

## RAG Knowledge Base — What Goes In, What Comes Out

The KB accumulates across all 6 stages. By the end of a full pipeline run, anyone on the team can query the entire project history in natural language.

| Stage | What gets embedded | Metadata tags |
|-------|-------------------|---------------|
| 1 | SOW summaries, transcript summaries, normalised requirement objects | `doc_type: requirement`, `client_id`, `project_id`, `source_format` |
| 2 | Epics, User Stories, **per-AC embeddings** | `doc_type: user_story`, `epic_id`, `story_id`, `sprint_id: null` |
| 3 | Sprint assignments, estimates, velocity history | `doc_type: sprint_plan`, `sprint_id`, `story_points`, `assigned_to` |
| 4 | Agent session **summaries** (not logs), design decisions, code patterns | `doc_type: dev_decision \| code_pattern`, `story_id`, `file_path`, `pattern_type` |
| 5 | Approved test cases per AC, test results, bug reports, fix records | `doc_type: test_case \| bug_report`, `story_id`, `ac_id`, `resolution` |
| 6 | PR descriptions, story references, test coverage summaries | `doc_type: pr`, `story_id`, `branch`, `merged_at` |

**Do not embed:** raw conversation logs, raw code files, raw meeting transcripts, unprocessed PDFs.

---

## Multica Internal Architecture (Stage 4)

The system runs across 5 layers: Next.js frontend, Go backend, PostgreSQL, Local Daemon, CLI Agent (Claude Code).

**Key flow:**
1. User assigns issue → Go backend atomically inserts into `agent_task_queue` (prevents race conditions).
2. Daemon maintains 15s WebSocket heartbeat. On `EventDaemonTaskAvailable`, daemon claims task via atomic DB UPDATE (prevents two daemons claiming same task).
3. Daemon prepares environment — **zero LLM calls**: creates workdir, checks out repo, writes `issue_context.md`, writes skill files to `.claude/skills/<name>/SKILL.md`, injects `CLAUDE.md` / `AGENTS.md`.
4. `BuildPrompt()` generates a short 5–20 line task message. This is the only thing sent to the LLM as the task instruction.
5. Claude Code CLI spawned. Discovers `CLAUDE.md` and skills natively from filesystem. Streams events back to daemon.
6. Daemon forwards progress via HTTP POST → backend fires WebSocket → frontend shows live updates.
7. On completion: `CleanupRuntimeConfig()` → daemon POSTs result → `task_usage` logged → `status=completed`.

**Token tracking:** Every task logs to `task_usage` in PostgreSQL. This must capture: `input_tokens`, `output_tokens`, `model`, `stage`, `task_type`, `project_id`, `client_id`. Without all these dimensions, cost data cannot drive optimization decisions.

---

## Known Gaps — Address These

These are confirmed architectural problems that need to be fixed. Do not implement anything that worsens these or works around them — fix them properly.

1. **No RAG retrieval before skill loading.** All skills load for every task regardless of relevance. Add: embed task → query skill library for top 3 → write only those to disk.

2. **Orchestrator not in completion flow.** `status=completed` fires without SE approval. Orchestrator must intercept between task complete and status update.

3. **No timeout/watchdog on daemon.** If CLI agent hangs, the task is stuck forever. Add a watchdog: no stream events for N minutes → kill process → POST failure result → re-queue or mark failed.

4. **`CleanupRuntimeConfig()` only runs on happy path.** If daemon or agent crashes, `CLAUDE.md` is left dirty. Wrap in Go `defer` so it runs regardless of how the task ends.

5. **Workspace isolation not confirmed under concurrency.** Concurrency is 6. If two tasks from the same repo run in parallel and share a directory, file edits will conflict. Each task needs an isolated directory keyed to `issue_id`, not repo name.

6. **No token budget enforcement mid-execution.** Runaway tasks burn unlimited tokens. Daemon should monitor token counts in stream events and kill the process if a per-task budget threshold is crossed.

7. **Model routing absent.** All tasks go to the same model. Routing classifier needed at Go backend level, between `LoadAgentSkills` and `BuildPrompt`.

8. **Skills are all-or-nothing per agent config.** `JOIN agent_skill → skill` loads all skills always. Task-type classification should filter which skills are included before the payload is built.

9. **`BuildPrompt` output not logged.** If the template changes and behaviour differs, there's no way to reproduce or debug the issue. Log the prompt output to the `task_usage` record.

10. **Lark integration bidirectionality unconfirmed.** The orchestrator may only be able to send messages, not receive replies. Confirm with lead engineer before building the review loop.

---

## Decisions Already Made — Do Not Revisit Without Good Reason

- Multica is used temporarily for Stage 4; Stackular will clone it. Do not make assumptions that require long-term Multica dependency.
- `claude-haiku` for the orchestrator agent. Justified: coordination and summarisation only.
- Per-AC test generation (not per-story). Established and working.
- Per-AC embedding (not per-story). Established and working.
- Batch API for all non-real-time generation. Non-negotiable.
- Content hashing for all embedded documents. Already planned in Stage 6.
- Diff summaries (not raw diffs) for PR generation. Established.
- Atomic task claiming in the daemon. Already implemented.
- `task_usage` table in PostgreSQL for token tracking. Already implemented; needs to capture all dimensions listed above.

### Stage 1 POC-specific decisions

- **LLM provider: Groq (free tier)** — `llama-3.1-8b-instant` maps to haiku tier; `llama-3.3-70b-versatile` maps to sonnet tier. Uses `openai` SDK with `base_url="https://api.groq.com/openai/v1"`. Switching to Anthropic API = change base URL + model name strings only, no architecture changes.
- **Database adapter: `pg8000`** — Pure Python PostgreSQL adapter. `psycopg2-binary` has no Python 3.14 wheels and cannot be built without pg_config on Windows. Do not switch back.
- **Vector search: disabled** — `sentence-transformers` requires `torch`/`torchvision` which have no Python 3.14 wheels. Schema has `embedding vector(384)` column ready (currently NULL). BM25 keyword search (`rank_bm25`) is used instead. Re-enable when Python 3.14 torch wheels are available — see `poc/pipeline/embedder.py` and `poc/rag/search.py`.
- **Async concurrency: `asyncio.Semaphore(5)`** — Groq free tier caps at 30 req/min. Semaphore in `poc/pipeline/summarizer.py` limits concurrent LLM calls to 5. Includes exponential backoff retry on 429 errors.
- **UUID array inserts:** `pg8000` cannot auto-cast Python lists to PostgreSQL `UUID[]` columns. Use string literal format `"{uuid}"` with `%s::uuid[]` cast in all SQL that writes to `source_document_ids`. This pattern is in `poc/pipeline/runner.py` and `poc/run_demo.py`.

---

## Conventions

- All AI generation calls return strict JSON. Define the schema before writing the call.
- Every new API call must be logged with at minimum: `input_tokens`, `output_tokens`, `model`, `stage`.
- Every new file-writing or embedding step must check a content hash before executing.
- No raw documents, transcripts, or conversation logs in the RAG store. Summaries only.
- When writing new Multica daemon code, wrap any state-mutation in `defer` if there is a corresponding cleanup operation.
- The orchestrator's conversation data goes into the shared Stage 6 KB. Do not create a separate RAG store for it.

---

## Stage 1 POC — File Map

```
poc/
├── requirements.txt          # All deps unpinned (>=) for Python 3.14 compat
├── .env                      # GROQ_API_KEY, DATABASE_URL (not committed)
├── config.py                 # Shared config — model names, chunk size, BM25/rerank top-k
├── db.py                     # pg8000 DB context manager (cursor must be closed manually — no `with cursor()`)
├── run_demo.py               # CLI runner: full pipeline + rich terminal output
├── db/
│   ├── init.sql              # Schema: clients, projects, documents, doc_chunks, requirements, clarifications, rag_chunks
│   └── seed.py               # Creates demo client/project; writes sample docs to sample_docs/
├── pipeline/
│   ├── parser.py             # PDF (pdfplumber) / DOCX (python-docx) / TXT → plain text
│   ├── chunker.py            # ~275-word chunks at paragraph boundaries (no overlap yet — known gap)
│   ├── summarizer.py         # Cheap model parallel summarisation with semaphore + retry
│   ├── extractor.py          # Capable model: summaries → structured requirements JSON
│   ├── embedder.py           # Stores text in rag_chunks; embedding column left NULL (vector search disabled)
│   ├── clarifier.py          # Cheap model: requirements → clarification questions JSON
│   └── runner.py             # Orchestrates all steps; called by FastAPI background task
├── rag/
│   ├── search.py             # BM25-only search over rag_chunks (semantic search disabled)
│   └── reranker.py           # Passthrough: returns top RERANK_TOP_K BM25 hits
├── api/
│   ├── main.py               # FastAPI app with CORS; mounts all routers
│   ├── models.py             # Pydantic request/response schemas
│   └── routes/
│       ├── projects.py       # CRUD: clients + projects
│       ├── documents.py      # File upload → pipeline via BackgroundTasks
│       ├── requirements.py   # List requirements by project
│       └── clarifications.py # List Qs, submit answers
└── ui/
    └── app.py                # Streamlit 4-tab UI (Setup / Upload / Requirements / Clarifications & Query)
```

**How to run:**
```powershell
# 1. Start database
docker start stackforge-db

# 2. From poc/ directory — terminal demo
python run_demo.py

# 3. API server
python -m uvicorn api.main:app --reload

# 4. Streamlit UI (separate terminal)
python -m streamlit run ui/app.py
```

**Sample client documents** are in `sample_client_docs/` at the repo root (CareFlow HIPAA telehealth platform). Use these for demos.

---