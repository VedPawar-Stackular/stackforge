"""
Pipeline runner: orchestrates all 6 steps for a project.

Steps:
  1. Parse each uploaded document → plain text
  2. Chunk text → ~275-word chunks
  3. Summarize chunks in parallel (cheap model)
  4. Extract structured requirements from all summaries (capable model)
  5. Embed chunk summaries + requirements → rag_chunks
  6. Generate clarification questions (cheap model) → clarifications table
"""

import hashlib
import logging
import os
import uuid

from rank_bm25 import BM25Okapi

from db import DB
from pipeline.chunker import chunk
from pipeline.clarifier import generate_clarifications
from pipeline.doc_writer import write_sdlc_docs
from pipeline.embedder import embed_chunk_summaries, embed_requirements
from pipeline.extractor import extract_requirements
from pipeline.parser import parse
from pipeline.summarizer import summarize_all
from pipeline.utils import get_project_name, text_array_literal

_logger = logging.getLogger(__name__)


async def run_pipeline_for_project(project_id: str, doc_paths: list[str]) -> None:
    """
    Run the full ingestion pipeline for a project given file paths on disk.
    Used by the seed script (--run-pipeline flag).
    """
    with DB() as db:
        client_id = _get_client_id(db, project_id)
        db.execute(
            "UPDATE projects SET status = 'processing' WHERE id = %s",
            (project_id,),
        )

    for path in doc_paths:
        filename = os.path.basename(path)
        ext = filename.rsplit(".", 1)[-1].lower()
        with open(path, "rb") as f:
            file_bytes = f.read()
        await ingest_document(project_id, client_id, file_bytes, filename, ext)

    with DB() as db:
        db.execute(
            "UPDATE projects SET status = 'ready' WHERE id = %s",
            (project_id,),
        )


async def ingest_document(
    project_id: str,
    client_id: str,
    file_bytes: bytes,
    filename: str,
    file_type: str,
) -> str:
    """
    Full pipeline for a single document. Returns document ID.
    Called by the FastAPI /documents upload endpoint.
    """
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    doc_id = str(uuid.uuid4())

    # ── Step 1: Check if this exact file was already processed ──────────────
    with DB() as db:
        existing = db.fetch_one(
            "SELECT id, status FROM documents WHERE project_id = %s AND content_hash = %s",
            (project_id, content_hash),
        )
        if existing and existing["status"] == "done":
            return existing["id"]  # skip re-processing unchanged document

        db.execute(
            """
            INSERT INTO documents (id, project_id, filename, file_type, content_hash, status)
            VALUES (%s, %s, %s, %s, %s, 'processing')
            ON CONFLICT DO NOTHING
            """,
            (doc_id, project_id, filename, file_type, content_hash),
        )

    try:
        # ── Step 1: Parse ────────────────────────────────────────────────────
        text = parse(file_bytes, file_type)

        # ── Step 2: Chunk ────────────────────────────────────────────────────
        chunks = chunk(text)

        # ── Step 3: Summarize (parallel cheap model calls) ───────────────────
        summaries = await summarize_all(chunks, doc_name=filename)

        # ── Store chunks + summaries in DB ───────────────────────────────────
        chunk_rows = []
        with DB() as db:
            for i, (raw, summary) in enumerate(zip(chunks, summaries)):
                chunk_id = str(uuid.uuid4())
                db.execute(
                    """
                    INSERT INTO doc_chunks (id, document_id, chunk_index, raw_text, summary)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (chunk_id, doc_id, i, raw, summary),
                )
                chunk_rows.append({
                    "id": chunk_id,
                    "document_id": doc_id,
                    "chunk_index": i,
                    "raw_text": raw,
                    "summary": summary,
                })

        # ── Step 4: Extract requirements from all summaries ──────────────────
        reqs = await extract_requirements(summaries, [doc_id])

        req_rows = []
        with DB() as db:
            for r in reqs:
                req_id = str(uuid.uuid4())
                # Pass UUID array as a PostgreSQL literal string — pg8000
                # doesn't auto-cast Python lists to UUID[] columns.
                db.execute(
                    """
                    INSERT INTO requirements
                        (id, project_id, req_type, sdlc_topic, title, description,
                         source_document_ids, confidence, key_specifics)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::uuid[], %s, %s::text[])
                    """,
                    (
                        req_id,
                        project_id,
                        r["req_type"],
                        r.get("sdlc_topic", "requirements"),
                        r["title"],
                        r["description"],
                        "{" + doc_id + "}",   # PostgreSQL UUID[] array literal
                        r["confidence"],
                        text_array_literal(r.get("key_specifics", [])),
                    ),
                )
                req_rows.append({**r, "id": req_id})

        # ── Step 5: Embed chunk summaries + requirements ──────────────────────
        with DB() as db:
            embed_chunk_summaries(db, project_id, chunk_rows)
            embed_requirements(db, project_id, req_rows)

        # ── Step 6: Generate clarification questions ──────────────────────────
        all_reqs = _fetch_all_requirements(project_id)
        clarifications = await generate_clarifications(all_reqs)

        with DB() as db:
            # Clear stale open clarifications before inserting fresh set
            db.execute(
                "DELETE FROM clarifications WHERE project_id = %s AND status = 'open'",
                (project_id,),
            )
            for c in clarifications:
                db.execute(
                    """
                    INSERT INTO clarifications
                        (id, project_id, question, context, priority)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        project_id,
                        c["question"],
                        c.get("context", ""),
                        c.get("priority", "medium"),
                    ),
                )

        # ── Step 7: Write SDLC topic .md docs ────────────────────────────────
        try:
            project_name = get_project_name(project_id)
            write_sdlc_docs(project_id, project_name)
        except Exception as doc_err:
            _logger.warning("doc_writer failed: %s", doc_err)

        # ── Step 7.5: Cross-document requirement dedup ───────────────────────
        # Runs after every upload — idempotent. Marks lower-confidence
        # near-duplicate requirements (Jaccard title similarity >= 0.5) as
        # status='duplicate' so Stage 2 skips them. Merges source_document_ids
        # so the surviving requirement knows all contributing docs.
        _dedup_requirements(project_id)

        # ── Mark document done ────────────────────────────────────────────────
        with DB() as db:
            db.execute(
                "UPDATE documents SET status = 'done' WHERE id = %s",
                (doc_id,),
            )

        return doc_id

    except Exception as e:
        with DB() as db:
            db.execute(
                "UPDATE documents SET status = 'failed', error_message = %s WHERE id = %s",
                (str(e), doc_id),
            )
        raise


def _jaccard(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Jaccard similarity between two token lists (word overlap ratio)."""
    a, b = set(tokens_a), set(tokens_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _dedup_requirements(project_id: str, similarity_threshold: float = 0.5) -> None:
    """
    Mark near-duplicate requirements as status='duplicate' within a project.

    Uses Jaccard similarity on lowercase title tokens. When two requirements
    have similarity >= threshold, the lower-confidence one is marked duplicate
    and its source_document_ids are merged into the survivor.

    Runs after every document upload (idempotent).
    """
    with DB() as db:
        reqs = db.fetch_all(
            """
            SELECT id, title, confidence, source_document_ids
            FROM requirements
            WHERE project_id = %s AND status = 'active'
            ORDER BY confidence DESC
            """,
            (project_id,),
        )

    if len(reqs) < 2:
        return

    for r in reqs:
        r["id"] = str(r["id"])
        r["tokens"] = r["title"].lower().split()
        r["source_document_ids"] = [str(d) for d in (r.get("source_document_ids") or [])]

    marked_duplicate: dict[str, str] = {}  # dup_id → survivor_id
    processed: set[str] = set()

    for i, req_a in enumerate(reqs):
        if req_a["id"] in processed:
            continue
        for req_b in reqs[i + 1:]:
            if req_b["id"] in processed:
                continue
            score = _jaccard(req_a["tokens"], req_b["tokens"])
            if score >= similarity_threshold:
                # req_a has higher/equal confidence (sorted DESC above)
                marked_duplicate[req_b["id"]] = req_a["id"]
                processed.add(req_b["id"])

    if not marked_duplicate:
        return

    _logger.info(
        "Deduped %d requirement(s) in project %s (kept %d active)",
        len(marked_duplicate),
        project_id,
        len(reqs) - len(marked_duplicate),
    )

    req_by_id = {r["id"]: r for r in reqs}
    with DB() as db:
        for dup_id, survivor_id in marked_duplicate.items():
            dup = req_by_id.get(dup_id)
            if dup and dup["source_document_ids"]:
                doc_ids_literal = "{" + ",".join(dup["source_document_ids"]) + "}"
                db.execute(
                    """
                    UPDATE requirements
                    SET source_document_ids = source_document_ids || %s::uuid[]
                    WHERE id = %s
                    """,
                    (doc_ids_literal, survivor_id),
                )
            db.execute(
                "UPDATE requirements SET status = 'duplicate' WHERE id = %s",
                (dup_id,),
            )


def _fetch_all_requirements(project_id: str) -> list[dict]:
    with DB() as db:
        return db.fetch_all(
            "SELECT req_type, title, description, confidence FROM requirements WHERE project_id = %s AND status = 'active'",
            (project_id,),
        )


def _get_client_id(db: DB, project_id: str) -> str:
    row = db.fetch_one("SELECT client_id FROM projects WHERE id = %s", (project_id,))
    if not row:
        raise ValueError(f"Project not found: {project_id}")
    return str(row["client_id"])
