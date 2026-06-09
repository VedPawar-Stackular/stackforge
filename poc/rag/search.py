"""
Hybrid retrieval: BM25 keyword search (PostgreSQL) + semantic vector search (Pinecone).

Results from both systems are merged with Reciprocal Rank Fusion (RRF), which
combines ranked lists without needing to normalise heterogeneous scores:
  RRF(d) = sum(1 / (k + rank_i(d)))  for each retrieval system i

If Pinecone is not enabled (PINECONE_API_KEY not set), falls back to BM25 only.
"""

from rank_bm25 import BM25Okapi

from config import BM25_TOP_K, PINECONE_ENABLED, SEMANTIC_TOP_K
from db import DB

_RRF_K = 60  # standard RRF constant; higher = less weight to top ranks


def hybrid_search(project_id: str, query: str) -> list[dict]:
    """
    Run BM25 + Pinecone semantic search, merge via RRF.
    Returns up to BM25_TOP_K candidates ranked by combined relevance.
    """
    with DB() as db:
        all_chunks = db.fetch_all(
            "SELECT id, text, content_type, content_id, metadata "
            "FROM rag_chunks WHERE project_id = %s",
            (project_id,),
        )

    if not all_chunks:
        return []

    bm25_results = _bm25_search(query, all_chunks, top_k=BM25_TOP_K)

    if PINECONE_ENABLED:
        from rag.pinecone_client import semantic_search
        pinecone_results = semantic_search(project_id, query, top_k=SEMANTIC_TOP_K)
        return _rrf_merge(bm25_results, pinecone_results, top_k=BM25_TOP_K)

    return bm25_results


def _bm25_search(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    tokenized_corpus = [c["text"].lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(query.lower().split())
    scored = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def _rrf_merge(
    bm25_results: list[dict],
    pinecone_results: list[dict],
    top_k: int,
) -> list[dict]:
    """
    Merge two ranked result lists with Reciprocal Rank Fusion.
    Chunks only in BM25 are still included (Pinecone may lag if index is fresh).
    Deduplication is by chunk id.
    """
    # Build a lookup of all chunks by id (BM25 results are source of truth for text)
    chunk_by_id: dict[str, dict] = {str(c["id"]): c for c in bm25_results}

    # Add Pinecone-only results (have same fields via stored metadata)
    for c in pinecone_results:
        if c["id"] not in chunk_by_id:
            chunk_by_id[c["id"]] = c

    rrf_scores: dict[str, float] = {}

    for rank, chunk in enumerate(bm25_results):
        cid = str(chunk["id"])
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank + 1)

    for rank, chunk in enumerate(pinecone_results):
        cid = chunk["id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank + 1)

    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return [chunk_by_id[cid] for cid, _ in ranked[:top_k] if cid in chunk_by_id]
