"""Pydantic request/response models for the FastAPI layer."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Projects / Clients ──────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    client_name: str = Field(..., min_length=1, max_length=200)
    project_name: str = Field(..., min_length=1, max_length=200)


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
    answer: str = Field(..., min_length=1, max_length=10_000)


# ─── RAG Query ───────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2_000)


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
    instruction: str = Field(..., min_length=1, max_length=5_000)


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
    thinking_tokens: int = 0
    cost_usd: float
    # Same tokens repriced at Opus rates — the per-step model-choice cost delta.
    opus_equivalent_cost_usd: float = 0.0
    opus_multiplier: float = 0.0
    duration_ms: int
    why_this_model: str


class PipelineMetricsResponse(BaseModel):
    actual_cost_usd: float
    naive_cost_usd: float
    savings_pct: float
    tokens_saved: int
    actual_input_tokens: int
    actual_output_tokens: int
    actual_thinking_tokens: int = 0
    naive_input_tokens: int
    naive_output_tokens: int
    steps: list[MetricsStep]


# Backwards-compatible aliases — both stages share the same report shape.
Stage1MetricsResponse = PipelineMetricsResponse
Stage2MetricsResponse = PipelineMetricsResponse


class GenerationStartedResponse(BaseModel):
    status: str
    message: str


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
