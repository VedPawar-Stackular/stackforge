"""Routes: document upload and pipeline trigger."""

import asyncio
import datetime
import hashlib
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from api.models import DocumentResponse
from api.routes import validate_project_id
from db import DB
from pipeline.runner import ingest_document

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])
_logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"pdf", "docx", "txt"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


def _fetch_project(project_id: str) -> dict | None:
    with DB() as db:
        return db.fetch_one("SELECT id, client_id FROM projects WHERE id = %s", (project_id,))


def _create_document_stub(
    project_id: str, filename: str, file_type: str, content_hash: str
) -> str:
    """Insert a processing-status document row and return its ID.

    Uses ON CONFLICT DO NOTHING so re-uploading the same file returns the
    existing row ID rather than creating a duplicate.
    """
    doc_id = str(uuid.uuid4())
    with DB() as db:
        db.execute(
            """
            INSERT INTO documents (id, project_id, filename, file_type, content_hash, status)
            VALUES (%s, %s, %s, %s, %s, 'processing')
            ON CONFLICT DO NOTHING
            """,
            (doc_id, project_id, filename, file_type, content_hash),
        )
        existing = db.fetch_one(
            "SELECT id FROM documents WHERE project_id = %s AND content_hash = %s",
            (project_id, content_hash),
        )
    return str(existing["id"]) if existing else doc_id


def _update_project_status(project_id: str) -> None:
    with DB() as db:
        counts = db.fetch_one(
            """
            SELECT
                COUNT(*)                                        AS total,
                COUNT(*) FILTER (WHERE status = 'done')       AS done,
                COUNT(*) FILTER (WHERE status = 'processing') AS processing
            FROM documents WHERE project_id = %s
            """,
            (project_id,),
        )
        total      = counts["total"]      if counts else 0
        done       = counts["done"]       if counts else 0
        processing = counts["processing"] if counts else 0

        if processing > 0:
            new_status = "processing"
        elif done == total:
            new_status = "ready"
        else:
            new_status = "failed"

        db.execute(
            "UPDATE projects SET status = %s WHERE id = %s",
            (new_status, project_id),
        )


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
    validate_project_id(project_id)
    project = await asyncio.to_thread(_fetch_project, project_id)
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
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    now = datetime.datetime.now(datetime.timezone.utc)

    doc_id = await asyncio.to_thread(
        _create_document_stub, project_id, filename, ext, content_hash
    )

    background_tasks.add_task(
        _run_pipeline_and_update_project,
        project_id,
        client_id,
        file_bytes,
        filename,
        ext,
        doc_id,
    )

    return {
        "id": doc_id,
        "filename": filename,
        "file_type": ext,
        "status": "processing",
        "uploaded_at": now,
    }


@router.get("", response_model=list[DocumentResponse])
def list_documents(project_id: str):
    validate_project_id(project_id)
    with DB() as db:
        return db.fetch_all(
            "SELECT * FROM documents WHERE project_id = %s ORDER BY uploaded_at DESC",
            (project_id,),
        )


def _run_pipeline_and_update_project(
    project_id: str,
    client_id: str,
    file_bytes: bytes,
    filename: str,
    file_type: str,
    doc_id: str,
) -> None:
    """Background task: run pipeline in a thread, then update project status."""
    try:
        with DB() as db:
            db.execute(
                "UPDATE projects SET status = 'processing' WHERE id = %s",
                (project_id,),
            )

        asyncio.run(
            ingest_document(project_id, client_id, file_bytes, filename, file_type, doc_id)
        )

        _update_project_status(project_id)
    except Exception:
        _logger.exception("Pipeline failed for project %s", project_id)
        with DB() as db:
            db.execute(
                "UPDATE projects SET status = 'failed' WHERE id = %s",
                (project_id,),
            )
