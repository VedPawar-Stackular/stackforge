"""
Stage 3 metrics calculator.

Reads stage3_metrics from the DB and produces a savings report comparing
the optimized approach against a naive (single Opus call, no routing) baseline.

The naive baseline represents an unoptimized pipeline:
  - Opus for all task generation (most expensive model, no routing)
  - All stories sent in a single prompt (no context scoping)
  - No RAG context (full story history instead of top-3 hits)
  - Free-form prose output (~40% more tokens than structured JSON)
  - No parallelism (sequential story processing)

Sprint assignment has zero token cost in our approach — the naive equivalent
assumes the planner asks Opus to schedule sprints (~500 tokens input/output).
"""

from db import DB
from pipeline.metrics_common import (
    PROSE_OUTPUT_MULTIPLIER,
    opus_multiplier,
    opus_reprice,
    step_cost,
    tier_for_model,
)

# Naive baseline constants
_NAIVE_SPRINT_PLAN_TOKENS = 500       # Opus sprint scheduling prompt + output
_NAIVE_TOKENS_PER_STORY_INPUT = 300   # Full story + all context in one call
_NAIVE_SYSTEM_PROMPT_TOKENS = 2000    # System prompt + all stories header
_TOKENS_PER_TASK_JSON = 80            # Approximate output tokens per task in JSON

# Human-readable explanations shown in the UI breakdown table
_WHY_MODEL = {
    "sprint_assignment": (
        "Zero LLM cost: sprint scheduling is greedy bin-packing (first-fit "
        "decreasing by story points). A deterministic algorithm with no "
        "probabilistic ambiguity — no LLM needed. Logged at 0 tokens to make "
        "the $0 cost explicit in the report."
    ),
    "task_generation": (
        "Capable model (Sonnet tier): task decomposition follows a fixed structure "
        "(title, description, type, hours). No novel reasoning required. "
        "Sonnet is 5-10x cheaper than Opus for equivalent quality on "
        "structured, schema-constrained outputs."
    ),
}


def _naive_baseline(total_stories: int, total_tasks: int) -> dict:
    """
    Calculate what a naive, unoptimized approach would cost.

    Assumptions:
    - Everything runs on Opus (no model routing)
    - Sprint assignment via Opus prompt (~500 tokens)
    - All story descriptions sent in one call (no scoping)
    - Output is free-form prose (~40% more tokens than structured JSON)
    """
    naive_input = (
        _NAIVE_SPRINT_PLAN_TOKENS
        + _NAIVE_SYSTEM_PROMPT_TOKENS
        + total_stories * _NAIVE_TOKENS_PER_STORY_INPUT
    )
    naive_output = int(total_tasks * _TOKENS_PER_TASK_JSON * PROSE_OUTPUT_MULTIPLIER)
    cost = opus_reprice(naive_input, naive_output)
    return {
        "input_tokens": naive_input,
        "output_tokens": naive_output,
        "cost_usd": round(cost, 6),
    }


def get_metrics_report(project_id: str) -> dict:
    """Read stage3_metrics for a project and return the full savings report."""
    with DB() as db:
        metric_rows = db.fetch_all(
            "SELECT * FROM stage3_metrics WHERE project_id = %s ORDER BY created_at",
            (project_id,),
        )
        story_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM user_stories WHERE project_id = %s",
            (project_id,),
        )
        task_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM tasks WHERE project_id = %s",
            (project_id,),
        )

    total_stories = int(story_row["cnt"]) if story_row else 0
    total_tasks = int(task_row["cnt"]) if task_row else 0

    steps = []
    actual_input_total = 0
    actual_output_total = 0
    actual_thinking_total = 0
    actual_cost_total = 0.0

    for row in metric_rows:
        tier = tier_for_model(row["model"])
        cost = step_cost(row["input_tokens"], row["output_tokens"], tier)
        opus_cost = opus_reprice(row["input_tokens"], row["output_tokens"])
        thinking = row.get("thinking_tokens", 0) or 0

        is_sprint = row["step"] == "sprint_assignment"
        why = _WHY_MODEL["sprint_assignment"] if is_sprint else _WHY_MODEL["task_generation"]

        steps.append({
            "step": row["step"],
            "model": row["model"],
            "tier": tier,
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "thinking_tokens": thinking,
            "cost_usd": round(cost, 6),
            "opus_equivalent_cost_usd": round(opus_cost, 6),
            "opus_multiplier": opus_multiplier(cost, opus_cost),
            "duration_ms": row["duration_ms"],
            "why_this_model": why,
        })

        actual_input_total += row["input_tokens"]
        actual_output_total += row["output_tokens"]
        actual_thinking_total += thinking
        actual_cost_total += cost

    naive = _naive_baseline(total_stories, total_tasks)

    total_actual_tokens = actual_input_total + actual_output_total
    total_naive_tokens = naive["input_tokens"] + naive["output_tokens"]
    tokens_saved = max(0, total_naive_tokens - total_actual_tokens)

    savings_pct = (
        round((1.0 - actual_cost_total / naive["cost_usd"]) * 100, 1)
        if naive["cost_usd"] > 0
        else 0.0
    )

    return {
        "actual_cost_usd": round(actual_cost_total, 6),
        "naive_cost_usd": naive["cost_usd"],
        "savings_pct": savings_pct,
        "tokens_saved": tokens_saved,
        "actual_input_tokens": actual_input_total,
        "actual_output_tokens": actual_output_total,
        "actual_thinking_tokens": actual_thinking_total,
        "naive_input_tokens": naive["input_tokens"],
        "naive_output_tokens": naive["output_tokens"],
        "steps": steps,
    }
