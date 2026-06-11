"""Routes: Stage 2 — Epic & User Story generation and Azure DevOps push."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from api.models import (
    EpicResponse,
    Stage2MetricsResponse,
    Stage2StatusResponse,
    StoryResponse,
)
from config import ADO_ORG, ADO_PAT, ADO_PROJECT
from db import DB
from pipeline.metrics_calculator import get_metrics_report
from pipeline.stage2_runner import push_to_ado as _push_to_ado
from pipeline.stage2_runner import run_stage2

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}", tags=["epics"])


@router.post("/generate-epics", status_code=202)
def trigger_generate_epics(project_id: str, background_tasks: BackgroundTasks):
    """
    Trigger Stage 2 generation (runs in background).
    Prerequisite: Stage 1 must be complete (requirements must exist).
    """
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")
        row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM requirements WHERE project_id = %s",
            (project_id,),
        )
        if not row or int(row["cnt"]) == 0:
            raise HTTPException(
                status_code=400,
                detail="No requirements found — run Stage 1 (upload documents) first",
            )

    background_tasks.add_task(_run_stage2_sync, project_id)
    return {"status": "generating", "message": "Stage 2 generation started in background"}


def _run_stage2_sync(project_id: str) -> None:
    """Adapter: runs the async Stage 2 pipeline in a background thread."""
    asyncio.run(run_stage2(project_id))


@router.get("/stage2-status", response_model=Stage2StatusResponse)
def get_stage2_status(project_id: str):
    with DB() as db:
        project = db.fetch_one(
            "SELECT stage2_status FROM projects WHERE id = %s", (project_id,)
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        epic_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM epics WHERE project_id = %s", (project_id,)
        )
        story_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM user_stories WHERE project_id = %s", (project_id,)
        )
        pushed_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM epics WHERE project_id = %s AND ado_work_item_id IS NOT NULL",
            (project_id,),
        )

    return {
        "status": project.get("stage2_status", "idle"),
        "epic_count": int(epic_row["cnt"]) if epic_row else 0,
        "story_count": int(story_row["cnt"]) if story_row else 0,
        "ado_pushed": int(pushed_row["cnt"]) > 0 if pushed_row else False,
    }


@router.get("/epics", response_model=list[EpicResponse])
def list_epics(project_id: str):
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

        epics = db.fetch_all(
            "SELECT * FROM epics WHERE project_id = %s ORDER BY created_at",
            (project_id,),
        )
        # Single query for all story counts — avoids N+1 round trips
        counts_rows = db.fetch_all(
            "SELECT epic_id, COUNT(*) AS cnt FROM user_stories WHERE project_id = %s GROUP BY epic_id",
            (project_id,),
        )
        story_counts = {str(r["epic_id"]): int(r["cnt"]) for r in counts_rows}
        result = []
        for epic in epics:
            result.append({
                **{k: (str(v) if k in ("id",) else v) for k, v in epic.items()},
                "story_count": story_counts.get(str(epic["id"]), 0),
            })
    return result


@router.get("/stories", response_model=list[StoryResponse])
def list_all_stories(project_id: str):
    """All stories for a project in one call — avoids N per-epic round trips in the UI."""
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")
        stories = db.fetch_all(
            "SELECT * FROM user_stories WHERE project_id = %s ORDER BY created_at",
            (project_id,),
        )
    return [
        {
            **{k: (str(v) if k in ("id", "epic_id", "project_id") else v) for k, v in s.items()},
            "acceptance_criteria": list(s.get("acceptance_criteria") or []),
        }
        for s in stories
    ]


@router.get("/epics/{epic_id}/stories", response_model=list[StoryResponse])
def list_stories(project_id: str, epic_id: str):
    with DB() as db:
        if not db.fetch_one(
            "SELECT id FROM epics WHERE id = %s AND project_id = %s",
            (epic_id, project_id),
        ):
            raise HTTPException(status_code=404, detail="Epic not found")

        stories = db.fetch_all(
            "SELECT * FROM user_stories WHERE epic_id = %s ORDER BY created_at",
            (epic_id,),
        )

    return [
        {
            **{k: (str(v) if k in ("id", "epic_id", "project_id") else v) for k, v in s.items()},
            "acceptance_criteria": list(s.get("acceptance_criteria") or []),
        }
        for s in stories
    ]


@router.post("/push-to-ado", status_code=202)
def push_to_ado(
    project_id: str,
    background_tasks: BackgroundTasks,
    area_path: str = Query(
        "",
        description=(
            "ADO sub-area for this project. StackForge will try to create it if it doesn't exist. "
            "Leave empty to fall back to the ADO project default area."
        ),
    ),
):
    """
    Push all generated epics and user stories to Azure DevOps (background task).
    Requires ADO_ORG, ADO_PROJECT, ADO_PAT in poc/.env.
    Poll /stage2-status for ado_pushed completion.
    """
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")
        epic_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM epics WHERE project_id = %s", (project_id,)
        )
        if not epic_row or int(epic_row["cnt"]) == 0:
            raise HTTPException(
                status_code=400,
                detail="No epics found — run Generate Epics first",
            )

    try:
        if not all([ADO_ORG, ADO_PROJECT, ADO_PAT]):
            raise ValueError(
                "ADO_ORG, ADO_PROJECT, and ADO_PAT must be set in poc/.env "
                "before pushing to Azure DevOps"
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    background_tasks.add_task(_run_ado_push_sync, project_id, area_path)
    return {"status": "pushing", "message": "ADO push started. Poll /stage2-status for completion."}


def _run_ado_push_sync(project_id: str, area_path: str) -> None:
    """Run the synchronous ADO push in a background thread."""
    try:
        result = _push_to_ado(project_id, area_path=area_path)
        _logger.info(
            "ADO push complete for %s: %d epics, %d stories, %d errors",
            project_id,
            result.get("epics_pushed", 0),
            result.get("stories_pushed", 0),
            len(result.get("errors", [])),
        )
        if result.get("errors"):
            for err in result["errors"]:
                _logger.warning("ADO push error: %s", err)
    except Exception:
        _logger.exception("ADO push failed for project %s", project_id)


@router.get("/stage2-metrics", response_model=Stage2MetricsResponse)
def get_stage2_metrics(project_id: str):
    """Return the token cost savings report for Stage 2."""
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

    return get_metrics_report(project_id)
