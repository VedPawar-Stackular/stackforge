"""
Map-reduce summarization using the cheap model (llama-3.1-8b-instant).

Uses a semaphore to cap concurrent Groq requests at 5 — prevents hitting the
free-tier rate limit (30 req/min) when many chunks are processed in parallel.
Includes retry with exponential backoff on 429 rate-limit responses.
"""

import asyncio
import json
import random

from openai import RateLimitError

from config import MODEL_CHEAP
from pipeline.llm_utils import get_llm_client

_client = get_llm_client()

_SYSTEM_PROMPT = (
    "You are a requirements analyst assistant. Summarise the provided document "
    "chunk in 2-3 concise sentences, preserving all functional requirements, "
    "constraints, and key decisions. Then list up to 5 key points as short "
    "phrases. Return ONLY valid JSON matching this schema:\n"
    '{"summary": "string", "key_points": ["string"]}'
)


async def _summarize_with_retry(raw_text: str, semaphore: asyncio.Semaphore, retries: int = 4) -> str:
    """Call the cheap model with exponential backoff on rate-limit errors."""
    for attempt in range(retries):
        try:
            async with semaphore:
                response = await _client.chat.completions.create(
                    model=MODEL_CHEAP,
                    max_tokens=300,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": raw_text},
                    ],
                )
            data = json.loads(response.choices[0].message.content)
            summary = data.get("summary", "")
            key_points = data.get("key_points", [])
            if key_points:
                return f"{summary} Key points: {'; '.join(key_points)}"
            return summary

        except RateLimitError:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)

    raise RuntimeError("summarize_chunk: all retries exhausted without a result")


async def summarize_all(chunks: list[str]) -> list[str]:
    """Summarise all chunks with rate-limit-safe concurrency.

    Semaphore is created here so it is bound to the current event loop,
    not the loop that was active at import time (which may differ when
    called via asyncio.run() in a FastAPI background thread).
    """
    semaphore = asyncio.Semaphore(5)
    tasks = [_summarize_with_retry(c, semaphore) for c in chunks]
    return await asyncio.gather(*tasks)
