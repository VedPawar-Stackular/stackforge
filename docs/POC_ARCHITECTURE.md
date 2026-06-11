# StackForge POC — Complete Architecture & System Design

> **Audience:** Stackular engineering team. This document explains the entire POC (Stages 1, 1.5, 2 + RAG + Stitch + ADO) end to end: every component, every pipeline step, every design decision and why it was made.
>
> **Source of truth:** `poc/` directory on branch `fix/poc-audit-remediation`. Companion diagram: `Exiladraw/poc_full_architecture.excalidraw`.

---

## Table of Contents

1. [What This POC Is](#1-what-this-poc-is)
2. [High-Level System Overview](#2-high-level-system-overview)
3. [Tech Stack & Foundational POC Decisions](#3-tech-stack--foundational-poc-decisions)
4. [Database Schema](#4-database-schema)
5. [Stage 1 — Requirement Ingestion Pipeline (Step by Step)](#5-stage-1--requirement-ingestion-pipeline-step-by-step)
6. [Stage 1.5 — SDLC Document Generation](#6-stage-15--sdlc-document-generation)
7. [RAG Subsystem — Hybrid Retrieval](#7-rag-subsystem--hybrid-retrieval)
8. [Stage 2 — Epic & User Story Generation (Step by Step)](#8-stage-2--epic--user-story-generation-step-by-step)
9. [Azure DevOps Integration](#9-azure-devops-integration)
10. [Google Stitch Integration (UI Design Generation)](#10-google-stitch-integration-ui-design-generation)
11. [Multica Workspace Prep (Stage 4 Bridge)](#11-multica-workspace-prep-stage-4-bridge)
12. [API Surface (FastAPI)](#12-api-surface-fastapi)
13. [Streamlit UI](#13-streamlit-ui)
14. [Token Cost Optimization — Where Every Saving Comes From](#14-token-cost-optimization--where-every-saving-comes-from)
15. [Robustness & Error-Handling Patterns](#15-robustness--error-handling-patterns)
16. [Known POC Limitations](#16-known-poc-limitations)
17. [How to Run](#17-how-to-run)

---

## 1. What This POC Is

StackForge is Stackular's AI-powered SDLC automation platform. The full vision is a 6-stage pipeline (Requirement Ingestion → Epic/Story Generation → Sprint Planning → AI Development via Multica → QA → PR + RAG Knowledge Base). **This POC implements Stages 1, 1.5, and 2 end to end**, plus the shared RAG store, the Google Stitch design integration, and the Azure DevOps push.

The POC's core research goal is **token cost optimization**: prove that the same output quality can be achieved at a small fraction of the cost of a naive single-big-model approach. Every architectural decision below is justified against that goal. The Stage 2 metrics calculator demonstrates **~87% cost savings** vs the naive baseline at real Anthropic pricing.

What the POC does, in one sentence: *you upload raw client documents (SOW, FRS, meeting transcripts), and ~2 minutes later you have structured requirements, clarification questions, eight SDLC topic documents, a searchable knowledge base, generated UI designs, and epics + user stories with acceptance criteria pushed to Azure DevOps.*

Validated against real CareFlow client documents: **130 requirements extracted across 4 types, 18 clarification questions, full Stage 2 generation**.

---

## 2. High-Level System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Streamlit UI (poc/ui/app.py) — 6 tabs, dark design system,         │
│  15s TTL scoped cache, polls FastAPI                                │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ HTTP (localhost:8000)
┌───────────────────────────▼─────────────────────────────────────────┐
│  FastAPI (poc/api/) — 7 routers, BackgroundTasks for all long work  │
│  projects · documents · requirements · clarifications · docs ·      │
│  epics · stitch                                                     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ direct Python calls
┌───────────────────────────▼─────────────────────────────────────────┐
│  Pipeline layer (poc/pipeline/) — all business logic                │
│  Stage 1: parser → chunker → summarizer → extractor → embedder →    │
│           clarifier → doc_writer → dedup                            │
│  Stage 2: epic_generator → story_generator → stage2_runner          │
│  Extras:  doc_editor · stitch_designer · workspace_prep ·           │
│           ado_client · metrics_calculator                           │
└──────┬──────────────┬──────────────┬──────────────┬─────────────────┘
       │              │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐ ┌─────▼──────────────┐
│ PostgreSQL  │ │ Groq LLM  │ │ Pinecone    │ │ External services  │
│ (pg8000)    │ │ (OpenAI   │ │ (optional   │ │ Azure DevOps REST  │
│ 9 tables    │ │  SDK)     │ │  vectors)   │ │ Google Stitch MCP  │
└─────────────┘ └───────────┘ └─────────────┘ └────────────────────┘
```

Five layers. The UI never talks to the database — everything goes through FastAPI. The pipeline layer never renders anything — it only transforms data and writes to the DB/disk. This mirrors the production Multica architecture (Next.js frontend / Go backend / PostgreSQL / daemon).

---

## 3. Tech Stack & Foundational POC Decisions

| Concern | Choice | Why |
|---|---|---|
| LLM provider | **Groq free tier** via `openai` SDK with `base_url="https://api.groq.com/openai/v1"` | Free for the POC. Switching to Anthropic = change base URL + model strings in `config.py` only — zero architecture changes. |
| Cheap model | `llama-3.1-8b-instant` | Maps to **Haiku tier**: summarisation, classification, clarification, screen extraction, doc editing. |
| Capable model | `llama-3.3-70b-versatile` | Maps to **Sonnet tier**: requirement extraction, user story generation. |
| DB adapter | **pg8000** (pure Python) | `psycopg2-binary` has no Python 3.14 wheels and can't be built on Windows without pg_config. |
| Keyword search | **BM25** (`rank_bm25`) | `sentence-transformers` needs torch — no Python 3.14 wheels. BM25 is the always-on baseline. |
| Semantic search | **Pinecone Inference** (`multilingual-e5-large`, 1024-dim), optional | Server-side embedding — no local model download. Enabled only when `PINECONE_API_KEY` is set; system degrades gracefully to BM25-only. |
| Concurrency | `asyncio.Semaphore(5)` + exponential backoff on 429 | Groq free tier caps at 30 req/min. Semaphores are created inside async functions (or module-level in the summarizer, safe in 3.10+) to avoid event-loop ownership bugs when run via `asyncio.run()` in FastAPI background threads. |
| ADO client | sync `httpx.Client` | Called from sync route paths; deliberate — do not convert to async without checking the route. |

### The four production rules the POC is architected for

1. **Model routing** — cheap model for classification/extraction/summarisation, mid model for templated generation, premium only for novel reasoning. Implemented at every call site (see §14).
2. **Prompt caching** — all system prompts are static strings, deliberately separated from per-call user content. On Anthropic, marking them cacheable yields ~90% reduction on cache hits. The architecture is "caching-ready" even though Groq doesn't support it.
3. **Batch API** — all generation is non-blocking (FastAPI `BackgroundTasks`); in production these calls become Anthropic Batch jobs (50% cheaper).
4. **Structured outputs** — every generation call uses `response_format={"type": "json_object"}` plus an explicit JSON schema in the prompt and a `max_tokens` cap. Models fill fields, they don't narrate (~40% output token reduction).

`config.py` also holds a `PRICING` table (real Anthropic per-1M-token rates) and a `MODEL_TIER` mapping so the metrics calculator can report what each call **would** cost on Anthropic in production.

---

## 4. Database Schema

Nine tables across two SQL files (`db/init.sql`, `db/stage2.sql`) plus one migration (`db/migrate_key_specifics.py`).

### Stage 1 tables (`init.sql`)

| Table | Purpose | Key columns |
|---|---|---|
| `clients` | One row per client company | `id`, `name` |
| `projects` | One row per engagement; carries pipeline state | `status` (pending→processing→ready/failed), `stage2_status` (idle→generating→ready/failed), `stitch_project_id`, `stitch_project_url` |
| `documents` | One row per uploaded file | `content_hash` (SHA-256 of raw bytes — dedup key), `status`, `error_message` |
| `doc_chunks` | ~275-word chunks of each document | `chunk_index`, `raw_text`, `summary` (filled by cheap model) |
| `requirements` | Structured extraction output | `req_type` (functional/non_functional/constraint/assumption), `sdlc_topic` (8-value taxonomy), `title`, `description`, `key_specifics TEXT[]` (verbatim client values), `confidence REAL`, `source_document_ids UUID[]`, `status` (active/duplicate) |
| `clarifications` | AI-generated questions for the client | `question`, `context`, `priority`, `answer`, `status` (open/answered) |
| `rag_chunks` | The knowledge base | `content_type` (chunk_summary/requirement/clarification), `text`, `embedding vector(384)` (currently NULL — local embeddings disabled), `metadata JSONB`, `content_hash` |

### Stage 2 tables (`stage2.sql`)

| Table | Purpose | Key columns |
|---|---|---|
| `epics` | Theme-level groupings | `title`, `description`, `theme`, `requirement_ids UUID[]`, `ado_work_item_id/url` |
| `user_stories` | Per-epic stories | `acceptance_criteria TEXT[]`, `story_points`, `assignee`, `ado_work_item_id/url`, `status` |
| `stage2_metrics` | **Every LLM call logged** | `step`, `model`, `input_tokens`, `output_tokens`, `duration_ms` — feeds the savings report |

Cascade behaviour: deleting a project cascades to documents → doc_chunks, requirements, clarifications, epics → user_stories, stage2_metrics. `rag_chunks` has **no FK** and is deleted explicitly in the delete-project route.

### pg8000 gotchas baked into the code

pg8000 cannot auto-cast Python lists to PostgreSQL arrays. Two patterns are used everywhere:
- **UUID[]**: build a literal string `"{uuid1,uuid2}"` and cast with `%s::uuid[]` (runner.py, stage2_runner.py).
- **TEXT[]**: `text_array_literal()` helper in `pipeline/utils.py` escapes quotes/backslashes and builds `{"a","b"}` (used for `key_specifics` and `acceptance_criteria`).

`db.py` wraps pg8000 in a `DB` context manager: fresh connection per use, commit on clean exit, rollback on exception. Cursors are closed manually (pg8000 cursors don't support `with`).

---

## 5. Stage 1 — Requirement Ingestion Pipeline (Step by Step)

**Entry points:** `POST /projects/{id}/documents` (FastAPI, background task) or `run_demo.py` (CLI). Both call `pipeline/runner.py :: ingest_document()`.

**The core token principle: never send raw documents to a capable model.** A cheap map-reduce pass compresses everything first.

### Step 0 — Content-hash gate

SHA-256 of the raw file bytes is checked against `documents.content_hash` for this project. If the same file was already processed (`status='done'`), the pipeline **returns immediately** — zero LLM calls for re-uploads. Otherwise a `documents` row is inserted with `status='processing'`.

### Step 1 — Parse (`parser.py`, no LLM)

PDF → `pdfplumber`, DOCX → `python-docx`, TXT → direct decode. Output is cleaned plain text (blank-line runs collapsed, trailing whitespace stripped).

### Step 2 — Chunk (`chunker.py`, no LLM)

- Split on blank lines (paragraph boundaries); paragraphs longer than 1.5× target are split at sentence endings.
- Merge paragraphs into chunks of ~**275 words** (`CHUNK_TARGET_WORDS`), with a 1.2× tolerance before cutting.
- **35-word tail overlap** (`CHUNK_OVERLAP_WORDS`): the last 35 words of chunk *i−1* are prepended to chunk *i* as `[...] <tail>`. This sliding window ensures a requirement spanning a chunk boundary appears in full in at least one chunk's summary.

### Step 3 — Summarize, map phase (`summarizer.py`, cheap model, parallel)

All chunks are summarised **concurrently** via `asyncio.gather`, throttled by a **module-level shared `Semaphore(5)`** (a true global gate across concurrent uploads, not per-document). Exponential backoff with jitter on 429s (6 retries).

**Doc-type-aware prompting** — the filename decides the mode:
- *Spec mode* (FRS/SOW/anything not matching transcript keywords): extraction-preserving bullet list, max 15 bullets, `max_tokens=600`. Prompt explicitly demands verbatim numbers, time limits, field names, UI details — "do not paraphrase".
- *Transcript mode* (filename matches `transcript|meeting|notes|call|interview|discussion|minutes`): 2–3 sentence summary + up to 5 key points, `max_tokens=300`.

Defaulting unknown docs to spec mode is deliberate: safer to over-extract than to lose detail.

Chunks + summaries are stored in `doc_chunks`.

### Step 4 — Extract, reduce phase (`extractor.py`, capable model, batched)

Summaries (never raw text) go to the 70B model, **in batches of 10** (`EXTRACTOR_BATCH_SIZE`) processed in parallel. Batching exists because a 130-requirement project would truncate at `max_tokens=2048` in a single call.

Each requirement comes back as strict JSON:

```json
{
  "req_type": "functional | non_functional | constraint | assumption",
  "sdlc_topic": "requirements | design | technical | timeline | budget | testing | integrations | team_and_process",
  "title": "max 10 words",
  "description": "...",
  "key_specifics": ["up to 3 verbatim values from the source"],
  "confidence": 0.85
}
```

Post-processing sanitizes everything: confidence clamped to [0,1], `key_specifics` capped at 3 strings, invalid enums fall back to safe defaults (`functional` / `requirements`) with a logged warning. If a batch returns unparseable JSON it contributes 0 requirements (logged); if **all** batches fail, a typed `ExtractionError` is raised so the document is marked failed rather than silently empty.

`key_specifics` is the detail-preservation channel: exact client-stated values ("15-minute timeout", "HL7 FHIR R4") survive summarisation → extraction → story generation, anchoring Stage 2 acceptance criteria to real client language.

### Step 5 — Embed into the RAG store (`embedder.py`)

Chunk **summaries** (not raw chunks) and requirements (`title: description`) are upserted into `rag_chunks`, each guarded by its own SHA-256 `content_hash` (skip if unchanged). If Pinecone is enabled, the same text is embedded server-side and upserted with metadata (`project_id`, `content_type`, `doc_type`, …). Pinecone failures are logged and swallowed — they must never roll back the PostgreSQL write.

This enforces the platform rule: **summaries only in the KB, never raw documents.**

### Step 6 — Clarification questions (`clarifier.py`, cheap model)

All active requirements (compact `[TYPE] title: description` lines) go to the cheap model, which returns 4–8 targeted questions about ambiguities, gaps, conflicts, and unstated assumptions, each with `context` and `priority` (validated, defaults to medium). Stale open clarifications are deleted first so re-uploads produce a fresh set; answered ones are preserved.

### Step 7 — SDLC docs (`doc_writer.py`, **no LLM**) — see §6.

### Step 7.5 — Cross-document dedup (`runner.py :: _dedup_requirements`, no LLM)

Runs after **every** upload (idempotent). Compares all active requirement titles pairwise using **Jaccard similarity on lowercase title tokens**. At ≥ 0.5 similarity, the lower-confidence requirement is marked `status='duplicate'` (requirements are pre-sorted by confidence DESC, so the survivor is always the higher-confidence one), and its `source_document_ids` are merged into the survivor. Stage 2 skips duplicates. This is what keeps a 3-document project (SOW + FRS + transcript, heavy overlap) from generating triple stories.

### Finalization

Document marked `done`; on any exception it's marked `failed` with the error message stored. The background task then recomputes the **project** status from live document counts (any processing → processing; all done → ready; else failed). The `/status` endpoint independently computes the same thing on read (including a `partial` state) — this avoids the race where concurrent background tasks overwrite `projects.status` unpredictably.

---

## 6. Stage 1.5 — SDLC Document Generation

After extraction, `doc_writer.py` writes **eight Markdown files** to `poc/output/{project_id}/` — one per SDLC topic (`requirements`, `design`, `technical`, `timeline`, `budget`, `testing`, `integrations`, `team_and_process`).

**Zero LLM calls.** Requirements are already structured; this is pure formatting: group by topic, then by req_type, render title/description/confidence.

One deliberate enrichment: **`design.md` gets a "Cross-cutting Context" section** appended — all non-functional and constraint requirements from *other* topics, plus all integration requirements. Rationale: accessibility rules, performance budgets, compliance constraints, and external APIs all shape UI design even when they're not tagged `design`. This section is what makes the Stitch generation context-rich.

`doc_editor.py` provides LLM-assisted editing: the current file + a plain-English instruction go to the cheap model (`max_tokens=4096`), which returns the full updated markdown; written back to disk. Exposed via `POST /docs/{topic}/edit`.

These files later feed Stitch (design screens) and are injected into Multica agent workspaces by `workspace_prep.py`.

---

## 7. RAG Subsystem — Hybrid Retrieval

**Write path** (§5 step 5 + clarifications): three content types enter `rag_chunks` — chunk summaries, requirements, and **answered clarification Q&A pairs** (`embed_clarification` fires inside the answer-submission route, storing `"Q: …\nA: …"`). Client answers are the highest-confidence content in a project, so they're made retrievable immediately.

**Read path** (`POST /projects/{id}/query` → `rag/search.py`):

1. **BM25** over all of the project's `rag_chunks` (tokenized lowercase, `rank_bm25`), top 20.
2. **Pinecone semantic search** (if enabled): query embedded via Pinecone Inference (`input_type="query"`), top 20, filtered by `project_id` metadata.
3. **Reciprocal Rank Fusion** merges the two ranked lists: `RRF(d) = Σ 1/(60 + rank_i(d))`. RRF was chosen because it combines rankings without needing to normalise incomparable score scales (BM25 scores vs cosine similarities). Dedup by chunk id; BM25 text is the source of truth.
4. **Rerank** (`rag/reranker.py`): currently a pass-through that takes the top 5 (`RERANK_TOP_K`). The cross-encoder is disabled pending Python 3.14-compatible torch wheels — the interface is in place so enabling it is a drop-in change.

Only those top 3–5 chunks would reach a main model in production — that's the platform rule (20–30 candidates → rerank → 3–5 chunks).

**Pinecone client details** (`rag/pinecone_client.py`): lazy singleton client + index; index auto-created on first use (serverless, cosine, 1024-dim) with a readiness poll; metadata carries the text (capped at 2,000 chars — summaries fit) so search results are self-contained; every operation is wrapped so failures degrade to BM25-only.

---

## 8. Stage 2 — Epic & User Story Generation (Step by Step)

**Entry point:** `POST /projects/{id}/generate-epics` → background task → `stage2_runner.py :: run_stage2()`.

The design is **hierarchical generation**: a cheap model does the grouping, a mid model does the writing, and each writing call sees only its own slice of context.

### Step 0 — Reset

Previous stories, epics, and metrics for the project are deleted (stories before epics — FK), `stage2_status='generating'`. Re-runs never accumulate stale data.

### Step 1 — Fetch + prepare context (no LLM)

- All non-duplicate requirements fetched (id, title, req_type, sdlc_topic, description, key_specifics).
- **Global constraints extracted by a rule-based filter — zero LLM cost**: any requirement whose `sdlc_topic` ∈ {budget, testing, integrations, team_and_process} (always project-wide topics) or whose `req_type == 'constraint'`. Technical/design topics are excluded — they're usually feature-specific.
- **Answered clarifications fetched** — direct client answers, treated as definitive.

### Step 2 — Epic decomposition (`epic_generator.py`, cheap model, 1 call)

The single most token-engineered call in the POC:

| Optimization | Mechanism | Saving |
|---|---|---|
| Cheap model | Theme grouping is classification, not generation | ~1/10th Sonnet cost |
| **Titles only** | Input lines are `idx: [req_type] sdlc_topic \| title` — descriptions deliberately excluded | ~77% input reduction (~3K vs ~13K tokens for 130 reqs) |
| **Integer indices, not UUIDs** | Prompt uses `1..N`; code maps back to UUIDs after parsing | Shorter tokens, and a model can't mangle an index the way it can hallucinate a UUID |
| Strict JSON + `max_tokens=1500` | Schema demonstrated in the prompt | ~40% output reduction |
| Static system prompt | Eligible for Anthropic prompt caching | 90% on cache hits in production |

Output: 3–8 epics, each `{theme, title, description, requirement_ids: [int]}`. Post-processing resolves indices → UUIDs (out-of-range dropped with a warning), runs a **coverage check** that logs any orphan requirements not assigned to an epic, and fills missing keys with defaults. Tokens + duration logged to `stage2_metrics` as `epic_decomposition`.

### Step 3 — Story generation (`story_generator.py`, mid model, N parallel calls)

One call **per epic**, all run concurrently (`asyncio.gather`, `Semaphore(5)`). Each prompt contains:

1. The epic title + description.
2. **Only that epic's requirements** — full descriptions plus `(specifics: …)` from `key_specifics`. ~85% per-call input reduction vs sending all 130 requirements.
3. **Global constraints block** (deduped against the epic's own requirements) — "apply to ALL stories, reflect in acceptance criteria". ~600 extra tokens buys project-wide constraint compliance with no extra LLM call.
4. **Client Confirmations block** — answered clarification Q&A pairs, framed as definitive requirements.

The static system prompt teaches the format with **2 full few-shot examples** (format demonstrated, not described — shorter and more consistent) and is cache-eligible. Output schema per story:

```json
{
  "title": "5-10 words",
  "description": "As a [role], I want [feature] so that [benefit]",
  "acceptance_criteria": ["Given [context], when [action], then [outcome]"],
  "story_points": 3,
  "assignee": null
}
```

3–7 stories per epic, 2–4 BDD acceptance criteria each, Fibonacci story points, `max_tokens=2000`. Each epic call's tokens are logged as `story_generation_epic_N`. Parallelism makes wall-clock ≈ one call, not N calls.

### Step 4 — Persist + finish

Stories inserted (`acceptance_criteria` via `text_array_literal`), `stage2_status='ready'`. Any exception → `'failed'`.

### Metrics report (`metrics_calculator.py`)

Reads `stage2_metrics`, prices every call at **real Anthropic rates** via the tier mapping, and compares against a modelled **naive baseline**: one Opus call, all full requirement descriptions, free-form prose output (×1.4 token multiplier), no routing, no scoping. Each step in the report carries a human-readable `why_this_model` explanation. This report — **~87% savings** on the CareFlow run — is the evidence artifact for the lead engineer.

---

## 9. Azure DevOps Integration

`pipeline/ado_client.py` + `stage2_runner.py :: push_to_ado()`. **Generation and sync are deliberately decoupled** — the lead engineer reviews stories in the UI before pushing.

- ADO REST API **v7.1**, Agile process template (`$Epic`, `$User Story`), sync `httpx.Client`.
- Auth: HTTP Basic with `base64(":" + PAT)`.
- **Area path per project**: `ensure_area_path()` creates `{ADO_PROJECT}\{project_name}` via the Classification Nodes API (409 = already exists = success). Keeps CareFlow, MediBook, etc. separated on one board. If creation fails, the field is omitted entirely (avoids TF401347) and items land in the project default area.
- **Hierarchy**: stories link to their epic via `System.LinkTypes.Hierarchy-Reverse` (child→parent direction — ADO names relations from the child's perspective).
- Acceptance criteria render as an HTML `<ul>` into `Microsoft.VSTS.Common.AcceptanceCriteria`; **all LLM-generated text passes through `html.escape()`** — prevents model output containing `<`, `>`, `&` (or injected script tags) from breaking ADO's rich-text renderer.
- **Idempotent re-push**: items with an existing `ado_work_item_id` are skipped, so re-running never duplicates. Per-item errors are collected and returned, not fatal.

---

## 10. Google Stitch Integration (UI Design Generation)

`pipeline/stitch_designer.py`. Generates high-fidelity UI screens from project requirements via the **Stitch MCP server** (`npx stitch-mcp-server`, spoken to over stdio using the Python `mcp` client).

**Flow** (`generate_for_project`):

1. **Build combined context** — `design.md` (explicit design intent, including its cross-cutting section) **plus** all DB requirements across every SDLC topic, formatted compactly. Both are always combined, not used as sequential fallbacks — functional/technical/integration requirements imply screens too (a booking requirement implies a booking screen; a payment integration implies a payment screen).
2. **Extract screens** (cheap model, `max_tokens=800`): returns 5–8 screens as `{name, label, device: mobile|desktop, prompt}` where `prompt` is a 2–4 sentence Stitch generation prompt. If no requirements exist at all, a static 3-screen scaffold (dashboard/list/detail) is used.
3. **MCP calls**: `create_project(title)` → `generate_screen(projectId, prompt)` per screen → `get_screen_code()` → HTML saved to `poc/output/{project_id}/stitch/screens/`. A known npm package bug can make `generate_screen` fail; handled gracefully — the screen is recorded with an "add manually in Stitch UI" note and the run continues.
4. **DESIGN.md** generated by the cheap model (design tokens as YAML front matter + overview/screens/principles) — Stitch has no design-tokens endpoint, so this is synthesized; a static fallback exists if even that fails.
5. **metadata.json** written (Stitch project id/URL, screen list, timestamp) and Stitch columns persisted on the `projects` row.

**Status tracking is filesystem-based**: a `.generating` flag file while running, `.error` file on failure, `metadata.json` presence = ready. The `GET /stitch` route reads these — no DB polling table needed.

---

## 11. Multica Workspace Prep (Stage 4 Bridge)

`pipeline/workspace_prep.py` — a standalone CLI (`python workspace_prep.py --project-id X --workspace-path Y`) designed to be called **by the Multica Go daemon as a subprocess** after workspace creation, before the Claude Code agent spawns. It injects design context so the agent sees designs natively:

1. `DESIGN.md` → `{workspace}/.claude/DESIGN.md` (Claude Code auto-loads it).
2. Screen HTML files → `{workspace}/design_screens/`.
3. A "Design Reference" section appended to `issue_context.md` (Stitch URL + screen list).
4. `.mcp.json` written so the agent can call Stitch MCP tools live during coding.

Exit code 0 even when no designs exist (non-fatal — agent just starts without design context); 1 only on filesystem errors.

---

## 12. API Surface (FastAPI)

`api/main.py` mounts 7 routers; CORS wide open (POC only). All long-running work uses `BackgroundTasks` + a poll endpoint — uploads and generation return in milliseconds.

| Method & Path | What it does |
|---|---|
| `POST /projects` | Upsert client by name + create project |
| `GET /projects` | List all projects |
| `DELETE /projects/{id}` | Full cascade delete: DB rows + `rag_chunks` (no FK, explicit) + on-disk `output/{id}/` |
| `GET /projects/{id}/status` | Live-computed status from document counts (processing/ready/partial/failed) + counts |
| `POST /projects/{id}/documents` | Validate type (pdf/docx/txt) + size (≤20 MB) → background ingest → 202 |
| `GET /projects/{id}/documents` | List documents with per-doc status |
| `GET /projects/{id}/requirements` | List requirements (filterable by `req_type`) |
| `GET /projects/{id}/clarifications` | List questions (filterable by status) |
| `POST .../clarifications/{cid}/answer` | Save answer + **embed Q&A into RAG immediately** |
| `POST /projects/{id}/query` | Hybrid RAG search → RRF → top 5 |
| `GET /projects/{id}/docs` / `GET .../docs/{topic}` | SDLC doc metadata / content |
| `POST .../docs/{topic}/edit` | LLM edit via plain-English instruction |
| `POST /projects/{id}/generate-epics` | Trigger Stage 2 (202, background) |
| `GET /projects/{id}/stage2-status` | idle/generating/ready/failed + counts + ado_pushed |
| `GET /projects/{id}/epics` | Epics with story counts (**single GROUP BY query — no N+1**) |
| `GET /projects/{id}/stories` | All stories in one call (bulk endpoint added to kill N per-epic round trips in the UI) |
| `GET .../epics/{eid}/stories` | Stories for one epic |
| `POST /projects/{id}/push-to-ado?area_path=` | Background ADO push |
| `GET /projects/{id}/stage2-metrics` | The savings report |
| `POST /projects/{id}/stitch/generate` / `GET .../stitch` | Trigger / poll Stitch generation |

Security touches: `validate_project_id()` rejects non-UUID path params on every route that builds filesystem paths from them (path-traversal guard); upload type allowlist + size cap.

---

## 13. Streamlit UI

`ui/app.py` (~1,800 lines). Six tabs: **Setup** (client/project create/select/delete), **Upload** (drag-drop + live pipeline progress), **Requirements** (cards + Plotly topic chart), **Documents** (SDLC doc viewer/editor + Stitch design generation/preview), **Clarifications** (answer questions + RAG query box), **Epics & Stories** (generate, browse, ADO push, metrics dashboard with the savings breakdown).

Notable engineering:
- **Custom scoped GET cache** (replaces `@st.cache_data`): per-path 15s TTL dict, with `invalidate_cache(*paths)` after every mutation and `invalidate_project_cache(project_id)` for blanket invalidation. Mutations feel instant without refetch storms.
- Single persistent `httpx.Client` via `@st.cache_resource` (TCP connection reuse across reruns).
- The UI talks **only** to FastAPI — never imports pipeline code or touches the DB.

---

## 14. Token Cost Optimization — Where Every Saving Comes From

The complete map of optimization → location → mechanism:

| # | Optimization | Where | Saving |
|---|---|---|---|
| 1 | Map-reduce ingestion (cheap summarise → capable extract; raw text never reaches the 70B model) | summarizer/extractor | Bulk of Stage 1 cost |
| 2 | Content-hash skip on re-upload | runner.py step 0 | 100% on unchanged docs |
| 3 | Content-hash skip on re-embed | embedder.py | 100% on unchanged chunks |
| 4 | Doc-type-aware summary budgets (600 vs 300 tokens) | summarizer.py | Output capped per doc type |
| 5 | Extraction batching (10/batch, parallel) | extractor.py | Prevents truncation waste + retry-everything blasts |
| 6 | Model routing: cheap for epics/clarifier/screens/doc-edit, mid for extraction/stories | every call site | ~10x on routed calls |
| 7 | Titles-only epic input | epic_generator | ~77% input |
| 8 | Integer indices instead of UUIDs | epic_generator | Fewer tokens, no UUID hallucination |
| 9 | Per-epic scoped story context | story_generator | ~85% input per call |
| 10 | Rule-based global-constraint injection (no LLM classification pass) | stage2_runner | A whole call class avoided; +600 tokens/epic |
| 11 | Strict JSON schema + max_tokens caps on every call | everywhere | ~40% output |
| 12 | Few-shot format demonstration instead of instruction prose | story_generator | Shorter prompt, better consistency |
| 13 | Static system prompts (cache-ready) | everywhere | 90% on cache hits (production) |
| 14 | Jaccard dedup before Stage 2 | runner.py | No stories generated for duplicate requirements |
| 15 | Summaries-only RAG store + top-5 rerank gate | embedder/search/reranker | Minimal retrieval context downstream |
| 16 | Parallelism (`asyncio.gather` + semaphore) | summarizer/extractor/stories | Time, not tokens — wall-clock ≈ 1 call |

Combined effect measured by the Stage 2 metrics calculator: **~87% cheaper than the naive baseline** at Anthropic list prices.

---

## 15. Robustness & Error-Handling Patterns

- **Retry with exponential backoff + jitter** on every LLM call (`2^attempt + random(0,1)` seconds; 4–6 retries), re-raising on final failure.
- **Global `Semaphore(5)`** caps concurrent LLM calls under Groq's 30 req/min free-tier limit; created inside async functions where event-loop ownership matters.
- **Status state machines** at two levels: per-document (pending→processing→done/failed + error_message) and per-project (computed live from document counts to avoid background-task races; includes `partial`).
- **JSON defensiveness everywhere**: parse failures logged with a raw-response snippet and degraded (empty batch / empty list), never crash; wrapper-tolerant parsing (accepts both bare arrays and `{"key": [...]}`); enum sanitization with safe defaults; `setdefault` for all required keys.
- **Typed failure for total loss**: `ExtractionError` when every batch fails — the document is marked failed instead of silently producing zero requirements.
- **Optional dependencies degrade, never break**: Pinecone down → BM25-only; Stitch screen bug → project still created with manual-add notes; doc_writer failure → warning, ingestion continues.
- **Idempotency**: re-upload (hash gate), re-push to ADO (work-item-id skip), dedup pass, Stage 2 reset-before-run, `ensure_area_path` 409 handling.
- **Injection guards**: `html.escape()` on all LLM output sent to ADO; UUID validation on path params used in filesystem paths; TEXT[] literal escaping.

---

## 16. Known POC Limitations

Deliberate scope cuts — known and documented, not accidents:

1. **Local embeddings disabled** — `rag_chunks.embedding` stays NULL (no Python 3.14 torch wheels). Pinecone covers semantic search when enabled; otherwise BM25-only.
2. **Reranker is a pass-through** (top-5 by retrieval rank) — the cross-encoder slot is wired but disabled for the same reason.
3. **No real prompt caching or Batch API on Groq** — the architecture is shaped for both; they activate on the Anthropic switch.
4. **Upload endpoint returns a stub document id** — the real row is created inside the background task; the UI tracks via the documents list, not that id.
5. **CORS `allow_origins=["*"]`** — POC only.
6. **Stage 2 token logging is POC-local** (`stage2_metrics`); production needs the full `task_usage` dimensions (stage, task_type, project_id, client_id).
7. **Stages 3–6 not in this POC** — sprint planning, Multica execution (orchestrator/SE gate), QA loop, and PR generation exist as architecture decisions in `CLAUDE.md`, with `workspace_prep.py` as the first Stage 4 bridge artifact.

---

## 17. How to Run

```powershell
# 1. Database
docker start stackforge-db
# First time only: apply init.sql, stage2.sql, then python db/migrate_key_specifics.py

# 2. From poc/ — API server
python -m uvicorn api.main:app --reload

# 3. Streamlit UI (separate terminal)
python -m streamlit run ui/app.py

# Optional: CLI demo (Stage 1 only, CareFlow sample docs)
python run_demo.py
```

Required in `poc/.env`: `DATABASE_URL`, `GROQ_API_KEY`. Optional: `PINECONE_API_KEY` (semantic search), `STITCH_API_KEY` (design generation), `ADO_ORG`/`ADO_PROJECT`/`ADO_PAT` (DevOps push).

**Demo script (the 5-minute walkthrough):** create project → upload the three CareFlow docs from `sample_client_docs/` → watch ~130 requirements extract in ~2 min → answer a clarification (note it embeds into RAG and feeds Stage 2 prompts) → open `design.md`, generate Stitch screens → generate epics & stories → open the metrics tab and show the ~87% savings breakdown → push to ADO and show the Epic→Story hierarchy under the project's area path.
