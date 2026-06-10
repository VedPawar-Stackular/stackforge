"""
Shared LLM client factory and retry utility.

All pipeline modules import from here instead of instantiating AsyncOpenAI
directly. This makes switching providers (Groq -> Anthropic) a one-line change
and ensures the retry pattern is consistent across every LLM call site.
"""

import asyncio
import random
from typing import Any

from openai import AsyncOpenAI, RateLimitError

from config import GROQ_API_KEY, LLM_BASE_URL


def get_llm_client() -> AsyncOpenAI:
    """Return a configured AsyncOpenAI client for the current provider."""
    return AsyncOpenAI(base_url=LLM_BASE_URL, api_key=GROQ_API_KEY)


async def call_with_retry(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    max_tokens: int,
    response_format: dict[str, Any] | None = None,
    retries: int = 4,
) -> str:
    """
    Call the LLM with exponential backoff on rate-limit errors.

    Returns the raw content string from the first choice.
    Raises RateLimitError if all retries are exhausted.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    for attempt in range(retries):
        try:
            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except RateLimitError:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)

    return ""
