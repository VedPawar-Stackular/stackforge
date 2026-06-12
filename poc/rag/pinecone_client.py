"""
Pinecone vector search client.

Handles:
  - Index creation (once, on first use)
  - Embedding via Pinecone Inference API (multilingual-e5-large, 1024-dim)
  - Upsert of chunk vectors with metadata
  - Semantic search with project_id metadata filter

Falls back gracefully if PINECONE_ENABLED is False (key not set).
"""

import logging
import threading
import time

from config import (
    PINECONE_API_KEY,
    PINECONE_CLOUD,
    PINECONE_DIMENSION,
    PINECONE_EMBED_MODEL,
    PINECONE_ENABLED,
    PINECONE_INDEX_NAME,
    PINECONE_REGION,
    SEMANTIC_TOP_K,
)

logger = logging.getLogger(__name__)

_pc = None
_index = None
_lock = threading.Lock()


def _get_client():
    global _pc
    with _lock:
        if _pc is None:
            from pinecone import Pinecone
            _pc = Pinecone(api_key=PINECONE_API_KEY)
    return _pc


def get_index():
    """Return the Pinecone index, creating it if it doesn't exist yet."""
    global _index
    with _lock:
        if _index is not None:
            return _index

        from pinecone import ServerlessSpec

        pc = _get_client()
        existing = {idx.name for idx in pc.list_indexes()}

        if PINECONE_INDEX_NAME not in existing:
            logger.info("Creating Pinecone index '%s'...", PINECONE_INDEX_NAME)
            pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=PINECONE_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
            )
            # Wait until index is ready (creation is async on Pinecone side)
            for _ in range(30):
                status = pc.describe_index(PINECONE_INDEX_NAME).status
                if status.get("ready"):
                    break
                time.sleep(2)

        _index = pc.Index(PINECONE_INDEX_NAME)
        return _index


def embed_texts(texts: list[str], input_type: str = "passage") -> list[list[float]]:
    """
    Embed a list of texts using Pinecone Inference API.
    input_type: "passage" for indexing, "query" for search.
    Returns list of float vectors.
    """
    pc = _get_client()
    result = pc.inference.embed(
        model=PINECONE_EMBED_MODEL,
        inputs=texts,
        parameters={"input_type": input_type, "truncate": "END"},
    )
    return [item.values for item in result.data]


def upsert_chunk(chunk_id: str, text: str, project_id: str, metadata: dict) -> None:
    """
    Upsert a single chunk vector to Pinecone.
    Stores text + project_id in metadata for retrieval and filtering.
    """
    if not PINECONE_ENABLED:
        return
    try:
        index = get_index()
        vectors = embed_texts([text], input_type="passage")
        pinecone_metadata = {
            "project_id": project_id,
            "text": text[:2000],  # Pinecone metadata cap; summaries fit comfortably
            **{k: str(v) for k, v in metadata.items() if v is not None},
        }
        index.upsert(vectors=[{"id": chunk_id, "values": vectors[0], "metadata": pinecone_metadata}])
    except Exception as e:
        # Non-fatal: BM25 search still works if Pinecone upsert fails
        logger.warning("Pinecone upsert failed for chunk %s: %s", chunk_id, e)


def semantic_search(project_id: str, query: str, top_k: int = SEMANTIC_TOP_K) -> list[dict]:
    """
    Query Pinecone for the top_k most semantically similar chunks
    filtered to the given project.
    Returns dicts compatible with BM25 result format.
    """
    if not PINECONE_ENABLED:
        return []
    try:
        index = get_index()
        query_vectors = embed_texts([query], input_type="query")
        results = index.query(
            vector=query_vectors[0],
            top_k=top_k,
            filter={"project_id": {"$eq": project_id}},
            include_metadata=True,
        )
        return [
            {
                "id": match.id,
                "text": match.metadata.get("text", ""),
                "content_type": match.metadata.get("content_type", ""),
                "content_id": match.metadata.get("content_id", ""),
                "metadata": {
                    k: v
                    for k, v in match.metadata.items()
                    if k not in ("project_id", "text", "content_type", "content_id")
                },
                "_pinecone_score": match.score,
            }
            for match in results.matches
        ]
    except Exception as e:
        logger.warning("Pinecone search failed: %s", e)
        return []
