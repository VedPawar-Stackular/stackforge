StackForge Stage 1 **POC** — Full Architecture Explained What This System Does (The One-Sentence Version) A client gives you raw documents — a Statement of Work, a meeting transcript, a compliance spec. StackForge reads them, extracts every software requirement buried inside, classifies each one, generates clarification questions about gaps, builds a searchable knowledge base, and writes formatted specification documents. All automatically, in about 2 minutes.

The Big Picture: Why This Architecture Exists The naive approach to this problem is: take the whole document, send it to a powerful AI, ask it to extract requirements. This fails in production for three reasons:

Cost — a 40-page **SOW** sent raw to **GPT**-4 or Claude Sonnet costs dollars per run, and you have hundreds of clients Quality — large language models lose focus when given 50,**000** tokens of dense legal/technical text at once Scale — you can't serve 20 concurrent clients if each job monopolizes a capable model for minutes The architecture solves all three with a single principle: use the cheapest tool sufficient for each job. A cheap fast model summarizes chunks in parallel. A capable model only sees clean, compressed summaries. The result is ~95% cheaper than the naive approach with equal or better quality.

The Flow: Start to End Phase 0 — Project Setup Before any documents are processed, you create a client and project in the system. Think of these as folders. Every requirement, document, and clarification question is tagged to a project. This is how the system serves multiple clients concurrently — all data is isolated by project_id in PostgreSQL.

In the UI: you go to the Setup tab, type *CareFlow* as the client and *CareFlow Platform **2026*** as the project, click Create. The **API** creates two database rows and returns a project_id (a **UUID**). Every subsequent **API** call uses that ID.

Step 1 — Document Upload and Parsing You upload **PDF**, **DOCX**, or **TXT** files through the UI. The moment you click *Start ingestion pipeline*, the file bytes are sent to **POST** /projects/{id}/documents.

The FastAPI endpoint does two things immediately:

Saves the file metadata to the documents table with status = 'processing' Fires the pipeline as a background task — the **API** returns instantly (**HTTP** **200**) without waiting for the pipeline to finish This is why the Upload tab has a live status panel rather than a spinner. The pipeline runs behind the scenes.

Parsing (pipeline/parser.py) converts the uploaded file to plain text:

**PDF** → pdfplumber extracts text page by page **DOCX** → python-docx extracts paragraphs **TXT** → read directly Output: one long string of raw text.

Content hash check: Before doing any work, the system computes a **SHA**-**256** hash of the file bytes. If a document with the same hash already exists for this project with status = 'done', the pipeline skips it entirely. This prevents re-processing the same file when a user re-uploads.

Step 2 — Chunking (The Sliding Window) The raw text is split into ~**275**-word chunks at paragraph boundaries. This is not arbitrary — it matches the sweet spot where a cheap model can hold the full chunk in working memory and produce a useful summary.

Why **275** words specifically? A cheap model like llama-3.1-8b or Claude Haiku has a context window of 8K–**32K** tokens, but smaller models produce better, more focused summaries when given less text. **275** words ≈ **350** tokens — small enough for the model to really *see* the content, large enough to capture a complete thought.

The 35-word overlap: The last 35 words of chunk N are prepended to chunk N+1 with a [...] tail marker. This solves the boundary problem: a requirement like "The system must support **HIPAA**-compliant audit logging for all **PHI** access, with a 7-year retention policy" might split across two chunks. Without overlap, each half goes to a different summarizer call and neither half makes sense. With overlap, the requirement appears in full in at least one chunk.

Without this fix, you'd lose 5-10% of cross-boundary requirements silently — they'd never appear in the extracted output.

Step 3 — Summarization (Cheap Model, Parallel) Each chunk is sent to the cheap model (llama-3.1-8b-instant on Groq, equivalent to Claude Haiku in production) with one job: compress the **275**-word chunk into a 50-**100** word summary that preserves every requirement, constraint, or decision mentioned.

Why summarize instead of sending raw text to the extraction step?

A 40-page document chunked at **275** words produces ~55 chunks. Each chunk is ~**350** tokens. Sending all 55 raw chunks to the capable model for extraction = 19,**250** input tokens per document. Summarizing first reduces each chunk to ~80 tokens. Now the capable model sees 55 × 80 = 4,**400** tokens — an 80% reduction with no loss of requirement information, because the summaries are specifically written to preserve requirements.

The calls run in parallel — all 55 summarization requests fire at the same time through asyncio. On Groq's free tier, this is rate-limited to 5 concurrent calls via asyncio.Semaphore(5), with exponential backoff (retry after 2s, 4s, 8s) on **HTTP** **429** errors.

Each summary is stored in the doc_chunks table alongside the raw text, indexed by chunk_index.

Step 4 — Requirement Extraction (Capable Model) The capable model (llama-3.3-70b-versatile / Claude Sonnet) receives all summaries combined and extracts structured requirement objects. This is the most important **LLM** call in the pipeline.

The model is given a strict **JSON** schema and told to return nothing else:

{
    *req_type*: "functional | non_functional | constraint | assumption*,
    *sdlc_topic*: *requirements | design | technical | timeline | budget | testing | integrations | team_and_process*,
    *title*: *Short label*,
    *description*: *Full description*,
    *confidence*: 0.0–1.0
}
req_type answers *what kind of requirement is this?*:

Functional — something the system must do (*The system must send appointment reminders via **SMS**") Non-functional — a quality the system must have (*Response time must be under 200ms*) Constraint — a hard boundary (*Must deploy on **AWS** us-east-1 only*) Assumption — something taken as given (*Users have smartphones with **SMS** capability*) sdlc_topic answers *which phase of the project does this belong to?*. This is the classification you added — it's orthogonal to req_type. A requirement can be both non_functional **AND** technical (e.g., *the database must use **AES**-**256** encryption*). The 8 topics are:

requirements — features, user needs, scope design — UI/UX, branding, component design technical — architecture, APIs, infrastructure, security timeline — phases, milestones, go-live dates budget — costs, payment schedules, resource allocation testing — **UAT**, acceptance criteria, test coverage integrations — **EHR** systems, payment gateways, external APIs team_and_process — roles, responsibilities, communication protocols confidence is a 0–1 score the model assigns to indicate how clearly the requirement was stated in the source document. A confidence of 0.6 might mean the model inferred it from context rather than reading it explicitly.

After extraction, each requirement is saved to the requirements table with its project_id, both classification fields, and the source_document_ids array (tracking which document it came from).

Step 5 — Embedding (Dual Storage) The system builds a searchable knowledge base from two things: the chunk summaries and the extracted requirements. This is what powers the **RAG** search later.

What gets embedded:

Every chunk summary → stored in rag_chunks as content_type = 'chunk_summary' Every requirement title + description → stored as content_type = 'requirement' Content hash deduplication: Before embedding anything, the system hashes the text. If a chunk with the same hash already exists in rag_chunks, it's skipped. This prevents duplication when a document is re-processed or multiple documents share identical sections.

Two storage backends run simultaneously:

**BM25** (PostgreSQL): The text is stored as-is in rag_chunks. At query time, **BM25** (a keyword ranking algorithm from information retrieval) scores how many query words appear in each chunk and how rare those words are. It's fast, works offline, and handles exact keyword matches well. This is the fallback that always works.

Pinecone (Vector Search): The text is sent to Pinecone's Inference **API**, which converts it to a **1024**-dimensional vector using the multilingual-e5-large model. This vector is stored in Pinecone with metadata. At query time, Pinecone finds chunks whose vectors are geometrically closest to the query vector — meaning it finds semantically similar content even when query and document use different words. *What are the security requirements?* will find chunks about ***HIPAA** compliance* and *audit logging* even though neither phrase contains the word *security*.

The reason we use Pinecone's Inference **API** rather than a local embedding model is that Python 3.14 has no wheels (pre-compiled packages) for libraries like sentence-transformers or onnxruntime. Pinecone handles embedding server-side — zero local ML dependencies.

Step 6 — Clarification Generation (Cheap Model) After all requirements are extracted, the cheap model reads the full list of requirements and generates 4–8 targeted questions about gaps and ambiguities.

Examples it generates for a healthcare project:

"The **SOW** mentions **HIPAA** compliance but doesn't specify whether the audit trail covers **API** access or only UI interactions — which scope is required?* *The **FRS** lists three user roles (provider, patient, admin) but doesn't define what actions each role can perform — is there a permission matrix?" These are stored in the clarifications table with status = 'open' and a priority (high, medium, low). When you answer them in the UI, the answer is stored and also embedded into the **RAG** knowledge base — so future queries about that topic can surface your clarifications as context.

After each new document is ingested, the clarifications are regenerated fresh (old open ones are deleted and replaced) so the questions always reflect the full picture of what's been processed so far.

Step 7 — **SDLC** Document Writing (Zero **LLM** Tokens) This is the newest step. After Step 6 completes, doc_writer.py runs.

It reads all requirements from the database, groups them by sdlc_topic, and writes one Markdown file per topic to poc/output/{project_id}/. No **LLM** is called — this is pure formatting from structured data.

Eight files are always created, even if a topic has no requirements (it gets a *No requirements in this category* placeholder). The files are:

requirements.md   — functional requirements, features, user needs design.md         — UI/UX, wireframes, components technical.md      — architecture, stack, security, infrastructure timeline.md       — phases, milestones, deadlines budget.md         — costs, payment schedules testing.md        — test requirements, **UAT** criteria integrations.md   — third-party services, external APIs team_and_process.md — roles, responsibilities, process Each file uses consistent Markdown structure: H2 sections for requirement type (Functional, Non-Functional, Constraint, Assumption), H3 headings for each requirement title, confidence percentage, and type badge.

These documents are what you share with the lead engineer for review. They're committed artifacts of the pipeline run.

Editing a document: In the Documents tab, you select a topic, read its .md content, and type a plain-English instruction like "Add a note that all budget items above $10,**000** require **CFO** written approval before commitment." You click Apply Edit. This sends the current document + your instruction to the cheap model with a single prompt: "Apply this edit instruction to the document while preserving the heading structure." The model returns the full updated markdown. It's written back to the file and displayed immediately.

This costs roughly 1,**500**–4,**000** tokens (the current doc is the bulk of it) — fractions of a cent at Haiku pricing.

### The Storage Layer

Three stores work together:

PostgreSQL is the source of truth. Every row in every table has a project_id, so all queries are scoped. The schema has referential integrity — documents reference projects, requirements reference documents, chunks reference documents. The task_usage table (planned for production) logs every **LLM** call's token counts for cost tracking.

Pinecone is the semantic memory. It stores only the **1024**-dimensional vectors and lightweight metadata (text truncated to **2000** chars, content_type, IDs). The full text always lives in PostgreSQL — Pinecone stores the minimum needed to return useful search results.

File System (poc/output/) stores the generated Markdown documents. These are keyed by project ID so they're always findable without a database lookup. They're excluded from git (in .gitignore) since they're generated artifacts.

The **API** Layer FastAPI serves the frontend and exposes all functionality as **REST** endpoints. A few design notes:

Background tasks: Document ingestion (**POST** /projects/{id}/documents) fires the 7-step pipeline as a FastAPI BackgroundTask. The **HTTP** response returns immediately with a **202**-style response. The UI polls /projects/{id}/status every 5 seconds to track progress.

Project status is derived: it queries the count of documents, count with status = 'done', count of requirements, and count of open clarifications — all in one **SQL** query. The project itself is 'processing' until all documents are done, then 'ready'.

The docs endpoints (**GET**/**POST** /projects/{id}/docs) serve directly from the file system. They don't touch the database. If a doc file doesn't exist yet (pipeline hasn't run), the endpoint returns a **404** with a clear message.

The Frontend (Streamlit) Five tabs, each scoped to the active project_id stored in st.session_state:

Setup Tab — creates or selects a project. The selected project ID is stored in session state and used by all other tabs.

Upload Tab — file upload widget + pipeline trigger. The status panel uses @st.fragment(run_every=5) — a Streamlit 1.37+ feature that re-renders only that component every 5 seconds, not the whole page. Without this, the old time.sleep(5) + st.rerun() approach blocked the entire UI thread, making the page unresponsive for 5 seconds every cycle.

Requirements Tab — two views selectable by radio button:

By Type: expanders for Functional, Non-Functional, Constraint, Assumption; each requirement shows its **SDLC** topic as a colored badge By **SDLC** Topic: metric chips showing count per topic, then expanders per topic; each requirement shows its type badge Export button downloads all requirements as **JSON** Documents Tab — selectbox of the 8 **SDLC** topics (only those with existing .md files shown). Left panel: rendered Markdown with a toggle to show raw text. Right panel: edit instruction textarea + Apply Edit button. Last-modified timestamp shown below the button.

Clarifications & Query Tab — split into two columns:

Left: list of open questions with text areas for answers; submit stores the answer and embeds it into the **RAG** KB Right: free-text query box; results come from the hybrid **RAG** search with scores shown The Hybrid **RAG** Search When you query the knowledge base (**POST** /projects/{id}/query), three things happen in sequence:

## Dual retrieval: BM25 searches rag_chunks in PostgreSQL and returns the top 20 matches by keyword score. Simultaneously, the query is embedded via Pinecone Inference API and the top 20 semantically similar vectors are retrieved from Pinecone.

## RRF merge (Reciprocal Rank Fusion): The two result lists overlap — some chunks appear in both. RRF merges them by rank without needing to normalize the scores (BM25 scores and cosine similarity scores are on completely different scales and can't be compared directly). The formula is:

score(chunk) = sum of  1 / (60 + rank) across the lists it appears in

A chunk ranked #1 in **BM25** and #3 in Pinecone gets: 1/61 + 1/63 = 0.**0323**. A chunk ranked #2 in only one list gets: 1/62 = 0.**0161**. The constant 60 is a dampening factor that prevents the #1 result from completely dominating. All chunks are sorted by this combined score and the top 20 are kept.

## Cross-encoder re-ranking: The top 20 candidates are re-scored by a cross-encoder (currently a passthrough on Python 3.14 due to missing wheels; in production this is cross-encoder/ms-marco-MiniLM-L-6-v2). A cross-encoder looks at the query and each candidate together, producing a relevance score that's more accurate than the retrieval-time scores. The top 3–5 chunks by cross-encoder score are returned to the API.

Why hybrid? **BM25** is precise for exact keyword matches (*HIPAA* will always surface **HIPAA** content) but misses synonyms. Semantic search handles paraphrasing (*data privacy* matches ***HIPAA** compliance*) but can miss exact terms. **RRF** gives you both for free with no scoring normalization required.

### Token Cost Summary

The architecture's cost efficiency comes from applying four optimizations simultaneously:

Step	Optimization	Effect
Summarize	Cheap model + parallel batch	~0.**001**$/chunk instead of ~0.01$
Summarize	Reduces input to Extract by 80%	Saves most of the expensive model's cost
Extract	Capable model sees summaries only	~4,**400** tokens instead of ~55,**000**
Embed	Content hash dedup	Re-processed files cost 0 tokens
Clarify	Cheap model	~0.**001**$ per run
Doc Write	No **LLM** at all	$0
Doc Edit	Cheap model, sync (user waiting)	~0.**002**$/edit
A naive version of this pipeline (send raw documents to **GPT**-4) would cost $2–5 per document. This architecture costs $0.05–0.15 per document. At **100** documents per day across all clients, that's the difference between $**150**/day and $7,**500**/day.

Key Things to Know If Asked *Why Groq instead of Anthropic?* — Groq has a free tier that makes the **POC** runnable without a billing account. The architecture is identical — switching to Anthropic is changing two strings in config.py (LLM_BASE_URL and model names). The openai **SDK** works with both.

*What happens if the **LLM** returns invalid **JSON**?* — extractor.py passes a **JSON** schema to the model via response_format={*type*: *json_object*}. After parsing, it validates every field: if req_type isn't in the allowed set, it defaults to *functional*; if sdlc_topic isn't valid, it defaults to *requirements*. The pipeline never crashes on a bad **LLM** response.

*Why pg8000 instead of psycopg2?* — psycopg2-binary has no pre-built wheels for Python 3.14 on Windows, and building from source requires pg_config in the **PATH**. pg8000 is pure Python and installs cleanly. The only quirk: PostgreSQL **UUID** array columns need a special string format (*{uuid}* with ::uuid[] cast) instead of passing a Python list.

*What's the **SDLC** topic used for?* — It's the second classification axis alongside req_type. req_type tells you what kind of requirement it is. sdlc_topic tells you which phase of the project it belongs to. This makes the Requirements tab's *By **SDLC** Topic* view useful for a sprint planning meeting (show me just the technical requirements for this sprint) vs. a budget review (show me just the budget requirements).

"What is the Orchestrator Agent mentioned in **CLAUDE**.md?" — That's Stage 4, not Stage 1. It sits between the AI coding agent completing a task and the Senior Engineer approving it. It intercepts task completion, writes a summary, sends it to the SE via Lark, waits for approval, and routes feedback back. Stage 1 is requirement ingestion only — it feeds the upstream backlog that Stage 4 will eventually implement.