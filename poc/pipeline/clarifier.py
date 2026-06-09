"""
Clarification agent: analyses extracted requirements and generates targeted
questions about ambiguities, gaps, and unstated assumptions.

Uses the cheap model (llama-3.1-8b-instant / Haiku).
"""

import json

from openai import AsyncOpenAI

from config import GROQ_API_KEY, LLM_BASE_URL, MODEL_CHEAP

_client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=GROQ_API_KEY)

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


async def generate_clarifications(requirements: list[dict]) -> list[dict]:
    """
    Takes a list of requirement dicts, returns list of clarification question dicts.
    requirements: list of {req_type, title, description, confidence}
    """
    # Format requirements as a readable list for the model
    req_text = "\n".join(
        f"[{r['req_type'].upper()}] {r['title']}: {r['description']}"
        for r in requirements
    )

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
    data = json.loads(response.choices[0].message.content)
    return data.get("clarifications", [])
