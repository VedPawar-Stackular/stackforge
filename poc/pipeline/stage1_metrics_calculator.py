"""
Stage 1 metrics: persistence + savings report.

`record_step` writes one row per ingestion LLM step (summarization, extraction,
clarification) to stage1_metrics. `get_report` reads them back and builds the same
report shape as the Stage 2 calculator, with two vs-Opus comparisons:

  - Per step: the SAME captured tokens repriced at Opus rates (model-choice delta).
  - Stage level: a naive all-Opus baseline grounded in real captured tokens — an
    unoptimized pipeline that skips the cheap summarization pass and feeds the raw
    document text straight to Opus, narrating prose output instead of strict JSON.
"""

import uuid

from db import DB
from pipeline.metrics_common import (
    PROSE_OUTPUT_MULTIPLIER,
    UsageTotals,
    opus_multiplier,
    opus_reprice,
    step_cost,
    tier_for_model,
)

# Human-readable justification for each step's model choice — shown in the breakdown.
_WHY_MODEL = {
    "summarization": (
        "Cheap model (Haiku tier): map-reduce summarisation compresses raw document "
        "chunks — pure extraction, no novel reasoning. Running this on Opus would cost "
        "~60x more on input tokens for no quality gain on a compression task."
    ),
    "extraction": (
        "Mid model (Sonnet tier): turning short summaries into structured requirement "
        "JSON is schema-constrained generation, not open-ended reasoning. Sonnet is "
        "5x cheaper than Opus and equivalent on structured output."
    ),
    "clarification": (
        "Cheap model (Haiku tier): spotting gaps and ambiguities across a requirement "
        "list is classification-style analysis — the cheap model handles it well."
    ),
}

# Stable display order regardless of created_at ties.
_STEP_ORDER = {"summarization": 0, "extraction": 1, "clarification": 2}


def record_step(
    project_id: str,
    step: str,
    model: str,
    usage: UsageTotals,
    duration_ms: int,
) -> None:
    """Persist one Stage 1 step's token usage. Never raises on empty usage."""
    with DB() as db:
        db.execute(
            """
            INSERT INTO stage1_metrics
                (id, project_id, step, model, input_tokens, output_tokens,
                 thinking_tokens, duration_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                project_id,
                step,
                model,
                usage.input_tokens,
                usage.output_tokens,
                usage.thinking_tokens,
                duration_ms,
            ),
        )


def _aggregate_by_step(rows: list[dict]) -> dict[str, dict]:
    """Sum token counts + duration per step name, across all documents.

    ingest_document runs once per uploaded file, so a multi-document project writes
    several summarization/extraction rows. The report collapses them into one row
    per step so the breakdown stays readable regardless of document count.
    """
    agg: dict[str, dict] = {}
    for row in rows:
        step = row["step"]
        bucket = agg.setdefault(step, {
            "step": step,
            "model": row["model"],
            "input_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
            "duration_ms": 0,
        })
        bucket["input_tokens"] += row["input_tokens"]
        bucket["output_tokens"] += row["output_tokens"]
        bucket["thinking_tokens"] += row.get("thinking_tokens", 0) or 0
        bucket["duration_ms"] += row["duration_ms"]
    return agg


def _naive_baseline(agg: dict[str, dict]) -> dict:
    """All-Opus, no-summarization baseline grounded in real captured tokens.

    naive_input  ≈ the raw chunk text the summarizer actually ingested (an Opus-only
                   pipeline feeds Opus that same raw text directly).
    naive_output ≈ the extraction + clarification output, inflated by the prose
                   multiplier (Opus narrating instead of filling a strict JSON schema).
    """
    summ = agg.get("summarization")
    extr = agg.get("extraction")
    clar = agg.get("clarification")

    naive_input = summ["input_tokens"] if summ else sum(b["input_tokens"] for b in agg.values())
    structured_output = (extr["output_tokens"] if extr else 0) + (
        clar["output_tokens"] if clar else 0
    )
    naive_output = int(structured_output * PROSE_OUTPUT_MULTIPLIER)

    cost = opus_reprice(naive_input, naive_output)
    return {
        "input_tokens": naive_input,
        "output_tokens": naive_output,
        "cost_usd": round(cost, 6),
    }


def get_report(project_id: str) -> dict:
    """Read stage1_metrics for a project and return the full savings report."""
    with DB() as db:
        rows = db.fetch_all(
            "SELECT * FROM stage1_metrics WHERE project_id = %s ORDER BY created_at",
            (project_id,),
        )

    agg = _aggregate_by_step(rows)
    ordered = sorted(agg.values(), key=lambda b: _STEP_ORDER.get(b["step"], 99))

    steps = []
    actual_input = 0
    actual_output = 0
    actual_thinking = 0
    actual_cost = 0.0

    for bucket in ordered:
        tier = tier_for_model(bucket["model"])
        cost = step_cost(bucket["input_tokens"], bucket["output_tokens"], tier)
        opus_cost = opus_reprice(bucket["input_tokens"], bucket["output_tokens"])

        steps.append({
            "step": bucket["step"],
            "model": bucket["model"],
            "tier": tier,
            "input_tokens": bucket["input_tokens"],
            "output_tokens": bucket["output_tokens"],
            "thinking_tokens": bucket["thinking_tokens"],
            "cost_usd": round(cost, 6),
            "opus_equivalent_cost_usd": round(opus_cost, 6),
            "opus_multiplier": opus_multiplier(cost, opus_cost),
            "duration_ms": bucket["duration_ms"],
            "why_this_model": _WHY_MODEL.get(bucket["step"], ""),
        })

        actual_input += bucket["input_tokens"]
        actual_output += bucket["output_tokens"]
        actual_thinking += bucket["thinking_tokens"]
        actual_cost += cost

    naive = _naive_baseline(agg)

    total_actual_tokens = actual_input + actual_output
    total_naive_tokens = naive["input_tokens"] + naive["output_tokens"]
    tokens_saved = max(0, total_naive_tokens - total_actual_tokens)

    savings_pct = (
        round((1.0 - actual_cost / naive["cost_usd"]) * 100, 1)
        if naive["cost_usd"] > 0
        else 0.0
    )

    return {
        "actual_cost_usd": round(actual_cost, 6),
        "naive_cost_usd": naive["cost_usd"],
        "savings_pct": savings_pct,
        "tokens_saved": tokens_saved,
        "actual_input_tokens": actual_input,
        "actual_output_tokens": actual_output,
        "actual_thinking_tokens": actual_thinking,
        "naive_input_tokens": naive["input_tokens"],
        "naive_output_tokens": naive["output_tokens"],
        "steps": steps,
    }
