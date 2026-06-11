"""
Epic decomposition — Stage 2, Step 1.

Groups requirements into 3-8 thematic epics using the CHEAP model.

TOKEN OPTIMIZATION:
  1. Cheap model (llama-3.1-8b-instant / haiku tier): theme grouping is
     classification, not generation. No novel reasoning needed.
     Cost: ~1/10th of Sonnet for the same task.

  2. Titles only as input, NOT full descriptions. Sending only
     {idx, title, req_type, sdlc_topic} per requirement keeps input to
     ~3,000 tokens instead of ~13,000 for a 130-requirement project.
     That is a 77% input token reduction.

  3. Integer indices instead of raw UUIDs in the prompt. Shorter tokens,
     no hallucination risk on long UUID strings. Code resolves indices
     back to UUIDs after parsing.

  4. Strict JSON output schema + max_tokens=1500 cap eliminates padding
     and forces concise responses (~40% output reduction vs free-form).

  5. Static system prompt is eligible for Anthropic prompt caching
     (90% cost reduction on cache hits in production). Architecture is
     caching-ready even when running on Groq.
"""

import asyncio
import json
import logging
import random
import time

from openai import RateLimitError

from config import MODEL_CHEAP
from pipeline.llm_utils import extract_usage, get_llm_client

_client = get_llm_client()
_logger = logging.getLogger(__name__)

# Static, cacheable system prompt — format is demonstrated, not described.
_SYSTEM_PROMPT = """\
You are an agile coach. Given a list of software requirements, group them into 3-8 high-level epics.
Each epic represents a major feature area or theme.

Return ONLY valid JSON — an array of epic objects. No explanation or prose outside the JSON.
Schema:
[
  {
    "theme": "short_snake_case_theme",
    "title": "Epic title (5-8 words)",
    "description": "2-3 sentence description of what this epic covers and why it matters",
    "requirement_ids": [1, 3, 7]
  }
]

Rules:
- Every requirement must appear in exactly one epic
- Aim for 4-6 epics for most projects (3 minimum, 8 maximum)
- Epic titles must be action-oriented (e.g. "User Authentication & Access Control")
- requirement_ids must be integer indices from the input list (the number before the colon on each line)
"""


async def _call_with_retry(
    prompt: str, semaphore: asyncio.Semaphore, retries: int = 4
) -> tuple[str, int, int, int, int]:
    """Returns (content, input_tokens, output_tokens, thinking_tokens, duration_ms)."""
    for attempt in range(retries):
        try:
            async with semaphore:
                t0 = time.monotonic()
                response = await _client.chat.completions.create(
                    model=MODEL_CHEAP,
                    max_tokens=1500,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                )
                duration_ms = int((time.monotonic() - t0) * 1000)

            in_tok, out_tok, think_tok = extract_usage(response)
            return (
                response.choices[0].message.content,
                in_tok,
                out_tok,
                think_tok,
                duration_ms,
            )

        except RateLimitError:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)

    return "{}", 0, 0, 0, 0


async def generate_epics(
    requirements: list[dict],
) -> tuple[list[dict], int, int, int, int]:
    """
    Decompose requirements into epics using the cheap model.

    Input requirements: dicts with keys id, title, req_type, sdlc_topic.
    Full descriptions are intentionally excluded — theme grouping does not
    need them, and excluding them saves ~77% of input tokens.

    Returns (epics, input_tokens, output_tokens, thinking_tokens, duration_ms).
    """
    # Semaphore created here so it belongs to the current event loop
    semaphore = asyncio.Semaphore(5)

    # Build 1-indexed mapping: "1" → actual UUID, so we never send raw UUIDs
    # to the LLM. Short integers are cheaper tokens and can't be hallucinated.
    idx_to_id: dict[str, str] = {
        str(i + 1): str(r["id"]) for i, r in enumerate(requirements)
    }

    # Compact prompt: index + type + topic + title only, no descriptions or UUIDs
    req_lines = [
        f"- {i + 1}: [{r['req_type']}] {r.get('sdlc_topic', 'requirements')} | {r['title']}"
        for i, r in enumerate(requirements)
    ]
    prompt = "Requirements to group into epics:\n" + "\n".join(req_lines)

    content, in_tok, out_tok, think_tok, dur_ms = await _call_with_retry(prompt, semaphore)

    try:
        parsed = json.loads(content)
        # Accept both bare array and {"epics": [...]} wrapper
        if isinstance(parsed, list):
            epics = parsed
        elif isinstance(parsed, dict):
            epics = next((v for v in parsed.values() if isinstance(v, list)), [])
        else:
            epics = []
    except json.JSONDecodeError as exc:
        _logger.warning("Epic generator JSON parse failed: %s. Returning empty epic list.", exc)
        epics = []

    # Resolve integer indices back to actual UUIDs; drop any out-of-range indices.
    all_assigned_ids: set[str] = set()
    for epic in epics:
        resolved: list[str] = []
        for raw_idx in epic.get("requirement_ids", []):
            key = str(raw_idx).strip()
            actual_id = idx_to_id.get(key)
            if actual_id:
                resolved.append(actual_id)
                all_assigned_ids.add(actual_id)
            else:
                _logger.warning("Epic '%s': unrecognised index %r — skipped", epic.get("title"), raw_idx)
        epic["requirement_ids"] = resolved

    # Coverage check — every requirement must appear in exactly one epic.
    all_valid_ids = set(idx_to_id.values())
    orphan_ids = all_valid_ids - all_assigned_ids
    if orphan_ids:
        # Build title lookup for readable log output
        id_to_title = {str(r["id"]): r["title"] for r in requirements}
        orphan_titles = [id_to_title.get(oid, oid) for oid in orphan_ids]
        _logger.warning(
            "ORPHAN REQUIREMENTS — %d requirement(s) not assigned to any epic: %s",
            len(orphan_ids),
            orphan_titles,
        )

    # Ensure required keys exist with sensible defaults
    for epic in epics:
        epic.setdefault("theme", "general")
        epic.setdefault("title", "Untitled Epic")
        epic.setdefault("description", "")

    return epics, in_tok, out_tok, think_tok, dur_ms
