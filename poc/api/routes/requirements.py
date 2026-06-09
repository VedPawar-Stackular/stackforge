"""Routes: list and query structured requirements."""

from fastapi import APIRouter, HTTPException

from api.models import RequirementResponse
from db import DB

router = APIRouter(prefix="/projects/{project_id}/requirements", tags=["requirements"])


@router.get("", response_model=list[RequirementResponse])
def list_requirements(project_id: str, req_type: str | None = None):
    """List all requirements for a project, optionally filtered by req_type."""
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

        if req_type:
            rows = db.fetch_all(
                "SELECT * FROM requirements WHERE project_id = %s AND req_type = %s ORDER BY created_at",
                (project_id, req_type),
            )
        else:
            rows = db.fetch_all(
                "SELECT * FROM requirements WHERE project_id = %s ORDER BY req_type, created_at",
                (project_id,),
            )
    return rows
