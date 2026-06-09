"""Routes: Stage 2 — Epic & User Story generation and Azure DevOps push."""

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.models import (
    AdoPushResponse,
    EpicResponse,
    Stage2MetricsResponse,
    Stage2StatusResponse,
    StoryResponse,
)
from db import DB

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
    from pipeline.stage2_runner import run_stage2
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
        result = []
        for epic in epics:
            story_count_row = db.fetch_one(
                "SELECT COUNT(*) AS cnt FROM user_stories WHERE epic_id = %s",
                (str(epic["id"]),),
            )
            result.append({
                **{k: (str(v) if k in ("id",) else v) for k, v in epic.items()},
                "story_count": int(story_count_row["cnt"]) if story_count_row else 0,
            })
    return result


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


@router.post("/push-to-ado", response_model=AdoPushResponse)
def push_to_ado(project_id: str):
    """
    Push all generated epics and user stories to Azure DevOps.
    Requires ADO_ORG, ADO_PROJECT, ADO_PAT in poc/.env.
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
        from pipeline.stage2_runner import push_to_ado as _push
        return _push(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stage2-metrics", response_model=Stage2MetricsResponse)
def get_stage2_metrics(project_id: str):
    """Return the token cost savings report for Stage 2."""
    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

    from pipeline.metrics_calculator import get_metrics_report
    return get_metrics_report(project_id)
