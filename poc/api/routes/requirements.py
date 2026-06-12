"""Routes: list and query structured requirements."""

from fastapi import APIRouter, HTTPException, Query

from api.models import RequirementResponse
from api.routes import validate_project_id
from db import DB

router = APIRouter(prefix="/projects/{project_id}/requirements", tags=["requirements"])


@router.get("", response_model=list[RequirementResponse])
def list_requirements(
    project_id: str,
    req_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List requirements for a project, optionally filtered by req_type."""
    validate_project_id(project_id)
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

        if req_type:
            rows = db.fetch_all(
                "SELECT * FROM requirements WHERE project_id = %s AND req_type = %s ORDER BY created_at LIMIT %s OFFSET %s",
                (project_id, req_type, limit, offset),
            )
        else:
            rows = db.fetch_all(
                "SELECT * FROM requirements WHERE project_id = %s ORDER BY req_type, created_at LIMIT %s OFFSET %s",
                (project_id, limit, offset),
            )
    return rows
