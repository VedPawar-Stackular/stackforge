"""Shared configuration loaded from .env."""

import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]

GROQ_API_KEY: str = os.environ["GROQ_API_KEY"]
LLM_BASE_URL: str = "https://api.groq.com/openai/v1"

# Model routing — matches production Haiku/Sonnet tier intent
MODEL_CHEAP: str = "llama-3.1-8b-instant"      # summarisation, clarification, routing
MODEL_CAPABLE: str = "llama-3.3-70b-versatile"  # structured requirement extraction

# Chunking
CHUNK_TARGET_WORDS: int = 275  # target ~250-300 words per chunk
CHUNK_OVERLAP_WORDS: int = 35  # tail words from previous chunk prepended to next

# Embedding model (local, 384-dim) — disabled on Python 3.14 (no wheels)
EMBED_MODEL: str = "all-MiniLM-L6-v2"

# Reranker model (local) — disabled on Python 3.14
RERANK_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# RAG retrieval
BM25_TOP_K: int = 20
SEMANTIC_TOP_K: int = 20
RERANK_TOP_K: int = 5

# Pinecone vector search
# Set PINECONE_API_KEY in .env to enable semantic search alongside BM25.
# If not set, system falls back to BM25-only retrieval.
PINECONE_API_KEY: str = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME: str = os.environ.get("PINECONE_INDEX_NAME", "stackforge-poc")
PINECONE_EMBED_MODEL: str = "multilingual-e5-large"  # 1024-dim, available in Pinecone Inference
PINECONE_DIMENSION: int = 1024
PINECONE_CLOUD: str = os.environ.get("PINECONE_CLOUD", "aws")
PINECONE_REGION: str = os.environ.get("PINECONE_REGION", "us-east-1")
PINECONE_ENABLED: bool = bool(PINECONE_API_KEY)

# Google Stitch design generation (optional — required only for Stitch integration)
# Get your key at stitch.withgoogle.com → Settings → API Keys
STITCH_API_KEY: str = os.environ.get("STITCH_API_KEY", "")

# SDLC topic taxonomy used for requirement classification
SDLC_TOPICS: list[str] = [
    "requirements",     # functional requirements, features, user needs, scope
    "design",           # UI/UX, wireframes, brand, components, flows, styling
    "technical",        # architecture, stack, APIs, DB, infra, security
    "timeline",         # phases, milestones, deadlines, dependencies
    "budget",           # costs, payment schedule, resource allocation
    "testing",          # test requirements, UAT, acceptance criteria, coverage
    "integrations",     # third-party services, ERP, payment gateways, external APIs
    "team_and_process", # roles, responsibilities, change management, communication
]
