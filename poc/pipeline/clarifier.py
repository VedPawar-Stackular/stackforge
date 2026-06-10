"""
Clarification agent: analyses extracted requirements and generates targeted
questions about ambiguities, gaps, and unstated assumptions.

Uses the cheap model (llama-3.1-8b-instant / Haiku).
"""

import asyncio
import json
import random

from openai import RateLimitError

from config import MODEL_CHEAP
from pipeline.llm_utils import get_llm_client

_client = get_llm_client()

_SYSTEM_PROMPT = (
    "You are a requirements analyst preparing a project for software development. "
    "Review the extracted requirements and identify:\n"
    "  - Ambiguous or vague requirements that need clarification\n"
    "  - Missing information a developer would need\n"
    "  - Conflicting requirements\n"
    "  - Unstated assumptions that should be confirmed\n\n"
    "Generate 4-8 specific, actionable clarification questions. Each question "
    "must reference the specific requirement or topic it targets.\n\n"
    "Return ONLY valid JSON:\n"
    '{"clarifications": [{"question": "string", "context": "string (which requirement '
    'or area this targets)", "priority": "high|medium|low"}]}'
)


async def generate_clarifications(requirements: list[dict], retries: int = 4) -> list[dict]:
    """
    Takes a list of requirement dicts, returns list of clarification question dicts.
    requirements: list of {req_type, title, description, confidence}
    """
    req_text = "\n".join(
        f"[{r['req_type'].upper()}] {r['title']}: {r['description']}"
        for r in requirements
    )
    for attempt in range(retries):
        try:
            response = await _client.chat.completions.create(
                model=MODEL_CHEAP,
                max_tokens=1024,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Analyse these requirements and generate clarification questions:\n\n{req_text}",
                    },
                ],
            )
            try:
                data = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError:
                data = {}
            return data.get("clarifications", [])
        except RateLimitError:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)
    return []
