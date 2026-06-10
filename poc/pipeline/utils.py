"""Shared pipeline utilities — small helpers used across multiple pipeline modules."""

from db import DB


def get_project_name(project_id: str) -> str:
    """Return the project name for the given ID, falling back to the ID if not found."""
    with DB() as db:
        row = db.fetch_one("SELECT name FROM projects WHERE id = %s", (project_id,))
    return row["name"] if row else project_id
