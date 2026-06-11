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


def extract_usage(response: Any) -> tuple[int, int, int]:
    """Return (input_tokens, output_tokens, thinking_tokens) from a chat response.

    Defensive by design — every field is read via getattr with a zero default so a
    provider that omits `.usage` (or omits a field) never aborts a generation step
    over telemetry. `thinking_tokens` comes from `completion_tokens_details.
    reasoning_tokens`, which reasoning models populate and the current Groq llama
    models leave absent (→ 0). It auto-populates if a reasoning model is wired later.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0, 0
    details = getattr(usage, "completion_tokens_details", None)
    thinking = getattr(details, "reasoning_tokens", 0) or 0
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    return input_tokens, output_tokens, thinking


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
