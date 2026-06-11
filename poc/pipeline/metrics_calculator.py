"""
Stage 2 metrics calculator.

Reads stage2_metrics from the DB and produces a savings report comparing
the optimized approach against a naive (single Opus call, no routing) baseline.

The naive baseline represents what an unoptimized pipeline would cost:
  - Single Opus call for ALL requirement descriptions at once
  - No model routing (everything goes to the most expensive model)
  - No context scoping (all 130 reqs per call, not just the epic's 15-20)
  - Free-form prose output (~40% more tokens than structured JSON)

Every delta between actual and naive maps to a named optimization decision.
This report is the evidence shown to the lead engineer.
"""

from db import DB
from pipeline.metrics_common import (
    PROSE_OUTPUT_MULTIPLIER,
    opus_multiplier,
    opus_reprice,
    step_cost,
    tier_for_model,
)

# Average tokens per requirement when full descriptions are included
_TOKENS_PER_REQ_FULL = 100
# Naive baseline: a single system prompt + all requirements in one call
_NAIVE_SYSTEM_PROMPT_TOKENS = 1500
# Approximate output tokens per story in structured JSON format
_TOKENS_PER_STORY_JSON = 80

# Human-readable explanation for each step — shown in the UI breakdown table
_WHY_MODEL = {
    "epic_decomposition": (
        "Cheap model (Haiku tier): grouping requirements into themes is pure "
        "classification — no content generation needed. Cheap model does this "
        "at ~1/10th the cost of Sonnet, with equivalent output quality."
    ),
    "story_generation": (
        "Mid model (Sonnet tier): user story generation follows a fixed "
        "'As a [role]...' template — templated generation, not novel reasoning. "
        "Sonnet is 5-10x cheaper than Opus and produces equivalent quality "
        "for structured, schema-constrained outputs."
    ),
}


def _naive_baseline(total_requirements: int, total_stories: int) -> dict:
    """
    Calculate what a naive, unoptimized approach would cost.

    Assumptions:
    - Everything runs on Opus (most expensive model, no routing)
    - All requirement full descriptions are sent in a single call
    - Output is free-form prose (~40% more tokens than structured JSON)
    - No parallelism benefit (single sequential call)
    """
    naive_input = _NAIVE_SYSTEM_PROMPT_TOKENS + total_requirements * _TOKENS_PER_REQ_FULL
    naive_output = int(total_stories * _TOKENS_PER_STORY_JSON * PROSE_OUTPUT_MULTIPLIER)

    cost = opus_reprice(naive_input, naive_output)
    return {
        "input_tokens": naive_input,
        "output_tokens": naive_output,
        "cost_usd": round(cost, 6),
    }


def get_metrics_report(project_id: str) -> dict:
    """
    Read stage2_metrics for a project and return the full savings report.
    """
    with DB() as db:
        metric_rows = db.fetch_all(
            "SELECT * FROM stage2_metrics WHERE project_id = %s ORDER BY created_at",
            (project_id,),
        )
        req_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM requirements WHERE project_id = %s",
            (project_id,),
        )
        story_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM user_stories WHERE project_id = %s",
            (project_id,),
        )

    total_reqs = int(req_row["cnt"]) if req_row else 0
    total_stories = int(story_row["cnt"]) if story_row else 0

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

        is_decomp = row["step"] == "epic_decomposition"
        why = _WHY_MODEL["epic_decomposition"] if is_decomp else _WHY_MODEL["story_generation"]

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

    naive = _naive_baseline(total_reqs, total_stories)

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
