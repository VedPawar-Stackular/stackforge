"""Routes: clarification questions and answers."""

import logging

from fastapi import APIRouter, HTTPException, Query

from api.models import AnswerRequest, ClarificationResponse, QueryRequest, RagChunkResponse
from api.routes import validate_project_id
from db import DB
from pipeline.embedder import embed_clarification
from rag.reranker import rerank
from rag.search import hybrid_search

router = APIRouter(prefix="/projects/{project_id}", tags=["clarifications"])
_logger = logging.getLogger(__name__)


@router.get("/clarifications", response_model=list[ClarificationResponse])
def list_clarifications(
    project_id: str,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List clarification questions, optionally filtered by status (open|answered)."""
    validate_project_id(project_id)
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

        if status:
            rows = db.fetch_all(
                "SELECT * FROM clarifications WHERE project_id = %s AND status = %s ORDER BY priority DESC, created_at LIMIT %s OFFSET %s",
                (project_id, status, limit, offset),
            )
        else:
            rows = db.fetch_all(
                "SELECT * FROM clarifications WHERE project_id = %s ORDER BY priority DESC, created_at LIMIT %s OFFSET %s",
                (project_id, limit, offset),
            )
    return rows


@router.post(
    "/clarifications/{clarification_id}/answer",
    response_model=ClarificationResponse,
)
def answer_clarification(project_id: str, clarification_id: str, body: AnswerRequest):
    """Submit an answer to a clarification question. Embeds the Q&A into RAG."""
    validate_project_id(project_id)
    with DB() as db:
        row = db.fetch_one(
            "SELECT * FROM clarifications WHERE id = %s AND project_id = %s",
            (clarification_id, project_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Clarification not found")

        db.execute(
            "UPDATE clarifications SET answer = %s, status = 'answered' WHERE id = %s",
            (body.answer, clarification_id),
        )
        updated = db.fetch_one(
            "SELECT * FROM clarifications WHERE id = %s", (clarification_id,)
        )

    # Outside the answer transaction — a RAG failure must not roll back the answer
    try:
        with DB() as db2:
            embed_clarification(db2, project_id, updated)
    except Exception:
        _logger.warning("RAG embed failed for clarification %s", clarification_id, exc_info=True)

    return updated


@router.post("/query", response_model=list[RagChunkResponse], tags=["rag"])
def query_rag(project_id: str, body: QueryRequest):
    """
    Hybrid RAG search: BM25 + semantic → cross-encoder re-rank → top 3-5 chunks.
    Returns the most relevant chunks for a natural language query.
    """
    validate_project_id(project_id)
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

    candidates = hybrid_search(project_id, body.query)
    if not candidates:
        return []

    top_chunks = rerank(body.query, candidates)
    return [
        {
            "content_type": c["content_type"],
            "text": c["text"],
            "metadata": c["metadata"] if isinstance(c["metadata"], dict) else {},
            "score": c.get("_score", 0.0),
        }
        for c in top_chunks
    ]
