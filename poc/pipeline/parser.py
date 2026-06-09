"""
Document parser: converts uploaded file bytes into plain text.

Supports: PDF (pdfplumber), DOCX (python-docx), TXT (direct).
"""

import re


def parse(file_bytes: bytes, file_type: str) -> str:
    """Return plain UTF-8 text from file bytes. file_type: pdf | docx | txt."""
    if file_type == "pdf":
        return _parse_pdf(file_bytes)
    elif file_type == "docx":
        return _parse_docx(file_bytes)
    elif file_type == "txt":
        return file_bytes.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


def _parse_pdf(data: bytes) -> str:
    import io
    import pdfplumber

    text_parts = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return _clean(_join(text_parts))


def _parse_docx(data: bytes) -> str:
    import io
    from docx import Document

    doc = Document(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return _clean(_join(paragraphs))


def _join(parts: list[str]) -> str:
    return "\n\n".join(parts)


def _clean(text: str) -> str:
    # Collapse runs of blank lines to at most two
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()
