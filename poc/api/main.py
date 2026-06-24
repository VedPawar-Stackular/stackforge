"""FastAPI application entry point."""

import sys
import os

# Allow imports from poc/ root when running from subdirectory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import clarifications, documents, docs, epics, metrics, projects, requirements, sprints, stitch

app = FastAPI(
    title="StackForge POC — Stages 1–3: Requirement Ingestion, Epic Generation & Sprint Planning",
    description=(
        "Ingests client documents (SOW, transcripts), extracts structured requirements, "
        "generates clarification questions, and provides hybrid RAG search."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # POC only — tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(requirements.router)
app.include_router(clarifications.router)
app.include_router(docs.router)
app.include_router(stitch.router)
app.include_router(epics.router)
app.include_router(sprints.router)
app.include_router(metrics.router)


@app.get("/health")
def health():
    return {"status": "ok"}
