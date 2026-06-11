"""
Stage 2 orchestrator.

Runs the full epic + story generation pipeline, writes results to DB,
and exposes a separate push_to_ado() function for on-demand ADO sync.

Flow:
  1. Fetch requirements from DB (all columns needed for story generation)
  2. epic_generator: cheap model groups titles into epics → log metrics
  3. Insert epics into DB
  4. story_generator: mid model generates stories per epic in parallel → log metrics
  5. Insert user stories into DB
  6. Mark project stage2_status = 'ready'

ADO push is intentionally separate — generation and sync are decoupled so
the lead engineer can review stories before pushing.
"""

import logging
import uuid

from config import ADO_ORG, ADO_PAT, ADO_PROJECT, MODEL_CAPABLE, MODEL_CHEAP
from db import DB
from pipeline.ado_client import create_epic, create_user_story, ensure_area_path
from pipeline.epic_generator import generate_epics
from pipeline.story_generator import generate_stories_for_all_epics
from pipeline.utils import text_array_literal

_logger = logging.getLogger(__name__)

_GLOBAL_CONSTRAINT_TOPICS = frozenset(
    {"budget", "testing", "integrations", "team_and_process"}
)


def _extract_global_constraints(requirements: list[dict]) -> list[dict]:
    """
    Rule-based filter — zero LLM cost.

    Returns requirements that are cross-cutting project-wide constraints:
    - sdlc_topic in (budget, testing, integrations, team_and_process): these
      topics are always project-wide, never feature-specific.
    - req_type == 'constraint': explicitly typed as a constraint by Stage 1.

    technical/design topics excluded — usually feature-specific and belong
    in the epic they were grouped into.
    """
    return [
        r for r in requirements
        if r.get("sdlc_topic") in _GLOBAL_CONSTRAINT_TOPICS
        or r.get("req_type") == "constraint"
    ]



async def run_stage2(project_id: str) -> dict:
    """
    Run the full Stage 2 pipeline for a project.
    Returns {epic_count, story_count}.
    Raises ValueError if no requirements exist.
    """
    with DB() as db:
        # Clear previous generation results so re-runs don't accumulate stale
        # epics and stories. Stories must be deleted before epics (FK constraint).
        db.execute("DELETE FROM user_stories WHERE project_id = %s", (project_id,))
        db.execute("DELETE FROM epics WHERE project_id = %s", (project_id,))
        db.execute("DELETE FROM stage2_metrics WHERE project_id = %s", (project_id,))
        db.execute(
            "UPDATE projects SET stage2_status = 'generating' WHERE id = %s",
            (project_id,),
        )

    try:
        # ── Fetch requirements ────────────────────────────────────────────────
        with DB() as db:
            requirements = db.fetch_all(
                """
                SELECT id, title, req_type, sdlc_topic, description, key_specifics
                FROM requirements
                WHERE project_id = %s AND status != 'duplicate'
                ORDER BY created_at
                """,
                (project_id,),
            )

        if not requirements:
            raise ValueError("No requirements found — run Stage 1 first")

        # pg8000 returns UUID objects; convert to strings for JSON handling
        for r in requirements:
            r["id"] = str(r["id"])
            # pg8000 may return None for TEXT[] columns with no value
            r["key_specifics"] = list(r.get("key_specifics") or [])

        requirements_by_id = {r["id"]: r for r in requirements}

        # Rule-based filter — zero LLM cost. Extracts cross-cutting requirements
        # (budget, testing, integrations, team_and_process topics + constraint type)
        # to inject into every epic's story generation prompt.
        global_constraints = _extract_global_constraints(requirements)

        # Fetch direct client answers — highest-confidence content in the project.
        # Injected into every epic's story prompt alongside global constraints.
        with DB() as db:
            answered_clarifications = db.fetch_all(
                """
                SELECT question, answer, context
                FROM clarifications
                WHERE project_id = %s AND status = 'answered'
                ORDER BY created_at
                """,
                (project_id,),
            )

        # ── Step 1: Epic decomposition (cheap model, titles only) ────────────
        epics, epic_in_tok, epic_out_tok, epic_think_tok, epic_dur = await generate_epics(requirements)

        _log_metrics(
            project_id, "epic_decomposition",
            epic_in_tok, epic_out_tok, epic_think_tok, epic_dur,
        )

        if not epics:
            raise ValueError("Epic generation returned empty results — check Groq API key")

        # ── Insert epics into DB ──────────────────────────────────────────────
        epic_rows: list[dict] = []
        with DB() as db:
            for epic in epics:
                epic_id = str(uuid.uuid4())
                req_ids = [str(rid) for rid in epic.get("requirement_ids", [])]
                # pg8000 UUID[] literal pattern (same as source_document_ids in runner.py)
                req_ids_literal = "{" + ",".join(req_ids) + "}"
                db.execute(
                    """
                    INSERT INTO epics
                        (id, project_id, title, description, theme, requirement_ids)
                    VALUES (%s, %s, %s, %s, %s, %s::uuid[])
                    """,
                    (
                        epic_id,
                        project_id,
                        epic.get("title", "Untitled Epic"),
                        epic.get("description", ""),
                        epic.get("theme", "general"),
                        req_ids_literal,
                    ),
                )
                epic["id"] = epic_id
                epic_rows.append(epic)

        # ── Step 2: Story generation (mid model, per epic, parallel) ─────────
        results = await generate_stories_for_all_epics(
            epic_rows,
            requirements_by_id,
            global_constraints,
            clarification_answers=answered_clarifications,
        )

        total_stories = 0
        with DB() as db:
            for i, (epic, stories, story_in_tok, story_out_tok, story_think_tok, story_dur) in enumerate(results):
                if story_dur > 0:
                    _log_metrics(
                        project_id,
                        f"story_generation_epic_{i + 1}",
                        story_in_tok,
                        story_out_tok,
                        story_think_tok,
                        story_dur,
                    )
                for story in stories:
                    story_id = str(uuid.uuid4())
                    ac_list = story.get("acceptance_criteria") or []
                    db.execute(
                        """
                        INSERT INTO user_stories
                            (id, epic_id, project_id, title, description,
                             acceptance_criteria, story_points, assignee)
                        VALUES (%s, %s, %s, %s, %s, %s::text[], %s, %s)
                        """,
                        (
                            story_id,
                            epic["id"],
                            project_id,
                            story.get("title", "Untitled Story"),
                            story.get("description", ""),
                            text_array_literal(ac_list),
                            story.get("story_points"),
                            story.get("assignee"),
                        ),
                    )
                    total_stories += 1

        with DB() as db:
            db.execute(
                "UPDATE projects SET stage2_status = 'ready' WHERE id = %s",
                (project_id,),
            )

        return {"epic_count": len(epic_rows), "story_count": total_stories}

    except Exception:
        with DB() as db:
            db.execute(
                "UPDATE projects SET stage2_status = 'failed' WHERE id = %s",
                (project_id,),
            )
        raise


def push_to_ado(project_id: str, area_path: str = "") -> dict:
    """
    Push all epics and user stories to Azure DevOps.

    Each StackForge project gets its own area path ({ADO_PROJECT}\\{project_name})
    created automatically via the ADO Classifications API before items are pushed.
    This keeps MediBook, CareFlow, etc. separated in the ADO board.

    This is a synchronous operation — it uses httpx.Client (sync) and runs
    sequentially: epics first, then their child stories.
    Returns {epics_pushed, stories_pushed, errors[]}.
    """
    if not all([ADO_ORG, ADO_PROJECT, ADO_PAT]):
        raise ValueError(
            "ADO_ORG, ADO_PROJECT, and ADO_PAT must be set in poc/.env "
            "before pushing to Azure DevOps"
        )

    with DB() as db:
        proj_row = db.fetch_one("SELECT name FROM projects WHERE id = %s", (project_id,))
        epics = db.fetch_all(
            "SELECT * FROM epics WHERE project_id = %s ORDER BY created_at",
            (project_id,),
        )

    project_name = proj_row["name"] if proj_row else project_id

    # area_path resolution:
    # 1. If caller passed an explicit area_path (from UI text input), use it directly
    #    and try to auto-create the node (idempotent).
    # 2. If no area_path provided, derive from project name and try to create.
    # 3. If creation fails either way, fall back to "" (omit AreaPath entirely —
    #    avoids TF401347 when the sub-area doesn't exist in ADO).
    if not area_path:
        area_path = project_name
    try:
        area_path = ensure_area_path(area_path)
    except Exception as e:
        _logger.warning(
            "Could not create ADO area path '%s' (%s) — items will use project default area",
            area_path, e,
        )
        area_path = ""
    tags = project_name

    epics_pushed = 0
    stories_pushed = 0
    errors: list[str] = []

    for epic in epics:
        epic_id = str(epic["id"])
        try:
            # Skip epics already pushed — prevents duplicates on re-push
            if epic.get("ado_work_item_id"):
                ado_epic_url = epic["ado_work_item_url"]
            else:
                ado_epic_id, ado_epic_url = create_epic(
                    epic["title"], epic["description"], area_path=area_path, tags=tags
                )
                with DB() as db:
                    db.execute(
                        "UPDATE epics SET ado_work_item_id = %s, ado_work_item_url = %s WHERE id = %s",
                        (ado_epic_id, ado_epic_url, epic_id),
                    )
                epics_pushed += 1

            with DB() as db:
                stories = db.fetch_all(
                    "SELECT * FROM user_stories WHERE epic_id = %s ORDER BY created_at",
                    (epic_id,),
                )

            for story in stories:
                # Skip stories already pushed
                if story.get("ado_work_item_id"):
                    continue
                try:
                    ac = list(story.get("acceptance_criteria") or [])
                    ado_story_id, ado_story_url = create_user_story(
                        story["title"],
                        story["description"],
                        ac,
                        story.get("story_points"),
                        ado_epic_url,
                        area_path=area_path,
                        tags=tags,
                    )
                    with DB() as db:
                        db.execute(
                            "UPDATE user_stories SET ado_work_item_id = %s, ado_work_item_url = %s WHERE id = %s",
                            (ado_story_id, ado_story_url, str(story["id"])),
                        )
                    stories_pushed += 1
                except Exception as e:
                    errors.append(f"Story '{story['title']}': {e}")

        except Exception as e:
            errors.append(f"Epic '{epic['title']}': {e}")

    return {
        "epics_pushed": epics_pushed,
        "stories_pushed": stories_pushed,
        "errors": errors,
    }


def _log_metrics(
    project_id: str,
    step: str,
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int,
    duration_ms: int,
) -> None:
    model = MODEL_CHEAP if step == "epic_decomposition" else MODEL_CAPABLE
    with DB() as db:
        db.execute(
            """
            INSERT INTO stage2_metrics
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
