"""Routes: Stage 3 — Sprint & Task Planning."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from api.models import (
    SprintResponse,
    SprintStoryResponse,
    Stage3AdoPushResponse,
    Stage3MetricsResponse,
    Stage3StatusResponse,
    TaskResponse,
)
from api.routes import validate_project_id
from config import ADO_ORG, ADO_PAT, ADO_PROJECT
from db import DB
from pipeline.stage3_metrics_calculator import get_metrics_report
from pipeline.stage3_runner import push_to_ado_stage3 as _push_to_ado_stage3
from pipeline.stage3_runner import run_stage3

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}", tags=["sprints"])


@router.post("/generate-sprints", status_code=202)
def trigger_generate_sprints(
    project_id: str,
    background_tasks: BackgroundTasks,
    sprint_capacity: int = Query(
        20,
        ge=5,
        le=100,
        description="Team velocity in story points per sprint (default: 20)",
    ),
):
    """
    Trigger Stage 3 sprint & task generation (runs in background).
    Prerequisite: Stage 2 must be complete (user stories must exist).
    Poll /stage3-status for progress.
    """
    validate_project_id(project_id)

    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")
        story_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM user_stories WHERE project_id = %s",
            (project_id,),
        )
        if not story_row or int(story_row["cnt"]) == 0:
            raise HTTPException(
                status_code=400,
                detail="No user stories found — run Stage 2 (Generate Epics & Stories) first",
            )

    background_tasks.add_task(_run_stage3_sync, project_id, sprint_capacity)
    return {
        "status": "generating",
        "message": f"Stage 3 generation started (capacity: {sprint_capacity} pts/sprint)",
    }


def _run_stage3_sync(project_id: str, sprint_capacity: int) -> None:
    """Adapter: runs the async Stage 3 pipeline in a background thread."""
    asyncio.run(run_stage3(project_id, sprint_capacity=sprint_capacity))


@router.get("/stage3-status", response_model=Stage3StatusResponse)
def get_stage3_status(project_id: str):
    """Poll Stage 3 generation progress."""
    validate_project_id(project_id)

    with DB() as db:
        project = db.fetch_one(
            "SELECT stage3_status FROM projects WHERE id = %s", (project_id,)
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        sprint_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM sprints WHERE project_id = %s", (project_id,)
        )
        task_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM tasks WHERE project_id = %s", (project_id,)
        )
        planned_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM sprint_stories WHERE project_id = %s", (project_id,)
        )
        ado_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM tasks WHERE project_id = %s AND ado_work_item_id IS NOT NULL",
            (project_id,),
        )

    return {
        "status": project.get("stage3_status", "idle"),
        "sprint_count": int(sprint_row["cnt"]) if sprint_row else 0,
        "task_count": int(task_row["cnt"]) if task_row else 0,
        "total_stories_planned": int(planned_row["cnt"]) if planned_row else 0,
        "ado_pushed": int(ado_row["cnt"]) > 0 if ado_row else False,
    }


@router.post("/push-sprints-to-ado", status_code=202)
def push_sprints_to_ado(
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
    Push all sprints (as ADO Iterations) and tasks (as ADO Task work items) to ADO.
    Runs in background — poll /stage3-status for ado_pushed completion.
    Requires ADO_ORG, ADO_PROJECT, ADO_PAT in poc/.env.
    """
    validate_project_id(project_id)

    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")
        task_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM tasks WHERE project_id = %s", (project_id,)
        )
        if not task_row or int(task_row["cnt"]) == 0:
            raise HTTPException(
                status_code=400,
                detail="No tasks found — run Stage 3 (Generate Sprint Plan) first",
            )

    if not all([ADO_ORG, ADO_PROJECT, ADO_PAT]):
        raise HTTPException(
            status_code=400,
            detail="ADO_ORG, ADO_PROJECT, and ADO_PAT must be set in poc/.env before pushing to Azure DevOps",
        )

    background_tasks.add_task(_run_ado_push_stage3_sync, project_id, area_path)
    return {"status": "pushing", "message": "ADO push started. Poll /stage3-status for completion."}


def _run_ado_push_stage3_sync(project_id: str, area_path: str) -> None:
    """Run the synchronous Stage 3 ADO push in a background thread."""
    try:
        result = _push_to_ado_stage3(project_id, area_path=area_path)
        _logger.info(
            "Stage 3 ADO push complete for %s: %d sprints, %d tasks, %d errors",
            project_id,
            result.get("sprints_pushed", 0),
            result.get("tasks_pushed", 0),
            len(result.get("errors", [])),
        )
        for err in result.get("errors", []):
            _logger.warning("Stage 3 ADO push error: %s", err)
    except Exception:
        _logger.exception("Stage 3 ADO push failed for project %s", project_id)


@router.get("/sprints", response_model=list[SprintResponse])
def list_sprints(project_id: str):
    """List all sprints with story and task counts. Single query — no N+1."""
    validate_project_id(project_id)

    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

        sprints = db.fetch_all(
            "SELECT * FROM sprints WHERE project_id = %s ORDER BY sprint_number",
            (project_id,),
        )
        # Story counts per sprint
        story_count_rows = db.fetch_all(
            "SELECT sprint_id, COUNT(*) AS cnt FROM sprint_stories WHERE project_id = %s GROUP BY sprint_id",
            (project_id,),
        )
        story_counts = {str(r["sprint_id"]): int(r["cnt"]) for r in story_count_rows}

        # Task counts per sprint (via sprint_stories → tasks join)
        task_count_rows = db.fetch_all(
            """
            SELECT ss.sprint_id, COUNT(t.id) AS cnt
            FROM sprint_stories ss
            JOIN tasks t ON t.story_id = ss.story_id
            WHERE ss.project_id = %s
            GROUP BY ss.sprint_id
            """,
            (project_id,),
        )
        task_counts = {str(r["sprint_id"]): int(r["cnt"]) for r in task_count_rows}

    result = []
    for sprint in sprints:
        sid = str(sprint["id"])
        result.append({
            **{k: (str(v) if k == "id" else v) for k, v in sprint.items()},
            "story_count": story_counts.get(sid, 0),
            "task_count": task_counts.get(sid, 0),
        })
    return result


@router.get("/sprints/{sprint_id}/stories", response_model=list[SprintStoryResponse])
def list_sprint_stories(project_id: str, sprint_id: str):
    """Stories assigned to a sprint, each with their task list nested."""
    validate_project_id(project_id)

    with DB() as db:
        if not db.fetch_one(
            "SELECT id FROM sprints WHERE id = %s AND project_id = %s",
            (sprint_id, project_id),
        ):
            raise HTTPException(status_code=404, detail="Sprint not found")

        story_rows = db.fetch_all(
            """
            SELECT us.id, us.epic_id, us.title, us.description,
                   us.acceptance_criteria, us.story_points
            FROM sprint_stories ss
            JOIN user_stories us ON us.id = ss.story_id
            WHERE ss.sprint_id = %s
            ORDER BY ss.priority_order
            """,
            (sprint_id,),
        )

        story_ids = [str(r["id"]) for r in story_rows]
        all_tasks: dict[str, list[dict]] = {sid: [] for sid in story_ids}

        if story_ids:
            # Single query for all tasks in this sprint — avoids N+1
            placeholders = ",".join(["%s"] * len(story_ids))
            task_rows = db.fetch_all(
                f"SELECT * FROM tasks WHERE story_id IN ({placeholders}) ORDER BY created_at",
                tuple(story_ids),
            )
            for task in task_rows:
                sid = str(task["story_id"])
                all_tasks.setdefault(sid, []).append({
                    **{k: (str(v) if k in ("id", "story_id", "project_id") else v)
                       for k, v in task.items()},
                })

    result = []
    for story in story_rows:
        sid = str(story["id"])
        result.append({
            "id": sid,
            "epic_id": str(story["epic_id"]),
            "title": story["title"],
            "description": story["description"],
            "story_points": story.get("story_points"),
            "tasks": all_tasks.get(sid, []),
        })
    return result


@router.get("/sprints/{sprint_id}/tasks", response_model=list[TaskResponse])
def list_sprint_tasks(project_id: str, sprint_id: str):
    """Flat list of all tasks for stories in a sprint."""
    validate_project_id(project_id)

    with DB() as db:
        if not db.fetch_one(
            "SELECT id FROM sprints WHERE id = %s AND project_id = %s",
            (sprint_id, project_id),
        ):
            raise HTTPException(status_code=404, detail="Sprint not found")

        tasks = db.fetch_all(
            """
            SELECT t.*
            FROM tasks t
            JOIN sprint_stories ss ON ss.story_id = t.story_id
            WHERE ss.sprint_id = %s
            ORDER BY ss.priority_order, t.created_at
            """,
            (sprint_id,),
        )

    return [
        {**{k: (str(v) if k in ("id", "story_id", "project_id") else v) for k, v in t.items()}}
        for t in tasks
    ]


@router.get("/stage3-metrics", response_model=Stage3MetricsResponse)
def get_stage3_metrics(project_id: str):
    """Return the token cost savings report for Stage 3."""
    validate_project_id(project_id)

    with DB() as db:
        if not db.fetch_one("SELECT id FROM projects WHERE id = %s", (project_id,)):
            raise HTTPException(status_code=404, detail="Project not found")

    return get_metrics_report(project_id)
