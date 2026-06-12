"""
Multica workspace preparation utility.

Called by the Multica Go daemon during workspace setup to inject Google Stitch
design assets into a Claude Code agent workspace. The daemon calls this as a
subprocess after creating the workspace directory and before spawning the CLI agent.

Usage:
    python workspace_prep.py --project-id <uuid> --workspace-path <path>

Exit codes:
    0  — designs injected (or no designs available, non-fatal)
    1  — fatal error (workspace path doesn't exist, permission denied, etc.)

Environment:
    STITCH_API_KEY  — passed through to .mcp.json for the agent session
"""

import argparse
import json
import logging
import os
import shutil
import sys
import uuid as _uuid_mod

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
_logger = logging.getLogger(__name__)

# poc/ root is the directory containing this script's parent (pipeline/)
_POC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def prep_workspace(project_id: str, workspace_path: str) -> bool:
    """
    Inject Stitch design assets from poc/output/{project_id}/stitch/ into the workspace.

    Returns True if designs were found and injected.
    Returns False if no Stitch designs exist yet (non-fatal — agent starts without them).
    Raises on filesystem errors (fatal).
    """
    # Validate project_id is a UUID to prevent path traversal
    _uuid_mod.UUID(project_id)
    stitch_dir = os.path.join(_POC_ROOT, "output", project_id, "stitch")
    design_md_src = os.path.join(stitch_dir, "DESIGN.md")
    metadata_path = os.path.join(stitch_dir, "metadata.json")

    if not os.path.exists(design_md_src):
        _logger.info(
            "No Stitch designs found for project %s — agent starts without design context",
            project_id,
        )
        return False

    # Load metadata for screen list and Stitch URL
    stitch_url = ""
    screens: list[dict] = []
    if os.path.exists(metadata_path):
        with open(metadata_path, encoding="utf-8") as f:
            meta = json.load(f)
        stitch_url = meta.get("stitch_project_url", "")
        screens = meta.get("screens", [])

    # 1. Copy DESIGN.md into .claude/ — Claude Code loads this natively as design context
    claude_dir = os.path.join(workspace_path, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    shutil.copy2(design_md_src, os.path.join(claude_dir, "DESIGN.md"))
    _logger.info("Injected DESIGN.md → %s/.claude/DESIGN.md", workspace_path)

    # 2. Copy screen HTML files for agent reference
    screens_src = os.path.join(stitch_dir, "screens")
    if os.path.isdir(screens_src):
        screens_dst = os.path.join(workspace_path, "design_screens")
        if os.path.exists(screens_dst):
            shutil.rmtree(screens_dst)
        shutil.copytree(screens_src, screens_dst)
        _logger.info(
            "Copied %d screen file(s) → %s/design_screens/",
            len(screens),
            workspace_path,
        )

    # 3. Append design reference section to issue_context.md
    issue_context_path = os.path.join(workspace_path, "issue_context.md")
    design_section = _build_design_section(stitch_url, screens)
    mode = "a" if os.path.exists(issue_context_path) else "w"
    with open(issue_context_path, mode, encoding="utf-8") as f:
        f.write(design_section)
    _logger.info("Appended design reference to issue_context.md")

    # 4. Write .mcp.json so the agent can call Stitch MCP tools during coding
    stitch_api_key = os.environ.get("STITCH_API_KEY", "")
    mcp_config = {
        "mcpServers": {
            "stitch": {
                "command": "npx",
                "args": ["--yes", "stitch-mcp-server"],
                "env": {"STITCH_API_KEY": stitch_api_key},
            }
        }
    }
    mcp_path = os.path.join(workspace_path, ".mcp.json")
    with open(mcp_path, "w", encoding="utf-8") as f:
        json.dump(mcp_config, f, indent=2)
    _logger.info("Wrote .mcp.json with Stitch MCP server config")

    return True


def _build_design_section(stitch_url: str, screens: list[dict]) -> str:
    lines = [
        "\n\n---\n\n## Design Reference\n\n",
        "Google Stitch has generated high-fidelity UI screens for this project. "
        "The design system is automatically loaded from `.claude/DESIGN.md`.\n",
    ]
    if stitch_url:
        lines.append(f"\nStitch project: {stitch_url}\n")
    if screens:
        lines.append("\nAvailable screens (HTML files in `design_screens/`):\n")
        for s in screens:
            lines.append(f"- `design_screens/{s['name']}.html` — {s['label']}\n")
    lines.append(
        "\nUse Stitch MCP tools (`stitch_*`) during development to fetch the latest "
        "design tokens or compare your implementation against the generated screens.\n"
    )
    return "".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inject Stitch design assets into a Multica Claude Code workspace"
    )
    parser.add_argument("--project-id", required=True, help="StackForge project UUID")
    parser.add_argument(
        "--workspace-path",
        required=True,
        help="Absolute path to the Multica workspace directory",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.workspace_path):
        _logger.error("Workspace path does not exist: %s", args.workspace_path)
        sys.exit(1)

    try:
        prep_workspace(args.project_id, args.workspace_path)
        sys.exit(0)
    except Exception as exc:
        _logger.error("workspace_prep failed: %s", exc)
        sys.exit(1)
