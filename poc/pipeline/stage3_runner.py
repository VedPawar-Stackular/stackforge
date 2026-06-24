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

from config import MODEL_CAPABLE, SPRINT_CAPACITY_DEFAULT
from db import DB
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
