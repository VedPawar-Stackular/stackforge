"""
API routes for SDLC topic documents.

GET  /projects/{project_id}/docs              — list all 8 topic docs (meta only)
GET  /projects/{project_id}/docs/{topic}      — read one doc's markdown content
POST /projects/{project_id}/docs/{topic}/edit — apply a plain-English edit instruction
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.models import DocContentResponse, DocEditRequest, DocEditResponse, DocMetaResponse
from api.routes import validate_project_id
from config import SDLC_TOPICS
from pipeline.doc_writer import get_doc_path

router = APIRouter()


@router.get("/projects/{project_id}/docs", response_model=list[DocMetaResponse])
def list_docs(project_id: str):
    """Return metadata for all 8 SDLC topic docs for this project."""
    validate_project_id(project_id)
    results = []
    for topic in SDLC_TOPICS:
        path = get_doc_path(project_id, topic)
        if os.path.exists(path):
            stat = os.stat(path)
            results.append(DocMetaResponse(
                topic=topic,
                filename=f"{topic}.md",
                exists=True,
                size_bytes=stat.st_size,
                last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            ))
        else:
            results.append(DocMetaResponse(
                topic=topic,
                filename=f"{topic}.md",
                exists=False,
                size_bytes=0,
                last_modified=None,
            ))
    return results


@router.get("/projects/{project_id}/docs/{topic}", response_model=DocContentResponse)
def get_doc(project_id: str, topic: str):
    """Return the markdown content of a single SDLC topic doc."""
    validate_project_id(project_id)
    if topic not in SDLC_TOPICS:
        raise HTTPException(status_code=400, detail=f"Unknown topic '{topic}'. Valid: {SDLC_TOPICS}")
    path = get_doc_path(project_id, topic)
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"Doc not generated yet for topic '{topic}'. Run the pipeline first.",
        )
    stat = os.stat(path)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return DocContentResponse(
        topic=topic,
        content=content,
        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
    )


@router.post("/projects/{project_id}/docs/{topic}/edit", response_model=DocEditResponse)
async def edit_doc(project_id: str, topic: str, body: DocEditRequest):
    """Apply a plain-English edit instruction to the doc and return updated content."""
    validate_project_id(project_id)
    if topic not in SDLC_TOPICS:
        raise HTTPException(status_code=400, detail=f"Unknown topic '{topic}'. Valid: {SDLC_TOPICS}")
    path = get_doc_path(project_id, topic)
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"Doc not generated yet for topic '{topic}'. Run the pipeline first.",
        )
    try:
        from pipeline.doc_editor import apply_edit
        updated = await apply_edit(project_id, topic, body.instruction)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Edit failed: {e}")
    return DocEditResponse(topic=topic, content=updated)
