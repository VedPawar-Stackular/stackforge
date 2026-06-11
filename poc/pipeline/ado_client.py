"""
Azure DevOps REST API client — synchronous.

Creates Epic and User Story work items via ADO REST API v7.1.
Uses the Agile process template work item types ($Epic, $User Story).

Authentication: HTTP Basic with base64(":PAT") — no username, just a colon
prepended to the PAT, then base64-encoded.

Epic → User Story hierarchy is created via System.LinkTypes.Hierarchy-Reverse
(the child points to its parent; ADO's naming is from the child's perspective).
"""

import base64
import html
import json

import httpx

from config import ADO_API_VERSION, ADO_ORG, ADO_PAT, ADO_PROJECT


def _auth_header() -> str:
    token = base64.b64encode(f":{ADO_PAT}".encode()).decode()
    return f"Basic {token}"


def _headers() -> dict:
    return {
        "Authorization": _auth_header(),
        "Content-Type": "application/json-patch+json",
    }


def _base_url() -> str:
    return f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/wit"


def _post_work_item(work_item_type: str, body: list[dict]) -> tuple[int, str]:
    """POST a new work item. Returns (id, url)."""
    url = f"{_base_url()}/workitems/${work_item_type}?api-version={ADO_API_VERSION}"
    with httpx.Client(timeout=30) as client:
        response = client.post(url, headers=_headers(), content=json.dumps(body))
        if not response.is_success:
            # Include ADO's response body so the actual reason is visible in the UI
            try:
                ado_error = response.json().get("message", response.text)
            except Exception:
                ado_error = response.text
            raise RuntimeError(
                f"ADO {response.status_code} creating {work_item_type}: {ado_error}"
            )
        data = response.json()
    return int(data["id"]), data["url"]


def ensure_area_path(area_name: str) -> str:
    """
    Create a child area node under the root ADO project area if it doesn't exist.
    Idempotent — 409 Conflict (already exists) is treated as success.
    Returns the full area path string: "{ADO_PROJECT}\\{area_name}".
    """
    url = (
        f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/wit/classificationnodes/areas"
        f"?api-version={ADO_API_VERSION}"
    )
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30) as client:
        response = client.post(url, headers=headers, content=json.dumps({"name": area_name}))
        if response.status_code not in (200, 201, 409):
            response.raise_for_status()
    return f"{ADO_PROJECT}\\{area_name}"


def create_epic(title: str, description: str, area_path: str = "", tags: str = "") -> tuple[int, str]:
    """
    Create an Epic work item. Returns (work_item_id, work_item_url).
    area_path: if empty, omitted from request and ADO uses project default.
    """
    body = [
        {"op": "add", "path": "/fields/System.Title", "value": title},
        # html.escape() prevents LLM-generated content with <, >, & from
        # breaking ADO's HTML rich-text renderer.
        {"op": "add", "path": "/fields/System.Description", "value": html.escape(description)},
    ]
    if area_path:
        body.append({"op": "add", "path": "/fields/System.AreaPath", "value": area_path})
    if tags:
        body.append({"op": "add", "path": "/fields/System.Tags", "value": tags})
    return _post_work_item("Epic", body)


def create_user_story(
    title: str,
    description: str,
    acceptance_criteria: list[str],
    story_points: int | None,
    parent_work_item_url: str,
    area_path: str = "",
    tags: str = "",
) -> tuple[int, str]:
    """
    Create a User Story work item linked as a child of the given epic.
    Returns (work_item_id, work_item_url).
    area_path: if empty, omitted and ADO uses project default.
    """
    # ADO's AcceptanceCriteria field is HTML rich-text.
    # html.escape() prevents AI-generated content from injecting script tags.
    ac_html = "<ul>" + "".join(f"<li>{html.escape(ac)}</li>" for ac in acceptance_criteria) + "</ul>"

    body = [
        {"op": "add", "path": "/fields/System.Title", "value": title},
        {"op": "add", "path": "/fields/System.Description", "value": html.escape(description)},
        {"op": "add", "path": "/fields/Microsoft.VSTS.Common.AcceptanceCriteria", "value": ac_html},
        # Link to parent epic: Hierarchy-Reverse = child→parent direction
        {
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "System.LinkTypes.Hierarchy-Reverse",
                "url": parent_work_item_url,
                "attributes": {"comment": ""},
            },
        },
    ]

    if area_path:
        body.append({"op": "add", "path": "/fields/System.AreaPath", "value": area_path})
    if tags:
        body.append({"op": "add", "path": "/fields/System.Tags", "value": tags})
    if story_points is not None:
        body.append({
            "op": "add",
            "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
            "value": story_points,
        })

    return _post_work_item("User Story", body)
