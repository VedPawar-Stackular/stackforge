"""
Bulk-delete ADO work items that were pushed from StackForge.

Run from the poc/ directory:
    python scripts/ado_bulk_delete.py
    python scripts/ado_bulk_delete.py --project-id <uuid>
    python scripts/ado_bulk_delete.py --dry-run
    python scripts/ado_bulk_delete.py --clear-db

Options:
    --project-id  Only delete items from this StackForge project UUID.
                  Omit to delete ALL pushed items across all projects.
    --dry-run     Print what would be deleted without actually deleting.
    --clear-db    After deletion, clear ado_work_item_id from DB so
                  items can be re-pushed cleanly.
"""

import argparse
import base64
import logging
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ADO_API_VERSION, ADO_ORG, ADO_PAT, ADO_PROJECT
from db import DB

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
_log = logging.getLogger(__name__)


def _auth_header() -> str:
    token = base64.b64encode(f":{ADO_PAT}".encode()).decode()
    return f"Basic {token}"


def _delete_work_item(item_id: int, dry_run: bool) -> bool:
    if dry_run:
        _log.info("DRY RUN — would delete ADO #%d", item_id)
        return True
    url = (
        f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}"
        f"/_apis/wit/workitems/{item_id}?destroy=true&api-version={ADO_API_VERSION}"
    )
    with httpx.Client(timeout=30) as client:
        r = client.delete(url, headers={"Authorization": _auth_header()})
    if r.status_code in (200, 204):
        _log.info("Deleted ADO #%d", item_id)
        return True
    if r.status_code == 404:
        _log.warning("ADO #%d not found (already deleted)", item_id)
        return True
    try:
        msg = r.json().get("message", r.text[:200])
    except Exception:
        msg = r.text[:200]
    _log.error("Failed to delete ADO #%d: %s — %s", item_id, r.status_code, msg)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete ADO work items pushed from StackForge")
    parser.add_argument("--project-id", help="StackForge project UUID (omit = all projects)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--clear-db",
        action="store_true",
        help="Clear ado_work_item_id from DB after deletion (enables re-push)",
    )
    args = parser.parse_args()

    if not all([ADO_ORG, ADO_PROJECT, ADO_PAT]):
        _log.error("ADO_ORG, ADO_PROJECT, ADO_PAT must be set in poc/.env")
        sys.exit(1)

    with DB() as db:
        if args.project_id:
            epics = db.fetch_all(
                "SELECT id, ado_work_item_id, title FROM epics"
                " WHERE project_id = %s AND ado_work_item_id IS NOT NULL",
                (args.project_id,),
            )
            stories = db.fetch_all(
                "SELECT id, ado_work_item_id, title FROM user_stories"
                " WHERE project_id = %s AND ado_work_item_id IS NOT NULL",
                (args.project_id,),
            )
        else:
            epics = db.fetch_all(
                "SELECT id, ado_work_item_id, title FROM epics WHERE ado_work_item_id IS NOT NULL"
            )
            stories = db.fetch_all(
                "SELECT id, ado_work_item_id, title FROM user_stories WHERE ado_work_item_id IS NOT NULL"
            )

    total = len(epics) + len(stories)
    if total == 0:
        _log.info("No pushed ADO work items found in DB — nothing to delete.")
        return

    _log.info("Found %d epics + %d user stories to delete.", len(epics), len(stories))
    for e in epics:
        _log.info("  Epic  ADO #%s — %s", e["ado_work_item_id"], e["title"])
    for s in stories:
        _log.info("  Story ADO #%s — %s", s["ado_work_item_id"], s["title"])

    if not args.dry_run:
        confirm = input(f"\nPermanently delete {total} work items from ADO? [y/N] ").strip().lower()
        if confirm != "y":
            _log.info("Aborted.")
            return

    deleted_story_ids: list[str] = []
    deleted_epic_ids: list[str] = []

    # Delete stories before epics (children first avoids orphan warnings)
    for s in stories:
        if _delete_work_item(int(s["ado_work_item_id"]), args.dry_run):
            deleted_story_ids.append(str(s["id"]))

    for e in epics:
        if _delete_work_item(int(e["ado_work_item_id"]), args.dry_run):
            deleted_epic_ids.append(str(e["id"]))

    _log.info(
        "Done. Deleted %d/%d stories, %d/%d epics.",
        len(deleted_story_ids),
        len(stories),
        len(deleted_epic_ids),
        len(epics),
    )

    if args.clear_db and not args.dry_run and (deleted_story_ids or deleted_epic_ids):
        with DB() as db:
            if deleted_story_ids:
                placeholders = ",".join(["%s"] * len(deleted_story_ids))
                db.execute(
                    "UPDATE user_stories SET ado_work_item_id = NULL, ado_work_item_url = NULL"
                    " WHERE id IN (" + placeholders + ")",
                    tuple(deleted_story_ids),
                )
            if deleted_epic_ids:
                placeholders = ",".join(["%s"] * len(deleted_epic_ids))
                db.execute(
                    "UPDATE epics SET ado_work_item_id = NULL, ado_work_item_url = NULL"
                    " WHERE id IN (" + placeholders + ")",
                    tuple(deleted_epic_ids),
                )
        _log.info("Cleared DB — items can be re-pushed.")


if __name__ == "__main__":
    main()
