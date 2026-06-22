"""Shared configuration loaded from .env."""

import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]

GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")

# Set LLM_PROVIDER=groq or LLM_PROVIDER=openrouter in .env to switch providers
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "groq")

if LLM_PROVIDER == "openrouter":
    LLM_API_KEY: str = OPENROUTER_API_KEY
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    # Override via .env; defaults map to haiku/sonnet tier equivalents
    MODEL_CHEAP: str = os.environ.get("OPENROUTER_MODEL_CHEAP", "meta-llama/llama-3.1-8b-instruct:free")
    MODEL_CAPABLE: str = os.environ.get("OPENROUTER_MODEL_CAPABLE", "meta-llama/llama-3.3-70b-instruct")
else:  # groq
    LLM_API_KEY = GROQ_API_KEY
    LLM_BASE_URL = "https://api.groq.com/openai/v1"
    MODEL_CHEAP = "llama-3.1-8b-instant"
    MODEL_CAPABLE = "llama-3.3-70b-versatile"

# Chunking
CHUNK_TARGET_WORDS: int = 275  # target ~250-300 words per chunk
CHUNK_OVERLAP_WORDS: int = 35  # tail words from previous chunk prepended to next

# Extraction batching — summaries are sent to the extractor in groups of this
# size to avoid truncating large requirement sets at max_tokens=2048.
EXTRACTOR_BATCH_SIZE: int = 10

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

# ── Stage 2: Azure DevOps ──────────────────────────────────────────────────────
# Set these in poc/.env to enable pushing epics and user stories to ADO.
# ADO_ORG:     your Azure DevOps organization name (e.g. "stackular")
# ADO_PROJECT: the project name inside that org (e.g. "StackForge")
# ADO_PAT:     Personal Access Token with Work Items (Read & Write) scope
ADO_ORG: str = os.environ.get("ADO_ORG", "")
ADO_PROJECT: str = os.environ.get("ADO_PROJECT", "")
ADO_PAT: str = os.environ.get("ADO_PAT", "")
ADO_API_VERSION: str = "7.1"

# Anthropic pricing reference (USD per 1 million tokens).
# Used by the metrics calculator to compare actual vs naive approach cost.
# These rates are used even when running on Groq — the calculator shows what
# the same calls would cost on the production Anthropic API.
PRICING: dict = {
    "haiku":  {"input": 0.25,  "output": 1.25},   # claude-haiku-4-5
    "sonnet": {"input": 3.00,  "output": 15.00},   # claude-sonnet-4-6
    "opus":   {"input": 15.00, "output": 75.00},   # claude-opus-4-8
}

# Map Groq model names → Anthropic pricing tier for cost calculations
MODEL_TIER: dict = {
    MODEL_CHEAP:   "haiku",   # llama-3.1-8b-instant  → haiku tier
    MODEL_CAPABLE: "sonnet",  # llama-3.3-70b-versatile → sonnet tier
}

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
