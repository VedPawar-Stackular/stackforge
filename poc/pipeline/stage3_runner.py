"""
Stage 3 orchestrator: Sprint & Task Planning.

Flow:
  1. Fetch all user_stories for the project (from Stage 2)
  2. Step A: sprint_planner — rule-based bin-packing, zero LLM cost
  3. Insert sprints + sprint_stories into DB
  4. Step B: task_generator — parallel per-story task decomposition (capable model)
  5. Insert tasks into DB
  6. Mark project stage3_status = 'ready'

Metrics are logged to stage3_metrics for every LLM call. The sprint_assignment
step is also logged with 0 tokens to make the zero-cost explicit in the report.
"""

import logging
import time
import uuid

from config import ADO_ORG, ADO_PAT, ADO_PROJECT, MODEL_CAPABLE, SPRINT_CAPACITY_DEFAULT
from db import DB
from pipeline.ado_client import create_task, ensure_area_path, ensure_iteration_path
from pipeline.sprint_planner import assign_stories_to_sprints
from pipeline.task_generator import generate_tasks_for_all_stories

_logger = logging.getLogger(__name__)


async def run_stage3(project_id: str, sprint_capacity: int = SPRINT_CAPACITY_DEFAULT) -> dict:
    """
    Run the full Stage 3 pipeline for a project.
    Returns {"sprint_count": N, "task_count": M}.
    Raises ValueError if no user stories exist (Stage 2 must be complete).
    """
    with DB() as db:
        # Clear previous Stage 3 results so re-runs don't accumulate stale data.
        # Order: tasks → sprint_stories → sprints (FK cascade order)
        db.execute("DELETE FROM tasks WHERE project_id = %s", (project_id,))
        db.execute("DELETE FROM sprint_stories WHERE project_id = %s", (project_id,))
        db.execute("DELETE FROM sprints WHERE project_id = %s", (project_id,))
        db.execute("DELETE FROM stage3_metrics WHERE project_id = %s", (project_id,))
        db.execute(
            "UPDATE projects SET stage3_status = 'generating' WHERE id = %s",
            (project_id,),
        )

    try:
        # ── Fetch user stories (produced by Stage 2) ──────────────────────────
        with DB() as db:
            stories = db.fetch_all(
                """
                SELECT id, epic_id, title, description, acceptance_criteria, story_points
                FROM user_stories
                WHERE project_id = %s
                ORDER BY created_at
                """,
                (project_id,),
            )

        if not stories:
            raise ValueError(
                "No user stories found — run Stage 2 (Generate Epics & Stories) first"
            )

        # Normalise types from pg8000
        for s in stories:
            s["id"] = str(s["id"])
            s["epic_id"] = str(s["epic_id"])
            s["acceptance_criteria"] = list(s.get("acceptance_criteria") or [])

        # ── Step A: Sprint assignment (rule-based, zero LLM cost) ─────────────
        t0 = time.monotonic()
        sprint_plan = assign_stories_to_sprints(stories, capacity=sprint_capacity)
        sprint_dur = int((time.monotonic() - t0) * 1000)

        # Log sprint assignment as 0-token step — makes the $0 cost explicit
        _log_metrics(project_id, "sprint_assignment", "rule-based", 0, 0, 0, sprint_dur)

        # ── Insert sprints and story assignments into DB ───────────────────────
        sprint_db_rows: list[dict] = []
        with DB() as db:
            for sprint in sprint_plan:
                sprint_id = str(uuid.uuid4())
                db.execute(
                    """
                    INSERT INTO sprints
                        (id, project_id, sprint_number, name, capacity_points, total_points)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        sprint_id,
                        project_id,
                        sprint["number"],
                        sprint["name"],
                        sprint["capacity_points"],
                        sprint["total_points"],
                    ),
                )
                for order, story in enumerate(sprint["stories"]):
                    db.execute(
                        """
                        INSERT INTO sprint_stories
                            (id, sprint_id, story_id, project_id, priority_order)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid.uuid4()),
                            sprint_id,
                            story["id"],
                            project_id,
                            order,
                        ),
                    )
                sprint_db_rows.append({**sprint, "id": sprint_id})

        # ── Step B: Task decomposition (capable model, parallel) ──────────────
        results = await generate_tasks_for_all_stories(stories, project_id)

        total_tasks = 0
        with DB() as db:
            for i, (story, tasks, in_tok, out_tok, think_tok, dur) in enumerate(results):
                if dur > 0:
                    _log_metrics(
                        project_id,
                        f"task_generation_story_{i + 1}",
                        MODEL_CAPABLE,
                        in_tok,
                        out_tok,
                        think_tok,
                        dur,
                    )
                for task in tasks:
                    db.execute(
                        """
                        INSERT INTO tasks
                            (id, story_id, project_id, title, description,
                             task_type, estimated_hours)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid.uuid4()),
                            story["id"],
                            project_id,
                            task.get("title", "Untitled Task"),
                            task.get("description", ""),
                            task.get("task_type", "backend"),
                            task.get("estimated_hours", 4.0),
                        ),
                    )
                    total_tasks += 1

        with DB() as db:
            db.execute(
                "UPDATE projects SET stage3_status = 'ready' WHERE id = %s",
                (project_id,),
            )

        _logger.info(
            "Stage 3 complete for %s: %d sprints, %d tasks",
            project_id, len(sprint_plan), total_tasks,
        )
        return {"sprint_count": len(sprint_plan), "task_count": total_tasks}

    except Exception:
        with DB() as db:
            db.execute(
                "UPDATE projects SET stage3_status = 'failed' WHERE id = %s",
                (project_id,),
            )
        raise


def push_to_ado_stage3(project_id: str, area_path: str = "") -> dict:
    """
    Push all sprints (as ADO Iterations) and tasks (as ADO Task work items) to ADO.

    Sprints → ADO Iterations via ensure_iteration_path().
    Tasks   → ADO Task work items linked to their parent User Story.

    Prerequisite: Stage 2 ADO push should be done first so stories have
    ado_work_item_url. Tasks whose parent story has no ADO URL are pushed
    standalone (no parent link) and the story title is added to errors[].

    Idempotent — skips sprints and tasks already pushed (ado_work_item_id set).
    Returns {"sprints_pushed": N, "tasks_pushed": M, "errors": [...]}.
    """
    if not all([ADO_ORG, ADO_PROJECT, ADO_PAT]):
        raise ValueError(
            "ADO_ORG, ADO_PROJECT, and ADO_PAT must be set in poc/.env "
            "before pushing to Azure DevOps"
        )

    with DB() as db:
        proj_row = db.fetch_one("SELECT name FROM projects WHERE id = %s", (project_id,))
        sprints = db.fetch_all(
            "SELECT * FROM sprints WHERE project_id = %s ORDER BY sprint_number",
            (project_id,),
        )

    project_name = proj_row["name"] if proj_row else project_id

    # Resolve area_path — same fallback pattern as Stage 2 push_to_ado()
    if not area_path:
        area_path = project_name
    try:
        area_path = ensure_area_path(area_path)
    except Exception as e:
        _logger.warning(
            "Could not create ADO area path '%s' (%s) — tasks will use project default area",
            area_path, e,
        )
        area_path = ""

    tags = project_name
    sprints_pushed = 0
    tasks_pushed = 0
    errors: list[str] = []

    for sprint in sprints:
        sprint_id = str(sprint["id"])
        sprint_name = sprint["name"]

        # Idempotency: ado_work_item_id = -1 means iteration already created
        if sprint.get("ado_work_item_id") is not None:
            iteration_path = sprint.get("ado_iteration_path") or ""
        else:
            try:
                iteration_path = ensure_iteration_path(sprint_name)
                with DB() as db:
                    db.execute(
                        """
                        UPDATE sprints
                        SET ado_work_item_id = -1, ado_work_item_url = '', ado_iteration_path = %s
                        WHERE id = %s
                        """,
                        (iteration_path, sprint_id),
                    )
                sprints_pushed += 1
            except Exception as e:
                _logger.warning("Could not create ADO iteration '%s' (%s) — tasks won't be assigned to sprint", sprint_name, e)
                iteration_path = ""

        # Fetch all tasks for stories in this sprint
        with DB() as db:
            sprint_tasks = db.fetch_all(
                """
                SELECT t.id, t.title, t.description, t.task_type, t.estimated_hours,
                       t.ado_work_item_id, t.story_id,
                       us.title AS story_title, us.ado_work_item_url AS story_ado_url
                FROM tasks t
                JOIN sprint_stories ss ON ss.story_id = t.story_id
                JOIN user_stories us ON us.id = t.story_id
                WHERE ss.sprint_id = %s
                ORDER BY t.created_at
                """,
                (sprint_id,),
            )

        for task in sprint_tasks:
            task_id = str(task["id"])

            # Idempotency: skip tasks already pushed
            if task.get("ado_work_item_id") is not None:
                continue

            story_ado_url = task.get("story_ado_url") or ""
            if not story_ado_url:
                errors.append(
                    f"Task '{task['title']}': parent story '{task['story_title']}' "
                    "not yet pushed to ADO — push epics/stories first for parent links"
                )

            try:
                ado_task_id, ado_task_url = create_task(
                    title=task["title"],
                    description=task.get("description", ""),
                    task_type=task.get("task_type", "backend"),
                    estimated_hours=float(task.get("estimated_hours") or 4.0),
                    parent_work_item_url=story_ado_url,
                    area_path=area_path,
                    iteration_path=iteration_path,
                    tags=tags,
                )
                with DB() as db:
                    db.execute(
                        "UPDATE tasks SET ado_work_item_id = %s, ado_work_item_url = %s WHERE id = %s",
                        (ado_task_id, ado_task_url, task_id),
                    )
                tasks_pushed += 1
            except Exception as e:
                errors.append(f"Task '{task['title']}': {e}")

    return {"sprints_pushed": sprints_pushed, "tasks_pushed": tasks_pushed, "errors": errors}


def _log_metrics(
    project_id: str,
    step: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int,
    duration_ms: int,
) -> None:
    with DB() as db:
        db.execute(
            """
            INSERT INTO stage3_metrics
                (id, project_id, step, model, input_tokens, output_tokens,
                 thinking_tokens, duration_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                project_id,
                step,
                model,
                input_tokens,
                output_tokens,
                thinking_tokens,
                duration_ms,
            ),
        )
