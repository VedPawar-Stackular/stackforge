"""
Structured requirement extraction using the capable model (llama-3.3-70b / Sonnet).

Input: combined chunk summaries for a project (never raw document text).
Output: list of structured requirement dicts, each classified by both
        req_type and sdlc_topic.
"""

import json

from openai import AsyncOpenAI

from config import GROQ_API_KEY, LLM_BASE_URL, MODEL_CAPABLE, SDLC_TOPICS

_client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=GROQ_API_KEY)

_SDLC_TOPIC_LIST = ", ".join(SDLC_TOPICS)

_SYSTEM_PROMPT = (
    "You are a senior requirements engineer. You will receive summaries of "
    "client documents (SOWs, meeting transcripts, requirement docs). Extract "
    "ALL requirements as structured objects.\n\n"
    "req_type values:\n"
    "  functional       — what the system must DO\n"
    "  non_functional   — quality attributes (performance, security, compliance)\n"
    "  constraint       — fixed limitations (budget, timeline, technology)\n"
    "  assumption       — things taken as true without confirmation\n\n"
    "sdlc_topic — the SDLC area this requirement belongs to. Choose exactly ONE:\n"
    f"  {_SDLC_TOPIC_LIST}\n\n"
    "  requirements   — functional requirements, features, user needs, scope\n"
    "  design         — UI/UX, wireframes, brand, components, flows, styling\n"
    "  technical      — architecture, stack, APIs, DB, infra, security\n"
    "  timeline       — phases, milestones, deadlines, dependencies\n"
    "  budget         — costs, payment schedule, resource allocation\n"
    "  testing        — test requirements, UAT, acceptance criteria, coverage\n"
    "  integrations   — third-party services, ERP, payment gateways, external APIs\n"
    "  team_and_process — roles, responsibilities, change management, communication\n\n"
    "confidence: 0.0-1.0. Use 0.6-0.7 for inferred/implicit, 0.8-1.0 for explicit.\n\n"
    "Return ONLY valid JSON:\n"
    '{"requirements": [{'
    '"req_type": "functional|non_functional|constraint|assumption", '
    '"sdlc_topic": "requirements|design|technical|timeline|budget|testing|integrations|team_and_process", '
    '"title": "string (max 10 words)", '
    '"description": "string", '
    '"confidence": 0.0'
    "}]}"
)

_VALID_SDLC_TOPICS = set(SDLC_TOPICS)
_VALID_REQ_TYPES = {"functional", "non_functional", "constraint", "assumption"}


async def extract_requirements(summaries: list[str], document_ids: list[str]) -> list[dict]:
    """
    Takes all chunk summaries for a project, returns list of requirement dicts.
    Each dict includes req_type, sdlc_topic, title, description, confidence.
    document_ids: list of document UUIDs that contributed to these summaries.
    """
    combined = "\n\n---\n\n".join(summaries)
    response = await _client.chat.completions.create(
        model=MODEL_CAPABLE,
        max_tokens=4096,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Extract all requirements from these document summaries:\n\n{combined}",
            },
        ],
    )
    data = json.loads(response.choices[0].message.content)
    reqs = data.get("requirements", [])

    for r in reqs:
        r["source_document_ids"] = document_ids
        r["confidence"] = max(0.0, min(1.0, float(r.get("confidence", 0.8))))
        # Sanitize enum fields — fall back to safe defaults if model returns garbage
        if r.get("req_type") not in _VALID_REQ_TYPES:
            r["req_type"] = "functional"
        if r.get("sdlc_topic") not in _VALID_SDLC_TOPICS:
            r["sdlc_topic"] = "requirements"

    return reqs
