"""Routes: project and client management."""

import uuid

from fastapi import APIRouter, HTTPException

from api.models import CreateProjectRequest, ProjectResponse, ProjectStatusResponse
from db import DB

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: CreateProjectRequest):
    """Create a client (if new) and a project under it."""
    with DB() as db:
        # Upsert client by name
        row = db.fetch_one(
            "SELECT id FROM clients WHERE name = %s", (body.client_name,)
        )
        if row:
            client_id = str(row["id"])
        else:
            client_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO clients (id, name) VALUES (%s, %s)",
                (client_id, body.client_name),
            )

        project_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO projects (id, client_id, name, status) VALUES (%s, %s, %s, 'pending')",
            (project_id, client_id, body.project_name),
        )
        project = db.fetch_one("SELECT * FROM projects WHERE id = %s", (project_id,))

    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects():
    with DB() as db:
        return db.fetch_all("SELECT * FROM projects ORDER BY created_at DESC")


@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
def get_project_status(project_id: str):
    with DB() as db:
        project = db.fetch_one("SELECT status FROM projects WHERE id = %s", (project_id,))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        doc_count = db.fetch_one(
            "SELECT COUNT(*) AS n FROM documents WHERE project_id = %s", (project_id,)
        )["n"]
        ready_count = db.fetch_one(
            "SELECT COUNT(*) AS n FROM documents WHERE project_id = %s AND status = 'done'",
            (project_id,),
        )["n"]
        req_count = db.fetch_one(
            "SELECT COUNT(*) AS n FROM requirements WHERE project_id = %s", (project_id,)
        )["n"]
        clarification_count = db.fetch_one(
            "SELECT COUNT(*) AS n FROM clarifications WHERE project_id = %s AND status = 'open'",
            (project_id,),
        )["n"]

    return {
        "project_id": project_id,
        "status": project["status"],
        "document_count": doc_count,
        "ready_count": ready_count,
        "requirement_count": req_count,
        "clarification_count": clarification_count,
    }
