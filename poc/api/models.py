"""Pydantic request/response models for the FastAPI layer."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# ─── Projects / Clients ──────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    client_name: str
    project_name: str


class ProjectResponse(BaseModel):
    id: UUID
    client_id: UUID
    name: str
    status: str
    created_at: datetime


class ProjectStatusResponse(BaseModel):
    project_id: UUID
    status: str
    document_count: int
    ready_count: int
    requirement_count: int
    clarification_count: int


# ─── Documents ───────────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    status: str
    uploaded_at: datetime


# ─── Requirements ────────────────────────────────────────────────────────────

class RequirementResponse(BaseModel):
    id: UUID
    req_type: str
    sdlc_topic: Optional[str] = "requirements"
    title: str
    description: str
    confidence: float
    created_at: datetime


# ─── Clarifications ──────────────────────────────────────────────────────────

class ClarificationResponse(BaseModel):
    id: UUID
    question: str
    context: Optional[str]
    priority: str
    answer: Optional[str]
    status: str
    created_at: datetime


class AnswerRequest(BaseModel):
    answer: str


# ─── RAG Query ───────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str


class RagChunkResponse(BaseModel):
    content_type: str
    text: str
    metadata: dict
    score: float


# ─── SDLC Docs ───────────────────────────────────────────────────────────────

class DocMetaResponse(BaseModel):
    topic: str
    filename: str
    exists: bool
    size_bytes: int
    last_modified: Optional[datetime]


class DocContentResponse(BaseModel):
    topic: str
    content: str
    last_modified: Optional[datetime]


class DocEditRequest(BaseModel):
    instruction: str


class DocEditResponse(BaseModel):
    topic: str
    content: str


# ─── Google Stitch ────────────────────────────────────────────────────────────

class StitchGenerateResponse(BaseModel):
    status: str  # "generating"


class StitchScreen(BaseModel):
    name: str
    label: str
    html_path: Optional[str]


class StitchStatusResponse(BaseModel):
    status: str  # "not_generated" | "generating" | "ready" | "error"
    stitch_url: Optional[str]
    screens: list[StitchScreen]
    generated_at: Optional[datetime]
    error: Optional[str]
