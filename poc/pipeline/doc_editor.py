"""
LLM-assisted document editor.

Reads the current .md file for an SDLC topic, sends it plus the user's
plain-English edit instruction to the cheap model, writes the result back,
and returns the updated content.
"""

from openai import AsyncOpenAI

from config import GROQ_API_KEY, LLM_BASE_URL, MODEL_CHEAP
from pipeline.doc_writer import get_doc_path

_client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=GROQ_API_KEY)

_SYSTEM_PROMPT = (
    "You are a technical documentation editor. "
    "You will receive a markdown document followed by an edit instruction. "
    "Apply the edit instruction to the document. "
    "Preserve the existing heading hierarchy and markdown formatting. "
    "Do not add new top-level sections unless the instruction asks for one. "
    "Return ONLY the updated markdown content — no preamble, no explanation, no code fences."
)


async def apply_edit(project_id: str, topic: str, instruction: str) -> str:
    """
    Apply a plain-English edit instruction to the .md file for the given topic.
    Writes the updated content back to disk and returns it.
    Raises FileNotFoundError if the doc has not been generated yet.
    """
    doc_path = get_doc_path(project_id, topic)

    with open(doc_path, encoding="utf-8") as f:
        current_content = f.read()

    user_message = (
        f"Document to edit:\n\n{current_content}\n\n"
        f"Edit instruction: {instruction}"
    )

    response = await _client.chat.completions.create(
        model=MODEL_CHEAP,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    updated = response.choices[0].message.content.strip()

    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(updated)

    return updated
