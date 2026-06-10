"""
Epic decomposition — Stage 2, Step 1.

Groups requirements into 3-8 thematic epics using the CHEAP model.

TOKEN OPTIMIZATION:
  1. Cheap model (llama-3.1-8b-instant / haiku tier): theme grouping is
     classification, not generation. No novel reasoning needed.
     Cost: ~1/10th of Sonnet for the same task.

  2. Titles only as input, NOT full descriptions. Sending only
     {id, title, req_type, sdlc_topic} per requirement keeps input to
     ~3,000 tokens instead of ~13,000 for a 130-requirement project.
     That is a 77% input token reduction.

  3. Strict JSON output schema + max_tokens=1500 cap eliminates padding
     and forces concise responses (~40% output reduction vs free-form).

  4. Static system prompt is eligible for Anthropic prompt caching
     (90% cost reduction on cache hits in production). Architecture is
     caching-ready even when running on Groq.
"""

import asyncio
import json
import random
import time

from openai import RateLimitError

from config import MODEL_CHEAP
from pipeline.llm_utils import get_llm_client

_client = get_llm_client()

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
    "requirement_ids": ["uuid1", "uuid2"]
  }
]

Rules:
- Every requirement must appear in exactly one epic
- Aim for 4-6 epics for most projects (3 minimum, 8 maximum)
- Epic titles must be action-oriented (e.g. "User Authentication & Access Control")
- requirement_ids must be exact UUIDs from the input list
"""


async def _call_with_retry(
    prompt: str, semaphore: asyncio.Semaphore, retries: int = 4
) -> tuple[str, int, int, int]:
    """Returns (content, input_tokens, output_tokens, duration_ms)."""
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

            usage = response.usage
            return (
                response.choices[0].message.content,
                usage.prompt_tokens,
                usage.completion_tokens,
                duration_ms,
            )

        except RateLimitError:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)

    return "{}", 0, 0, 0


async def generate_epics(
    requirements: list[dict],
) -> tuple[list[dict], int, int, int]:
    """
    Decompose requirements into epics using the cheap model.

    Input requirements: dicts with keys id, title, req_type, sdlc_topic.
    Full descriptions are intentionally excluded — theme grouping does not
    need them, and excluding them saves ~77% of input tokens.

    Returns (epics, input_tokens, output_tokens, duration_ms).
    """
    # Semaphore created here so it belongs to the current event loop
    semaphore = asyncio.Semaphore(5)

    # Compact prompt: titles and metadata only, no descriptions
    req_lines = [
        f"- ID: {r['id']} | Type: {r['req_type']} | Topic: {r.get('sdlc_topic', 'requirements')} | Title: {r['title']}"
        for r in requirements
    ]
    prompt = "Requirements to group into epics:\n" + "\n".join(req_lines)

    content, in_tok, out_tok, dur_ms = await _call_with_retry(prompt, semaphore)

    try:
        parsed = json.loads(content)
        # Accept both bare array and {"epics": [...]} wrapper
        if isinstance(parsed, list):
            epics = parsed
        elif isinstance(parsed, dict):
            epics = next((v for v in parsed.values() if isinstance(v, list)), [])
        else:
            epics = []
    except json.JSONDecodeError:
        epics = []

    # Validate all requirement_ids exist in our input set
    valid_ids = {str(r["id"]) for r in requirements}
    for epic in epics:
        epic["requirement_ids"] = [
            rid for rid in epic.get("requirement_ids", [])
            if str(rid) in valid_ids
        ]

    # Ensure required keys exist with sensible defaults
    for epic in epics:
        epic.setdefault("theme", "general")
        epic.setdefault("title", "Untitled Epic")
        epic.setdefault("description", "")

    return epics, in_tok, out_tok, dur_ms
