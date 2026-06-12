"""Routes: project and client management."""

import os
import shutil
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.models import CreateProjectRequest, ProjectResponse, ProjectStatusResponse
from api.routes import validate_project_id
from db import DB

router = APIRouter(prefix="/projects", tags=["projects"])
_logger = logging.getLogger(__name__)


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


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str):
    """
    Permanently delete a project and ALL associated data:
    documents, chunks, requirements, clarifications, epics, user stories,
    stage2 metrics, rag_chunks, and the on-disk output directory.

    The DB cascade handles most child tables. rag_chunks has no FK constraint
    so it must be deleted explicitly before the project row is removed.
    """
    validate_project_id(project_id)
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

        # rag_chunks has no FK → projects, must be deleted manually
        db.execute("DELETE FROM rag_chunks WHERE project_id = %s", (project_id,))

        # Deleting the project row cascades to:
        #   documents → doc_chunks
        #   requirements, clarifications
        #   epics → user_stories
        #   stage2_metrics
        db.execute("DELETE FROM projects WHERE id = %s", (project_id,))

    # Remove on-disk output (SDLC docs, Stitch artefacts, etc.)
    try:
        from pipeline.doc_writer import get_output_dir
        output_dir = get_output_dir(project_id)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
    except Exception as e:
        _logger.warning("Output dir cleanup failed for project %s: %s", project_id, e)

    return Response(status_code=204)


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
        failed_count = db.fetch_one(
            "SELECT COUNT(*) AS n FROM documents WHERE project_id = %s AND status = 'failed'",
            (project_id,),
        )["n"]
        processing_count = db.fetch_one(
            "SELECT COUNT(*) AS n FROM documents WHERE project_id = %s AND status = 'processing'",
            (project_id,),
        )["n"]
        req_count = db.fetch_one(
            "SELECT COUNT(*) AS n FROM requirements WHERE project_id = %s", (project_id,)
        )["n"]
        clarification_count = db.fetch_one(
            "SELECT COUNT(*) AS n FROM clarifications WHERE project_id = %s AND status = 'open'",
            (project_id,),
        )["n"]

    # Compute status from live document states — avoids the race condition where
    # multiple background tasks overwrite projects.status unpredictably.
    if doc_count == 0:
        computed_status = project["status"]  # no docs uploaded yet — trust project table
    elif processing_count > 0:
        computed_status = "processing"
    elif ready_count == doc_count:
        computed_status = "ready"
    elif ready_count > 0:
        computed_status = "partial"  # some succeeded, some failed
    else:
        computed_status = "failed"   # all failed

    return {
        "project_id": project_id,
        "status": computed_status,
        "document_count": doc_count,
        "ready_count": ready_count,
        "failed_count": failed_count,
        "requirement_count": req_count,
        "clarification_count": clarification_count,
    }
