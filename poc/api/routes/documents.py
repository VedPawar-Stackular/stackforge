"""Routes: document upload and pipeline trigger."""

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from api.models import DocumentResponse
from db import DB
from pipeline.runner import ingest_document

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])

ALLOWED_TYPES = {"pdf", "docx", "txt"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


@router.post("", response_model=DocumentResponse, status_code=202)
async def upload_document(
    project_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
):
    """
    Upload a document and trigger the ingestion pipeline in the background.
    Returns immediately with status='processing'. Poll /status to track progress.
    """
    with DB() as db:
        project = db.fetch_one("SELECT id, client_id FROM projects WHERE id = %s", (project_id,))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    if ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Allowed: {', '.join(ALLOWED_TYPES)}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    client_id = str(project["client_id"])

    # Kick off the pipeline in the background so the response is instant
    background_tasks.add_task(
        _run_pipeline_and_update_project,
        project_id,
        client_id,
        file_bytes,
        filename,
        ext,
    )

    # Return a minimal document stub — actual document row is created inside the pipeline
    import hashlib, uuid, datetime
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    return {
        "id": uuid.uuid4(),
        "filename": filename,
        "file_type": ext,
        "status": "processing",
        "uploaded_at": datetime.datetime.utcnow(),
    }


@router.get("", response_model=list[DocumentResponse])
def list_documents(project_id: str):
    with DB() as db:
        return db.fetch_all(
            "SELECT * FROM documents WHERE project_id = %s ORDER BY uploaded_at DESC",
            (project_id,),
        )


async def _run_pipeline_and_update_project(
    project_id: str,
    client_id: str,
    file_bytes: bytes,
    filename: str,
    file_type: str,
) -> None:
    """Background task: run pipeline, then update project status."""
    try:
        with DB() as db:
            db.execute(
                "UPDATE projects SET status = 'processing' WHERE id = %s",
                (project_id,),
            )

        await ingest_document(project_id, client_id, file_bytes, filename, file_type)

        # Update project status based on live document states.
        # Count only 'processing' as still-in-flight — failed docs must not
        # keep the project stuck in "processing" indefinitely.
        with DB() as db:
            done_count = db.fetch_one(
                "SELECT COUNT(*) AS n FROM documents WHERE project_id = %s AND status = 'done'",
                (project_id,),
            )["n"]
            processing_count = db.fetch_one(
                "SELECT COUNT(*) AS n FROM documents WHERE project_id = %s AND status = 'processing'",
                (project_id,),
            )["n"]
            total_count = db.fetch_one(
                "SELECT COUNT(*) AS n FROM documents WHERE project_id = %s",
                (project_id,),
            )["n"]

            if processing_count > 0:
                new_status = "processing"
            elif done_count == total_count:
                new_status = "ready"
            else:
                new_status = "failed"

            db.execute(
                "UPDATE projects SET status = %s WHERE id = %s",
                (new_status, project_id),
            )
    except Exception as e:
        with DB() as db:
            db.execute(
                "UPDATE projects SET status = 'failed' WHERE id = %s",
                (project_id,),
            )
