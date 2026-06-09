"""
Map-reduce summarization using the cheap model (llama-3.1-8b-instant).

Uses a semaphore to cap concurrent Groq requests at 5 — prevents hitting the
free-tier rate limit (30 req/min) when many chunks are processed in parallel.
Includes retry with exponential backoff on 429 rate-limit responses.
"""

import asyncio
import json
import random

from openai import AsyncOpenAI, RateLimitError

from config import GROQ_API_KEY, LLM_BASE_URL, MODEL_CHEAP

_client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=GROQ_API_KEY)

# Max concurrent Groq API calls across the whole process
_semaphore = asyncio.Semaphore(5)

_SYSTEM_PROMPT = (
    "You are a requirements analyst assistant. Summarise the provided document "
    "chunk in 2-3 concise sentences, preserving all functional requirements, "
    "constraints, and key decisions. Then list up to 5 key points as short "
    "phrases. Return ONLY valid JSON matching this schema:\n"
    '{"summary": "string", "key_points": ["string"]}'
)


async def _summarize_with_retry(raw_text: str, retries: int = 4) -> str:
    """Call the cheap model with exponential backoff on rate-limit errors."""
    for attempt in range(retries):
        try:
            async with _semaphore:
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

    return ""


async def summarize_chunk(raw_text: str) -> str:
    return await _summarize_with_retry(raw_text)


async def summarize_all(chunks: list[str]) -> list[str]:
    """Summarise all chunks with rate-limit-safe concurrency."""
    tasks = [summarize_chunk(c) for c in chunks]
    return await asyncio.gather(*tasks)
