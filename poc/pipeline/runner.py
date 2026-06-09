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

import uuid

from db import DB
from pipeline.chunker import chunk
from pipeline.clarifier import generate_clarifications
from pipeline.embedder import embed_chunk_summaries, embed_requirements
from pipeline.extractor import extract_requirements
from pipeline.summarizer import summarize_all


async def run_pipeline_for_project(project_id: str, doc_paths: list[str]) -> None:
    """
    Run the full ingestion pipeline for a project given file paths on disk.
    Used by the seed script (--run-pipeline flag).
    """
    import os

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
    import hashlib

    from pipeline.parser import parse

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
        summaries = await summarize_all(chunks)

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
                         source_document_ids, confidence)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::uuid[], %s)
                    """,
                    (
                        req_id,
                        project_id,
                        r["req_type"],
                        r.get("sdlc_topic", "requirements"),
                        r["title"],
                        r["description"],
                        "{" + doc_id + "}",   # PostgreSQL array literal
                        r["confidence"],
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
            from pipeline.doc_writer import write_sdlc_docs
            project_name = _get_project_name(project_id)
            write_sdlc_docs(project_id, project_name)
        except Exception as doc_err:
            # Doc generation failing must not block the pipeline completing
            import logging
            logging.getLogger(__name__).warning("doc_writer failed: %s", doc_err)

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


def _fetch_all_requirements(project_id: str) -> list[dict]:
    with DB() as db:
        return db.fetch_all(
            "SELECT req_type, title, description, confidence FROM requirements WHERE project_id = %s",
            (project_id,),
        )


def _get_client_id(db: DB, project_id: str) -> str:
    row = db.fetch_one("SELECT client_id FROM projects WHERE id = %s", (project_id,))
    if not row:
        raise ValueError(f"Project not found: {project_id}")
    return str(row["client_id"])


def _get_project_name(project_id: str) -> str:
    with DB() as db:
        row = db.fetch_one("SELECT name FROM projects WHERE id = %s", (project_id,))
    return row["name"] if row else project_id
