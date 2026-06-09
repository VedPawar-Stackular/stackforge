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
        response.raise_for_status()
        data = response.json()
    return int(data["id"]), data["url"]


def create_epic(title: str, description: str) -> tuple[int, str]:
    """Create an Epic work item. Returns (work_item_id, work_item_url)."""
    body = [
        {"op": "add", "path": "/fields/System.Title", "value": title},
        {"op": "add", "path": "/fields/System.Description", "value": description},
        {"op": "add", "path": "/fields/System.AreaPath", "value": ADO_PROJECT},
    ]
    return _post_work_item("Epic", body)


def create_user_story(
    title: str,
    description: str,
    acceptance_criteria: list[str],
    story_points: int | None,
    parent_work_item_url: str,
) -> tuple[int, str]:
    """
    Create a User Story work item linked as a child of the given epic.
    Returns (work_item_id, work_item_url).
    """
    # ADO's AcceptanceCriteria field is HTML rich-text
    ac_html = "<ul>" + "".join(f"<li>{ac}</li>" for ac in acceptance_criteria) + "</ul>"

    body = [
        {"op": "add", "path": "/fields/System.Title", "value": title},
        {"op": "add", "path": "/fields/System.Description", "value": description},
        {"op": "add", "path": "/fields/Microsoft.VSTS.Common.AcceptanceCriteria", "value": ac_html},
        {"op": "add", "path": "/fields/System.AreaPath", "value": ADO_PROJECT},
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

    if story_points is not None:
        body.append({
            "op": "add",
            "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
            "value": story_points,
        })

    return _post_work_item("User Story", body)
