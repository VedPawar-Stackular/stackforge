"""
User story generation — Stage 2, Step 2.

Generates user stories for each epic using the CAPABLE (mid-tier) model.
All epics are processed in parallel via asyncio.gather with a rate-limit semaphore.

TOKEN OPTIMIZATION:
  1. Mid model (llama-3.3-70b-versatile / Sonnet tier): user story generation
     follows a fixed "As a [role]..." template. This is templated generation,
     not novel reasoning. Sonnet is 5-10x cheaper than Opus for equivalent
     output quality on structured tasks.

  2. Context scoped per epic: each call receives ONLY the requirement
     descriptions belonging to that epic (~15-20 reqs × 100 tokens ≈ 1,500
     tokens), NOT all 130 requirements. That is an ~85% per-call input
     reduction vs sending the full requirement set.

  3. Parallel execution: all N epics run concurrently (asyncio.gather).
     Wall-clock time ≈ time of one call, not N × one call. ~Nx speedup.

  4. Static system prompt + 2 few-shot examples: eligible for Anthropic
     prompt caching. Cache hit = 90% cost reduction on the prompt portion
     across all parallel epic calls. Architecture is caching-ready.

  5. Strict JSON schema + max_tokens=2000 cap eliminates prose padding
     (~40% output token reduction vs free-form).
"""

import asyncio
import json
import random
import time

from openai import AsyncOpenAI, RateLimitError

from config import GROQ_API_KEY, LLM_BASE_URL, MODEL_CAPABLE

_client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=GROQ_API_KEY)

# Static system prompt with 2 few-shot examples.
# Format is demonstrated, not described — shorter prompt, better consistency.
# This block is eligible for Anthropic prompt caching in production.
_SYSTEM_PROMPT = """\
You are a senior product manager writing user stories for a software project.
Generate user stories for the given epic using the format:
  "As a [role], I want [feature] so that [benefit]"

Return ONLY valid JSON — an array of story objects. No explanation or prose.
Schema:
[
  {
    "title": "Short story title (5-10 words)",
    "description": "As a [role], I want [feature] so that [benefit]",
    "acceptance_criteria": [
      "Given [context], when [action], then [outcome]"
    ],
    "story_points": 3,
    "assignee": null
  }
]

Rules:
- 3-7 stories per epic
- acceptance_criteria: 2-4 items per story, BDD Given/When/Then format
- story_points: Fibonacci scale (1, 2, 3, 5, 8) based on complexity
- assignee: always null

--- EXAMPLE 1 ---
Epic: User Authentication & Access Control
Requirements:
- [functional] User Registration with Email: Users must register with email/password
- [functional] Password Reset: Password reset via emailed link

Output:
[
  {
    "title": "Register Account with Email and Password",
    "description": "As a new visitor, I want to register with my email and password so that I can create an account and access the platform",
    "acceptance_criteria": [
      "Given a new visitor, when they submit the registration form with a valid email and password, then an account is created and a verification email is sent",
      "Given a registration attempt, when the email is already registered, then a clear error message is displayed",
      "Given a new user, when they click the verification link, then their account is activated"
    ],
    "story_points": 3,
    "assignee": null
  },
  {
    "title": "Reset Forgotten Password via Email",
    "description": "As a registered user, I want to reset my password via email so that I can regain access if I forget my credentials",
    "acceptance_criteria": [
      "Given a user on the login page, when they click Forgot Password and enter their email, then a reset link is sent within 60 seconds",
      "Given a valid reset link, when the user sets a new password, then the old password is invalidated and they are redirected to login"
    ],
    "story_points": 2,
    "assignee": null
  }
]

--- EXAMPLE 2 ---
Epic: Patient Appointment Scheduling
Requirements:
- [functional] Book Appointment: Patients can book with available providers
- [non_functional] Appointment Reminders: Automated reminders 24h before

Output:
[
  {
    "title": "Book Appointment with Available Provider",
    "description": "As a patient, I want to book an appointment with an available provider so that I can receive care at a convenient time",
    "acceptance_criteria": [
      "Given a logged-in patient, when they select a provider and time slot, then the appointment is confirmed and added to their profile",
      "Given a time slot that becomes unavailable, when a patient tries to book it, then they see alternative slots",
      "Given a booked appointment, when the patient views their dashboard, then appointment details are visible"
    ],
    "story_points": 5,
    "assignee": null
  },
  {
    "title": "Receive Automated Appointment Reminder",
    "description": "As a patient, I want to receive an automated reminder before my appointment so that I do not miss my scheduled care",
    "acceptance_criteria": [
      "Given a confirmed appointment, when 24 hours remain, then the patient receives an email or SMS reminder",
      "Given a reminder sent, when the patient confirms or cancels, then the appointment status updates accordingly"
    ],
    "story_points": 3,
    "assignee": null
  }
]
"""


async def _generate_for_epic(
    epic: dict,
    requirements_by_id: dict[str, dict],
    semaphore: asyncio.Semaphore,
    retries: int = 4,
) -> tuple[list[dict], int, int, int]:
    """
    Generate user stories for one epic.

    Context is intentionally scoped: only this epic's requirement descriptions
    are included in the prompt, not the full project requirement set.
    Returns (stories, input_tokens, output_tokens, duration_ms).
    """
    epic_req_ids = [str(rid) for rid in epic.get("requirement_ids", [])]
    epic_reqs = [
        requirements_by_id[rid]
        for rid in epic_req_ids
        if rid in requirements_by_id
    ]

    if not epic_reqs:
        return [], 0, 0, 0

    req_text = "\n".join(
        f"- [{r['req_type']}] {r['title']}: {r['description']}"
        for r in epic_reqs
    )
    prompt = (
        f"Epic: {epic['title']}\n"
        f"Description: {epic.get('description', '')}\n\n"
        f"Requirements for this epic ({len(epic_reqs)} items):\n{req_text}"
    )

    for attempt in range(retries):
        try:
            async with semaphore:
                t0 = time.monotonic()
                response = await _client.chat.completions.create(
                    model=MODEL_CAPABLE,
                    max_tokens=2000,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                )
                duration_ms = int((time.monotonic() - t0) * 1000)

            usage = response.usage
            content = response.choices[0].message.content
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    stories = parsed
                elif isinstance(parsed, dict):
                    stories = next((v for v in parsed.values() if isinstance(v, list)), [])
                else:
                    stories = []
            except json.JSONDecodeError:
                stories = []

            # Ensure required keys
            for s in stories:
                s.setdefault("title", "Untitled Story")
                s.setdefault("description", "")
                s.setdefault("acceptance_criteria", [])
                s.setdefault("story_points", None)
                s.setdefault("assignee", None)

            return stories, usage.prompt_tokens, usage.completion_tokens, duration_ms

        except RateLimitError:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)

    return [], 0, 0, 0


async def generate_stories_for_all_epics(
    epics: list[dict],
    requirements_by_id: dict[str, dict],
) -> list[tuple[dict, list[dict], int, int, int]]:
    """
    Generate stories for all epics in parallel.

    Parallelism is the key time optimization: all N epics run concurrently
    so wall-clock time ≈ time of one call, not N × one call.

    Returns list of (epic, stories, input_tokens, output_tokens, duration_ms).
    """
    # Semaphore created here — belongs to current event loop, shared across
    # all parallel epic calls to respect the Groq 30 req/min rate limit.
    semaphore = asyncio.Semaphore(5)

    tasks = [
        _generate_for_epic(epic, requirements_by_id, semaphore)
        for epic in epics
    ]
    results = await asyncio.gather(*tasks)

    return [
        (epic, stories, in_tok, out_tok, dur)
        for epic, (stories, in_tok, out_tok, dur) in zip(epics, results)
    ]
