"""
Text chunker: splits plain text into ~250-300 word chunks at paragraph
boundaries with a ~35-word tail overlap between adjacent chunks.

Overlap ensures requirements that span a chunk boundary appear in full
context in at least one chunk's summary (sliding window approach).
"""

import re
from config import CHUNK_TARGET_WORDS, CHUNK_OVERLAP_WORDS


def chunk(text: str) -> list[str]:
    """Return list of text chunks with overlap. Each core chunk is ~250-300 words."""
    paragraphs = _split_paragraphs(text)
    base_chunks = _merge_to_chunks(paragraphs, CHUNK_TARGET_WORDS)
    return _add_overlap(base_chunks, CHUNK_OVERLAP_WORDS)


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; fall back to sentence boundaries for long paragraphs."""
    raw = re.split(r"\n{2,}", text.strip())
    result = []
    for para in raw:
        para = para.strip()
        if not para:
            continue
        words = para.split()
        if len(words) <= CHUNK_TARGET_WORDS * 1.5:
            result.append(para)
        else:
            # Long paragraph: split at sentence endings
            sentences = re.split(r"(?<=[.!?])\s+", para)
            result.extend(s for s in sentences if s.strip())
    return result


def _merge_to_chunks(paragraphs: list[str], target: int) -> list[str]:
    """Merge short paragraphs together until each chunk hits ~target words."""
    chunks: list[str] = []
    current_parts: list[str] = []
    current_words = 0

    for para in paragraphs:
        word_count = len(para.split())
        if current_words + word_count > target * 1.2 and current_parts:
            chunks.append("\n\n".join(current_parts))
            current_parts = [para]
            current_words = word_count
        else:
            current_parts.append(para)
            current_words += word_count

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return [c for c in chunks if c.strip()]


def _add_overlap(chunks: list[str], overlap_words: int) -> list[str]:
    """
    Prepend the last `overlap_words` words of chunk[i-1] to chunk[i].
    Gives the summariser cross-boundary context without re-running
    the chunking algorithm on an already-merged text.
    """
    if overlap_words <= 0 or len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev_words = chunks[i - 1].split()
        tail = " ".join(prev_words[-overlap_words:])
        result.append(f"[...] {tail}\n\n{chunks[i]}")
    return result
