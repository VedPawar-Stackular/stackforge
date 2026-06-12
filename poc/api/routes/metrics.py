"""Routes: Stage 1 — token-cost metrics for the ingestion pipeline.

Stage 2 metrics live on the epics router (/stage2-metrics). This router exposes the
parallel Stage 1 report so the UI and any client can show ingestion token economics.
"""

from fastapi import APIRouter, HTTPException

from api.models import PipelineMetricsResponse
from api.routes import validate_project_id
from db import DB
from pipeline.stage1_metrics_calculator import get_report

router = APIRouter(prefix="/projects/{project_id}", tags=["metrics"])


@router.get("/stage1-metrics", response_model=PipelineMetricsResponse)
def get_stage1_metrics(project_id: str):
    """Return the token cost savings report for Stage 1 (summarize / extract / clarify)."""
    validate_project_id(project_id)
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

    return get_report(project_id)
