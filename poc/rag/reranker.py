"""
Reranker: returns the top RERANK_TOP_K BM25 candidates.

Cross-encoder reranking is disabled pending Python 3.14 compatible libraries.
For a POC the top BM25 hits are sufficient.
"""

from config import RERANK_TOP_K


def rerank(query: str, candidates: list[dict]) -> list[dict]:
    """Return top RERANK_TOP_K candidates. Score is set to rank position (1.0 = best)."""
    top = candidates[:RERANK_TOP_K]
    return [
        {**c, "_score": round(1.0 - i * 0.1, 2)}
        for i, c in enumerate(top)
    ]
