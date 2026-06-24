"""
Task decomposition — Stage 3, Step 2.

Generates 3-5 development tasks for each user story using the CAPABLE (mid-tier)
model. All stories are processed in parallel via asyncio.gather with a shared
rate-limit semaphore — identical pattern to story_generator.py in Stage 2.

TOKEN OPTIMIZATION:
  1. Capable model (Sonnet tier), not Opus: task decomposition follows a fixed
     structure (title, description, type, hours). No novel reasoning required.
     Sonnet is 5-10x cheaper than Opus for equivalent quality on structured tasks.

  2. Context scoped per story: each call receives ONLY the single story
     (~200-300 tokens) + top-3 RAG hits (~300 tokens) = ~600 tokens total.
     A naive approach would send the full backlog (~15,000 tokens) per call.
     That is a ~96% per-call input reduction.

  3. Parallel execution: all N stories run concurrently via asyncio.gather.
     Wall-clock time ≈ time of one call, not N × one call.

  4. RAG context injection: top-3 similar past stories retrieved via BM25
     keyword search over the project's existing rag_chunks. This simulates
     the Stage 6 KB retrieval pattern — no separate historical store needed.
     Retrieval is free (no LLM call) and guides estimation accuracy.

  5. Strict JSON schema + max_tokens=1000 cap per story. No prose bloat.
"""

import asyncio
import json
import random
import time

from openai import RateLimitError

from config import MODEL_CAPABLE
from pipeline.llm_utils import extract_usage, get_llm_client
from rag.search import hybrid_search

_client = get_llm_client()

_VALID_TASK_TYPES = frozenset(
    {"backend", "frontend", "testing", "devops", "design", "documentation"}
)

# Static system prompt — eligible for Anthropic prompt caching in production.
# Format is demonstrated with an example, not described in prose.
_SYSTEM_PROMPT = """\
You are a senior software engineer breaking user stories into development tasks.
Given a story with acceptance criteria, generate 3-5 concrete, estimable development tasks.

Return ONLY valid JSON — an object with a "tasks" array. No explanation or prose.
Schema:
{
  "tasks": [
    {
      "title": "Short imperative task title (5-10 words)",
      "description": "What to build and how — 1-2 sentences",
      "task_type": "backend",
      "estimated_hours": 4.0
    }
  ]
}

Rules:
- 3-5 tasks per story (never fewer, never more)
- task_type must be one of: backend | frontend | testing | devops | design | documentation
- estimated_hours: realistic estimate (0.5 - 16.0 range; use 0.5 increments)
- Every acceptance criterion should map to at least one task
- Include at least one testing task per story

--- EXAMPLE ---
Story: "As a patient, I want to book an appointment with an available provider so that I can receive care at a convenient time"
Acceptance Criteria:
- Given a logged-in patient, when they select a provider and time slot, then the appointment is confirmed
- Given a time slot that becomes unavailable, when a patient tries to book it, then they see alternatives
- Given a booked appointment, when the patient views their dashboard, then details are visible

Output:
{
  "tasks": [
    {
      "title": "Create appointment booking API endpoint",
      "description": "Build POST /appointments route with slot availability check, conflict detection, and confirmation response.",
      "task_type": "backend",
      "estimated_hours": 5.0
    },
    {
      "title": "Build appointment booking UI component",
      "description": "Provider selector, calendar date picker, and time slot grid with real-time availability updates.",
      "task_type": "frontend",
      "estimated_hours": 6.0
    },
    {
      "title": "Add appointment to patient dashboard",
      "description": "Fetch and display upcoming appointments on the patient dashboard with status and provider details.",
      "task_type": "frontend",
      "estimated_hours": 3.0
    },
    {
      "title": "Write integration tests for booking flow",
      "description": "Test happy path booking, slot conflict handling, and dashboard display via API integration tests.",
      "task_type": "testing",
      "estimated_hours": 4.0
    }
  ]
}
"""

_RAG_CONTEXT_TOP_K = 3


async def _generate_for_story(
    story: dict,
    project_id: str,
    semaphore: asyncio.Semaphore,
    retries: int = 4,
) -> tuple[list[dict], int, int, int, int]:
    """
    Generate development tasks for one user story.

    RAG context: top-3 similar chunks retrieved via BM25 from the project's
    rag_chunks. These represent similar past requirements or stories, giving
    the model calibration context for estimation without sending the full
    history. Retrieval runs synchronously before the async LLM call.

    Returns (tasks, input_tokens, output_tokens, thinking_tokens, duration_ms).
    """
    title = story.get("title", "")
    description = story.get("description", "")
    ac_list = list(story.get("acceptance_criteria") or [])
    story_points = story.get("story_points")

    # Retrieve similar past content via BM25 — zero LLM cost, simulates Stage 6 KB
    rag_hits = hybrid_search(project_id, title)[:_RAG_CONTEXT_TOP_K]

    prompt = f"Story: {title}\nDescription: {description}\n"
    if story_points:
        prompt += f"Story Points: {story_points}\n"
    if ac_list:
        prompt += "Acceptance Criteria:\n" + "\n".join(f"- {ac}" for ac in ac_list)

    if rag_hits:
        rag_text = "\n".join(
            f"- [{hit.get('content_type', 'ref')}] {hit.get('text', '')[:200]}"
            for hit in rag_hits
        )
        prompt += f"\n\nSimilar project context (for estimation calibration):\n{rag_text}"

    prompt += "\n\nGenerate 3-5 development tasks for this story."

    for attempt in range(retries):
        try:
            async with semaphore:
                t0 = time.monotonic()
                response = await _client.chat.completions.create(
                    model=MODEL_CAPABLE,
                    max_tokens=1000,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                )
                duration_ms = int((time.monotonic() - t0) * 1000)

            in_tok, out_tok, think_tok = extract_usage(response)
            content = response.choices[0].message.content

            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    tasks = parsed.get("tasks", [])
                elif isinstance(parsed, list):
                    tasks = parsed
                else:
                    tasks = []
            except json.JSONDecodeError:
                tasks = []

            # Normalise and validate fields
            validated = []
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                task_type = t.get("task_type", "backend")
                if task_type not in _VALID_TASK_TYPES:
                    task_type = "backend"
                try:
                    hours = float(t.get("estimated_hours", 4.0))
                    hours = max(0.5, min(16.0, hours))
                except (TypeError, ValueError):
                    hours = 4.0
                validated.append({
                    "title": t.get("title", "Untitled Task"),
                    "description": t.get("description", ""),
                    "task_type": task_type,
                    "estimated_hours": hours,
                })

            return validated, in_tok, out_tok, think_tok, duration_ms

        except RateLimitError:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)

    return [], 0, 0, 0, 0


async def generate_tasks_for_all_stories(
    stories: list[dict],
    project_id: str,
) -> list[tuple[dict, list[dict], int, int, int, int]]:
    """
    Generate development tasks for all stories in parallel.

    Semaphore is created here so it belongs to the current event loop and is
    shared across all parallel story calls (respects Groq 30 req/min limit).

    Returns list of (story, tasks, input_tokens, output_tokens, thinking_tokens, duration_ms).
    """
    semaphore = asyncio.Semaphore(5)

    task_coros = [
        _generate_for_story(story, project_id, semaphore)
        for story in stories
    ]
    results = await asyncio.gather(*task_coros)

    return [
        (story, tasks, in_tok, out_tok, think_tok, dur)
        for story, (tasks, in_tok, out_tok, think_tok, dur) in zip(stories, results)
    ]
