"""FastAPI application entry point."""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from api.routes import clarifications, documents, docs, epics, metrics, projects, requirements, stitch

_logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_API_KEY = os.environ.get("API_KEY", "")


def _require_api_key(key: str | None = Security(_api_key_header)) -> None:
    if _API_KEY and key != _API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


app = FastAPI(
    title="StackForge POC — Stages 1 & 2: Requirement Ingestion + Epic Generation",
    description=(
        "Ingests client documents (SOW, transcripts), extracts structured requirements, "
        "generates clarification questions, and provides hybrid RAG search."
    ),
    version="0.1.0",
)

_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:8501").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
    allow_credentials=False,
)

_auth = [Depends(_require_api_key)]

app.include_router(projects.router, dependencies=_auth)
app.include_router(documents.router, dependencies=_auth)
app.include_router(requirements.router, dependencies=_auth)
app.include_router(clarifications.router, dependencies=_auth)
app.include_router(docs.router, dependencies=_auth)
app.include_router(stitch.router, dependencies=_auth)
app.include_router(epics.router, dependencies=_auth)
app.include_router(metrics.router, dependencies=_auth)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok"}


@app.on_event("startup")
def _startup_checks() -> None:
    if not _API_KEY:
        _logger.warning(
            "API_KEY is not set — all endpoints are unauthenticated. "
            "Set API_KEY in poc/.env before deploying."
        )
