"""
Embedder: stores text in both PostgreSQL rag_chunks (BM25) and Pinecone (semantic).

PostgreSQL provides keyword search via BM25. Pinecone provides semantic vector
search via multilingual-e5-large embeddings. Both are queried in parallel during
retrieval and merged with Reciprocal Rank Fusion.

If PINECONE_ENABLED is False (key not set), Pinecone calls are silently skipped
and the system falls back to BM25-only retrieval.
"""

import hashlib
import json
import uuid

from config import PINECONE_ENABLED
from db import DB


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def upsert_rag_chunk(
    db: DB,
    project_id: str,
    content_type: str,
    content_id: str,
    text: str,
    metadata: dict,
) -> str | None:
    """
    Store a RAG chunk in PostgreSQL for BM25 retrieval.
    Returns the chunk UUID (new or existing), or None if content was empty.
    Skips insert if identical content_hash already exists.
    """
    if not text or not text.strip():
        return None

    h = _hash(text)
    existing = db.fetch_one(
        "SELECT id FROM rag_chunks WHERE project_id = %s AND content_hash = %s",
        (project_id, h),
    )
    if existing:
        return str(existing["id"])

    chunk_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO rag_chunks
            (id, project_id, content_type, content_id, text, metadata, content_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (chunk_id, project_id, content_type, content_id, text, json.dumps(metadata), h),
    )
    return chunk_id


def _upsert_with_vector(
    db: DB,
    project_id: str,
    content_type: str,
    content_id: str,
    text: str,
    metadata: dict,
) -> None:
    """
    Store chunk in PostgreSQL AND push vector to Pinecone.
    Pinecone stores content_type so search results are self-contained.
    """
    chunk_id = upsert_rag_chunk(db, project_id, content_type, content_id, text, metadata)
    if chunk_id and PINECONE_ENABLED:
        from rag.pinecone_client import upsert_chunk
        upsert_chunk(
            chunk_id=chunk_id,
            text=text,
            project_id=project_id,
            metadata={"content_type": content_type, "content_id": content_id, **metadata},
        )


def embed_chunk_summaries(db: DB, project_id: str, chunk_rows: list[dict]) -> None:
    for row in chunk_rows:
        if not row.get("summary"):
            continue
        _upsert_with_vector(
            db,
            project_id=project_id,
            content_type="chunk_summary",
            content_id=str(row["id"]),
            text=row["summary"],
            metadata={
                "doc_type": "chunk_summary",
                "document_id": str(row["document_id"]),
                "chunk_index": str(row["chunk_index"]),
            },
        )


def embed_requirements(db: DB, project_id: str, req_rows: list[dict]) -> None:
    for row in req_rows:
        text = f"{row['title']}: {row['description']}"
        _upsert_with_vector(
            db,
            project_id=project_id,
            content_type="requirement",
            content_id=str(row["id"]),
            text=text,
            metadata={
                "doc_type": "requirement",
                "req_type": row.get("req_type", "functional"),
                "sdlc_topic": row.get("sdlc_topic", "requirements"),
                "confidence": str(row.get("confidence", 0.8)),
            },
        )


def embed_clarification(db: DB, project_id: str, clarification_row: dict) -> None:
    if not clarification_row.get("answer"):
        return
    text = (
        f"Q: {clarification_row['question']}\n"
        f"A: {clarification_row['answer']}"
    )
    _upsert_with_vector(
        db,
        project_id=project_id,
        content_type="clarification",
        content_id=str(clarification_row["id"]),
        text=text,
        metadata={
            "doc_type": "clarification",
            "priority": clarification_row.get("priority", "medium"),
        },
    )
