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
    failed_count: int = 0
    requirement_count: int
    clarification_count: int


# ─── Documents ───────────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    status: str
    uploaded_at: datetime
    error_message: Optional[str] = None


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


# ─── Stage 2: Epics & User Stories ───────────────────────────────────────────

class EpicResponse(BaseModel):
    id: UUID
    title: str
    description: str
    theme: str
    story_count: int
    ado_work_item_id: Optional[int]
    ado_work_item_url: Optional[str]
    created_at: datetime


class StoryResponse(BaseModel):
    id: UUID
    epic_id: UUID
    title: str
    description: str
    acceptance_criteria: list[str]
    story_points: Optional[int]
    assignee: Optional[str]
    ado_work_item_id: Optional[int]
    ado_work_item_url: Optional[str]
    status: str
    created_at: datetime


class Stage2StatusResponse(BaseModel):
    status: str           # idle | generating | ready | failed
    epic_count: int
    story_count: int
    ado_pushed: bool


class MetricsStep(BaseModel):
    step: str
    model: str
    tier: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    why_this_model: str


class Stage2MetricsResponse(BaseModel):
    actual_cost_usd: float
    naive_cost_usd: float
    savings_pct: float
    tokens_saved: int
    actual_input_tokens: int
    actual_output_tokens: int
    naive_input_tokens: int
    naive_output_tokens: int
    steps: list[MetricsStep]


class AdoPushResponse(BaseModel):
    epics_pushed: int
    stories_pushed: int
    errors: list[str]


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
