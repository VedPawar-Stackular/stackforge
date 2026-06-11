"""
Map-reduce summarization using the cheap model (llama-3.1-8b-instant).

Uses a semaphore to cap concurrent Groq requests at 5 — prevents hitting the
free-tier rate limit (30 req/min) when many chunks are processed in parallel.
Includes retry with exponential backoff on 429 rate-limit responses.

Doc-type-aware: spec docs (FRS/SOW) use extraction-preserving bullet mode
(max 15 bullets, 600 tokens); transcripts/meeting notes use compact summary
mode (2-3 sentences, 300 tokens). Both modes preserve UI/design details.
"""

import asyncio
import json
import logging
import random
import re

from openai import RateLimitError

from config import MODEL_CHEAP
from pipeline.llm_utils import extract_usage, get_llm_client
from pipeline.metrics_common import UsageTotals

_client = get_llm_client()
_logger = logging.getLogger(__name__)

# Keywords in the filename that identify transcript/meeting docs.
# Everything else is treated as a spec document (FRS, SOW, requirements, etc.)
# — safer to extract more rather than less.
_TRANSCRIPT_KEYWORDS = re.compile(
    r"(transcript|meeting|notes|call|interview|discussion|minutes)",
    re.IGNORECASE,
)

_SPEC_SYSTEM_PROMPT = (
    "You are a requirements analyst. Extract ALL requirements, constraints, "
    "and design details from this document chunk as a bullet list. "
    "Include exact numbers, time limits, field names, UI/screen/branding details, "
    "measurable thresholds, and any named system components. "
    "Do not summarise or paraphrase — preserve specific values verbatim. "
    "Return ONLY valid JSON matching this schema:\n"
    '{"key_points": ["string"]}\n'
    "Max 15 bullets."
)

_TRANSCRIPT_SYSTEM_PROMPT = (
    "You are a requirements analyst assistant. Summarise the provided document "
    "chunk in 2-3 concise sentences, preserving all functional requirements, "
    "constraints, and key decisions. Include any UI, screen, design, or branding "
    "details mentioned. Then list up to 5 key points as short phrases. "
    "Return ONLY valid JSON matching this schema:\n"
    '{"summary": "string", "key_points": ["string"]}'
)


def _detect_doc_mode(doc_name: str) -> str:
    """Return 'transcript' or 'spec' based on the document filename."""
    if _TRANSCRIPT_KEYWORDS.search(doc_name):
        return "transcript"
    return "spec"


async def _summarize_with_retry(
    raw_text: str,
    semaphore: asyncio.Semaphore,
    mode: str = "spec",
    retries: int = 6,
) -> tuple[str, int, int, int]:
    """Call the cheap model with exponential backoff on rate-limit errors.

    Returns (summary_text, input_tokens, output_tokens, thinking_tokens) so the
    caller can aggregate token usage for the metrics report.
    """
    if mode == "transcript":
        system_prompt = _TRANSCRIPT_SYSTEM_PROMPT
        max_tokens = 300
    else:
        system_prompt = _SPEC_SYSTEM_PROMPT
        max_tokens = 600

    for attempt in range(retries):
        try:
            async with semaphore:
                response = await _client.chat.completions.create(
                    model=MODEL_CHEAP,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": raw_text},
                    ],
                )
            in_tok, out_tok, think_tok = extract_usage(response)
            data = json.loads(response.choices[0].message.content)

            if mode == "spec":
                key_points = data.get("key_points", [])
                text = "; ".join(key_points) if key_points else ""
            else:
                summary = data.get("summary", "")
                key_points = data.get("key_points", [])
                if key_points:
                    text = f"{summary} Key points: {'; '.join(key_points)}"
                else:
                    text = summary
            return text, in_tok, out_tok, think_tok

        except RateLimitError:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)

    raise RuntimeError("summarize_chunk: all retries exhausted without a result")


# Shared across ALL concurrent summarize_all() calls so the 5-slot cap is
# a true global rate-limit gate, not per-document. Safe in Python 3.10+ because
# Semaphore binds to the running event loop on first await, not at construction.
_semaphore = asyncio.Semaphore(5)


async def summarize_all(chunks: list[str], doc_name: str = "") -> tuple[list[str], UsageTotals]:
    """Summarise all chunks with rate-limit-safe concurrency.

    doc_name is used to detect whether this is a spec document (FRS/SOW)
    or a transcript/meeting note, selecting the appropriate extraction mode.

    Returns (summaries, usage) where usage aggregates token counts across every
    chunk call — one call per chunk — for the Stage 1 metrics report.
    """
    mode = _detect_doc_mode(doc_name)
    _logger.info("Summarizer mode: %s (doc: %s)", mode, doc_name or "<unknown>")
    tasks = [_summarize_with_retry(c, _semaphore, mode=mode) for c in chunks]
    results = await asyncio.gather(*tasks)

    summaries: list[str] = []
    usage = UsageTotals()
    for text, in_tok, out_tok, think_tok in results:
        summaries.append(text)
        usage = usage.add(in_tok, out_tok, think_tok)
    return summaries, usage
