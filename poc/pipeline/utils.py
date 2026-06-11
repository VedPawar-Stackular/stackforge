"""Shared pipeline utilities — small helpers used across multiple pipeline modules."""

from db import DB


def get_project_name(project_id: str) -> str:
    """Return the project name for the given ID, falling back to the ID if not found."""
    with DB() as db:
        row = db.fetch_one("SELECT name FROM projects WHERE id = %s", (project_id,))
    return row["name"] if row else project_id


def text_array_literal(items: list[str]) -> str:
    """Convert a Python list to a PostgreSQL TEXT[] literal string for pg8000.

    pg8000 cannot auto-cast Python lists to TEXT[] columns, so we build
    the literal manually: {"item1","item2",...}
    """
    if not items:
        return "{}"
    escaped = []
    for item in items:
        item = item.replace("\\", "\\\\").replace('"', '\\"')
        item = item.replace("\n", " ").replace("\r", "")
        escaped.append(f'"{item}"')
    return "{" + ",".join(escaped) + "}"
