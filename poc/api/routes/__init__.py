import uuid as _uuid

from fastapi import HTTPException


def validate_project_id(project_id: str) -> None:
    """Raise HTTP 400 if project_id is not a valid UUID.

    project_id is used to construct filesystem paths (output/{project_id}/).
    Rejecting non-UUID values prevents path traversal attacks.
    """
    try:
        _uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")
