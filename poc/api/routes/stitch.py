"""
API routes for Google Stitch design generation.

POST /projects/{project_id}/stitch/generate  — trigger screen generation from design.md
GET  /projects/{project_id}/stitch           — return status + screen list
"""

import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.models import StitchGenerateResponse, StitchScreen, StitchStatusResponse
from api.routes import validate_project_id
from pipeline.doc_writer import get_output_dir

router = APIRouter()
_logger = logging.getLogger(__name__)


@router.post("/projects/{project_id}/stitch/generate", response_model=StitchGenerateResponse)
async def generate_stitch(project_id: str, background_tasks: BackgroundTasks):
    """
    Trigger Stitch UI screen generation from the project's design.md.

    Runs in the background. Use GET /stitch to poll for completion.
    Requires STITCH_API_KEY in poc/.env and Node.js installed.
    """
    validate_project_id(project_id)
    from config import STITCH_API_KEY

    if not STITCH_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "STITCH_API_KEY is not configured. "
                "Add it to poc/.env (get it at stitch.withgoogle.com → Settings → API Keys)."
            ),
        )

    # Mark status as "generating" immediately so the UI can poll
    stitch_dir = os.path.join(get_output_dir(project_id), "stitch")
    os.makedirs(stitch_dir, exist_ok=True)
    flag_path = os.path.join(stitch_dir, ".generating")
    error_path = os.path.join(stitch_dir, ".error")

    # Clear any previous error before starting fresh
    if os.path.exists(error_path):
        os.remove(error_path)

    with open(flag_path, "w") as f:
        f.write("1")

    background_tasks.add_task(_run_generation, project_id, flag_path, error_path)
    return StitchGenerateResponse(status="generating")


async def _run_generation(project_id: str, flag_path: str, error_path: str) -> None:
    try:
        from pipeline.stitch_designer import generate_for_project
        await generate_for_project(project_id)
    except Exception as exc:
        _logger.error("Stitch generation failed for project %s: %s", project_id, exc)
        with open(error_path, "w", encoding="utf-8") as f:
            f.write(str(exc))
    finally:
        if os.path.exists(flag_path):
            os.remove(flag_path)


@router.get("/projects/{project_id}/stitch", response_model=StitchStatusResponse)
def get_stitch_status(project_id: str):
    """Return Stitch generation status and screen list for the project."""
    validate_project_id(project_id)
    stitch_dir = os.path.join(get_output_dir(project_id), "stitch")
    metadata_path = os.path.join(stitch_dir, "metadata.json")
    flag_path = os.path.join(stitch_dir, ".generating")
    error_path = os.path.join(stitch_dir, ".error")

    if os.path.exists(flag_path):
        return StitchStatusResponse(
            status="generating", stitch_url=None, screens=[], generated_at=None, error=None
        )

    if os.path.exists(error_path):
        with open(error_path, encoding="utf-8") as f:
            error_msg = f.read().strip()
        return StitchStatusResponse(
            status="error", stitch_url=None, screens=[], generated_at=None, error=error_msg
        )

    if not os.path.exists(metadata_path):
        return StitchStatusResponse(
            status="not_generated", stitch_url=None, screens=[], generated_at=None, error=None
        )

    with open(metadata_path, encoding="utf-8") as f:
        meta = json.load(f)

    from datetime import datetime
    screens = [
        StitchScreen(
            name=s["name"],
            label=s["label"],
            html_path=s.get("html_path") or None,
        )
        for s in meta.get("screens", [])
    ]
    generated_at = None
    if meta.get("generated_at"):
        try:
            generated_at = datetime.fromisoformat(meta["generated_at"])
        except ValueError:
            pass

    return StitchStatusResponse(
        status="ready",
        stitch_url=meta.get("stitch_project_url"),
        screens=screens,
        generated_at=generated_at,
        error=None,
    )
