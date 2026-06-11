"""
Structured requirement extraction using the capable model (llama-3.3-70b / Sonnet).

Input: combined chunk summaries for a project (never raw document text).
Output: list of structured requirement dicts, each classified by both
        req_type and sdlc_topic, with key_specifics capturing verbatim
        measurements and terms from the source.

Summaries are processed in batches of EXTRACTOR_BATCH_SIZE to avoid
truncating large requirement sets at the output token limit.
"""

import asyncio
import json
import logging
import random

from openai import RateLimitError

from config import EXTRACTOR_BATCH_SIZE, MODEL_CAPABLE, SDLC_TOPICS
from pipeline.llm_utils import extract_usage, get_llm_client
from pipeline.metrics_common import UsageTotals

_client = get_llm_client()
_logger = logging.getLogger(__name__)

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
    "key_specifics: list of up to 3 verbatim measurements, time limits, field names, "
    "UI element names, or specific values from the source. Empty array if none.\n\n"
    "Return ONLY valid JSON:\n"
    '{"requirements": [{'
    '"req_type": "functional|non_functional|constraint|assumption", '
    '"sdlc_topic": "requirements|design|technical|timeline|budget|testing|integrations|team_and_process", '
    '"title": "string (max 10 words)", '
    '"description": "string", '
    '"key_specifics": ["string"], '
    '"confidence": 0.0'
    "}]}"
)

_VALID_SDLC_TOPICS = set(SDLC_TOPICS)
_VALID_REQ_TYPES = {"functional", "non_functional", "constraint", "assumption"}


class ExtractionError(RuntimeError):
    """Raised when all extraction batches fail to produce any requirements."""


async def _extract_batch(
    batch_summaries: list[str],
    batch_index: int,
    retries: int = 4,
) -> tuple[list[dict], int, int, int]:
    """Extract requirements from a single batch of summaries.

    Returns (requirements, input_tokens, output_tokens, thinking_tokens). Token
    counts are captured even when JSON parsing fails — the call still cost tokens.
    """
    combined = "\n\n---\n\n".join(batch_summaries)
    for attempt in range(retries):
        try:
            response = await _client.chat.completions.create(
                model=MODEL_CAPABLE,
                max_tokens=2048,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Extract all requirements from these document summaries:\n\n{combined}",
                    },
                ],
            )
            in_tok, out_tok, think_tok = extract_usage(response)
            try:
                data = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError as exc:
                raw_snippet = response.choices[0].message.content[:200]
                _logger.warning(
                    "Batch %d: JSON parse failed (%s). Raw response start: %s",
                    batch_index,
                    exc,
                    raw_snippet,
                )
                return [], in_tok, out_tok, think_tok
            return data.get("requirements", []), in_tok, out_tok, think_tok
        except RateLimitError:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)
    return [], 0, 0, 0


async def extract_requirements(
    summaries: list[str], document_ids: list[str]
) -> tuple[list[dict], UsageTotals]:
    """
    Takes all chunk summaries for a project, returns (requirement dicts, usage).
    Each dict includes req_type, sdlc_topic, title, description, key_specifics, confidence.
    document_ids: list of document UUIDs that contributed to these summaries.

    Summaries are processed in batches of EXTRACTOR_BATCH_SIZE to avoid
    output token truncation on large documents. usage aggregates token counts
    across every batch call for the Stage 1 metrics report.
    """
    batches = [
        summaries[i: i + EXTRACTOR_BATCH_SIZE]
        for i in range(0, len(summaries), EXTRACTOR_BATCH_SIZE)
    ]
    total_batches = len(batches)
    _logger.info("Extractor: %d summaries → %d batch(es)", len(summaries), total_batches)

    batch_results = await asyncio.gather(*[
        _extract_batch(batch, idx + 1) for idx, batch in enumerate(batches)
    ])

    reqs: list[dict] = []
    usage = UsageTotals()
    failed_batches = 0
    for idx, (batch_reqs, in_tok, out_tok, think_tok) in enumerate(batch_results):
        usage = usage.add(in_tok, out_tok, think_tok)
        if not batch_reqs:
            failed_batches += 1
            _logger.warning("Batch %d/%d returned 0 requirements", idx + 1, total_batches)
        else:
            _logger.info("Batch %d/%d extracted %d requirements", idx + 1, total_batches, len(batch_reqs))
            reqs.extend(batch_reqs)

    if failed_batches > 0:
        _logger.warning(
            "%d/%d extraction batches failed. %d requirements extracted total.",
            failed_batches,
            total_batches,
            len(reqs),
        )

    if not reqs and summaries:
        raise ExtractionError(
            f"All {total_batches} extraction batches failed to produce requirements. "
            "Check LLM response logs above."
        )

    for r in reqs:
        r["source_document_ids"] = document_ids
        r["confidence"] = max(0.0, min(1.0, float(r.get("confidence", 0.8))))
        r["key_specifics"] = [str(s) for s in r.get("key_specifics", []) if s][:3]
        # Sanitize enum fields — fall back to safe defaults if model returns garbage
        if r.get("req_type") not in _VALID_REQ_TYPES:
            _logger.warning("Invalid req_type %r → defaulting to 'functional'", r.get("req_type"))
            r["req_type"] = "functional"
        if r.get("sdlc_topic") not in _VALID_SDLC_TOPICS:
            _logger.warning("Invalid sdlc_topic %r → defaulting to 'requirements'", r.get("sdlc_topic"))
            r["sdlc_topic"] = "requirements"

    return reqs, usage
