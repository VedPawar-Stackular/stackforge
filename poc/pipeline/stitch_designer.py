"""
Google Stitch design generation pipeline.

Reads design.md for a project, uses the cheap model to extract screen
descriptions, then calls the Google Stitch MCP server to generate
high-fidelity UI screens.

Outputs to poc/output/{project_id}/stitch/:
    DESIGN.md       — design tokens + rationale (Claude Code reads natively)
    metadata.json   — stitch project id, url, screen list, timestamp
    screens/        — one HTML file per generated screen (if MCP succeeds)

Requirements:
    - STITCH_API_KEY in poc/.env
    - Node.js installed
    - npm package stitch-mcp-server available via npx
    - Python mcp>=1.0.0 package

MCP tool inventory (stitch-mcp-server v1.x):
    create_project(title)           -- creates project, returns {name: "projects/{id}", ...}
    generate_screen(projectId, prompt) -- generates a screen; returns screenId
    get_screen_code(projectId, screenId) -- returns HTML download URL + inline HTML
    list_projects()                 -- lists project IDs
    (no get_design_tokens — DESIGN.md is generated from requirements by cheap model)
"""

import asyncio
import json
import logging
import os
import random

from openai import AsyncOpenAI, RateLimitError

from config import GROQ_API_KEY, LLM_BASE_URL, MODEL_CHEAP, STITCH_API_KEY
from db import DB
from pipeline.doc_writer import get_doc_path, get_output_dir

_logger = logging.getLogger(__name__)
_client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=GROQ_API_KEY)

# ─── Screen extraction ───────────────────────────────────────────────────────

_EXTRACT_SYSTEM = (
    "You are a UI/UX analyst. Given a set of design requirements, identify the distinct "
    "application screens or views that need to be built.\n\n"
    "For each screen:\n"
    "- Give it a short snake_case name (e.g. 'patient_join', 'provider_dashboard')\n"
    "- Give it a human-readable label (e.g. 'Patient Join Screen')\n"
    "- Set device to 'mobile' or 'desktop' based on who uses it\n"
    "- Write a 2-3 sentence Stitch prompt describing the screen's purpose, key UI elements, "
    "and visual style\n\n"
    "Return ONLY valid JSON matching this schema:\n"
    '{"screens": [{"name": "string", "label": "string", "device": "mobile|desktop", "prompt": "string"}]}\n\n'
    "Extract 3-6 screens maximum. Focus on the most important user-facing screens."
)

_DESIGN_MD_SYSTEM = (
    "You are a design systems engineer. Given a list of UI screens and design requirements, "
    "write a DESIGN.md file in the following format:\n\n"
    "---\n"
    "# YAML front matter: approximate design tokens\n"
    "colors:\n"
    "  primary: \"#hex\"\n"
    "  ...\n"
    "typography:\n"
    "  base-size: \"16px\"\n"
    "  ...\n"
    "---\n\n"
    "# Project Design System\n\n"
    "## Overview\n...\n\n"
    "## Screens\n...\n\n"
    "## Design Principles\n...\n\n"
    "Infer sensible design tokens from the requirements context (e.g. healthcare = clean/professional). "
    "Return ONLY the DESIGN.md markdown content — no preamble, no code fences."
)


async def extract_screens(design_md_content: str) -> list[dict]:
    """
    Use cheap model to extract screen names + Stitch prompts from design.md.
    Returns list of {name, label, device, prompt}.
    """
    for attempt in range(4):
        try:
            response = await _client.chat.completions.create(
                model=MODEL_CHEAP,
                max_tokens=800,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _EXTRACT_SYSTEM},
                    {"role": "user", "content": f"Design requirements:\n\n{design_md_content}"},
                ],
            )
            data = json.loads(response.choices[0].message.content)
            screens = data.get("screens", [])
            if isinstance(screens, list) and screens:
                return screens
        except RateLimitError:
            if attempt == 3:
                raise
            await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
        except (json.JSONDecodeError, KeyError) as e:
            _logger.warning("Screen extraction parse error (attempt %d): %s", attempt + 1, e)
    return []


async def _generate_design_md(project_name: str, screens: list[dict], design_md_content: str) -> str:
    """
    Generate a DESIGN.md file using the cheap model.
    Used as a fallback when Stitch doesn't provide design tokens directly.
    """
    screen_list = "\n".join(f"- {s['label']} ({s['name']}, {s.get('device', 'mobile')})" for s in screens)
    user_msg = (
        f"Project: {project_name}\n\n"
        f"Screens:\n{screen_list}\n\n"
        f"Design requirements:\n{design_md_content[:2000]}"
    )
    try:
        response = await _client.chat.completions.create(
            model=MODEL_CHEAP,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": _DESIGN_MD_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        _logger.warning("DESIGN.md generation failed: %s", e)
        return _fallback_design_md(project_name, screens)


def _fallback_design_md(project_name: str, screens: list[dict]) -> str:
    """Minimal DESIGN.md when both Stitch and LLM generation fail."""
    screen_lines = "\n".join(f"- {s['label']} (`{s['name']}.html`)" for s in screens)
    return (
        "---\n"
        "colors:\n"
        "  primary: \"#2563eb\"\n"
        "  background: \"#ffffff\"\n"
        "  surface: \"#f8fafc\"\n"
        "typography:\n"
        "  base-size: \"16px\"\n"
        "  font-family: \"Inter, system-ui, sans-serif\"\n"
        "spacing:\n"
        "  small: \"8px\"\n"
        "  medium: \"16px\"\n"
        "  large: \"24px\"\n"
        "---\n\n"
        f"# {project_name} — Design System\n\n"
        "> Generated by StackForge. Open the Stitch project to customise and export final tokens.\n\n"
        "## Screens\n\n"
        f"{screen_lines}\n\n"
        "## Design Principles\n\n"
        "- Clean, professional medical UI\n"
        "- Mobile-first for patient-facing screens\n"
        "- Desktop-optimised for provider-facing screens\n"
        "- WCAG AA accessibility compliance\n"
    )


# ─── Stitch MCP generation ───────────────────────────────────────────────────

async def generate_stitch_designs(project_id: str, project_name: str, screens: list[dict],
                                   design_md_content: str) -> str:
    """
    Calls Stitch MCP to create a project and attempt screen generation.
    Falls back gracefully when screen generation fails (known npm package bug).

    Returns the absolute path of the stitch output directory.
    """
    if not STITCH_API_KEY:
        raise EnvironmentError(
            "STITCH_API_KEY is not set. Add it to poc/.env to enable Stitch integration."
        )

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as e:
        raise ImportError("Install the mcp package: pip install mcp>=1.0.0") from e

    output_dir = os.path.join(get_output_dir(project_id), "stitch")
    screens_dir = os.path.join(output_dir, "screens")
    os.makedirs(screens_dir, exist_ok=True)

    server_params = StdioServerParameters(
        command="npx",
        args=["--yes", "stitch-mcp-server"],
        env={**os.environ, "STITCH_API_KEY": STITCH_API_KEY},
    )

    stitch_project_id = ""
    stitch_project_url = ""
    screen_meta: list[dict] = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. Create Stitch project — uses 'title' param (not 'name')
            create_result = await session.call_tool("create_project", {"title": project_name})
            create_data = _parse_tool_result(create_result, "create_project")

            # Resource name is "projects/{numeric_id}" — extract the numeric part
            resource_name = create_data.get("name", "")
            stitch_project_id = resource_name.split("/")[-1] if "/" in resource_name else resource_name
            stitch_project_url = (
                f"https://stitch.withgoogle.com/projects/{stitch_project_id}"
                if stitch_project_id
                else "https://stitch.withgoogle.com/"
            )
            _logger.info("Created Stitch project '%s' → ID %s", project_name, stitch_project_id)

            # 2. Generate screens — graceful fallback if npm package has bugs
            for screen in screens:
                try:
                    gen_result = await session.call_tool(
                        "generate_screen",
                        {
                            "projectId": stitch_project_id,
                            "prompt": screen["prompt"],
                        },
                    )
                    screen_data = _parse_tool_result(gen_result, "generate_screen")
                    screen_id = (
                        screen_data.get("screenId")
                        or screen_data.get("id")
                        or screen_data.get("name", "").split("/")[-1]
                    )

                    if screen_id:
                        # 3. Fetch HTML for this screen
                        try:
                            code_result = await session.call_tool(
                                "get_screen_code",
                                {"projectId": stitch_project_id, "screenId": screen_id},
                            )
                            code_data = _parse_tool_result(code_result, "get_screen_code")
                            html_content = (
                                code_data.get("html")
                                or code_data.get("code")
                                or code_data.get("content", "")
                            )
                            if html_content and isinstance(html_content, str):
                                html_filename = f"{screen['name']}.html"
                                with open(os.path.join(screens_dir, html_filename), "w", encoding="utf-8") as f:
                                    f.write(html_content)
                                screen_meta.append({
                                    "name": screen["name"],
                                    "label": screen["label"],
                                    "stitch_id": screen_id,
                                    "html_path": f"screens/{html_filename}",
                                })
                                _logger.info("Saved screen '%s'", screen["name"])
                        except RuntimeError as e:
                            _logger.warning("get_screen_code failed for '%s': %s", screen["name"], e)
                            screen_meta.append({
                                "name": screen["name"],
                                "label": screen["label"],
                                "stitch_id": screen_id,
                                "html_path": None,
                            })

                except RuntimeError as e:
                    # Known npm package bug: "Cannot read properties of undefined (reading 'screens')"
                    # Stitch project was still created; screen must be added manually via Stitch UI
                    _logger.warning(
                        "generate_screen failed for '%s' (npm package bug): %s — "
                        "add this screen manually in the Stitch web UI",
                        screen["name"], e,
                    )
                    screen_meta.append({
                        "name": screen["name"],
                        "label": screen["label"],
                        "stitch_id": None,
                        "html_path": None,
                        "note": "Add manually in Stitch UI",
                    })

    # 4. Generate DESIGN.md (no Stitch API endpoint for this — generated by cheap model)
    _logger.info("Generating DESIGN.md from requirements...")
    design_md_text = await _generate_design_md(project_name, screens, design_md_content)
    with open(os.path.join(output_dir, "DESIGN.md"), "w", encoding="utf-8") as f:
        f.write(design_md_text)

    # 5. Write metadata.json
    from datetime import datetime, timezone
    metadata = {
        "stitch_project_id": stitch_project_id,
        "stitch_project_url": stitch_project_url,
        "screens": screen_meta,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Stitch project created. If screens show 'Add manually in Stitch UI', "
            "open the project in Stitch and generate screens there."
        ),
    }
    with open(os.path.join(output_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # 6. Persist stitch columns in DB
    _save_stitch_to_db(project_id, stitch_project_id, stitch_project_url)

    _logger.info(
        "Stitch output written to %s | project_id=%s | screens=%d",
        output_dir, stitch_project_id, len(screen_meta),
    )
    return output_dir


def _parse_tool_result(result, tool_name: str = "") -> dict:
    """
    Extract the dict payload from an MCP CallToolResult.

    Raises RuntimeError if the server returned an MCP protocol error or
    a JavaScript error from the npm package so callers get clear failures.
    """
    if hasattr(result, "isError") and result.isError:
        text = ""
        if hasattr(result, "content") and result.content:
            text = getattr(result.content[0], "text", "")
        raise RuntimeError(f"Stitch MCP tool '{tool_name}' error: {text}")

    if hasattr(result, "content") and result.content:
        first = result.content[0]
        raw_text = getattr(first, "text", "") or ""

        # Detect MCP protocol-level errors embedded in text
        if raw_text.startswith("MCP error") or raw_text.startswith("Error "):
            raise RuntimeError(f"Stitch MCP tool '{tool_name}' error: {raw_text}")

        if raw_text:
            # The response often has a human-readable header before the JSON block
            try:
                json_start = raw_text.index("{")
                parsed = json.loads(raw_text[json_start:])
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, json.JSONDecodeError):
                pass
            return {"content": raw_text}
    return {}


def _save_stitch_to_db(project_id: str, stitch_project_id: str, stitch_project_url: str) -> None:
    with DB() as db:
        db.execute(
            "UPDATE projects SET stitch_project_id = %s, stitch_project_url = %s WHERE id = %s",
            (stitch_project_id, stitch_project_url, project_id),
        )


# ─── Public entry point ──────────────────────────────────────────────────────

async def generate_for_project(project_id: str) -> str:
    """
    Reads design.md, extracts screens, generates the Stitch project.
    Returns the absolute path of poc/output/{project_id}/stitch/.
    """
    design_md_path = get_doc_path(project_id, "design")
    if not os.path.exists(design_md_path):
        raise FileNotFoundError(
            f"design.md not found for project {project_id}. Run the ingestion pipeline first."
        )

    with open(design_md_path, encoding="utf-8") as f:
        design_content = f.read()

    project_name = _get_project_name(project_id)

    screens = await extract_screens(design_content)
    if not screens:
        raise ValueError(
            "Could not extract any screens from design.md. "
            "Check that the project has design requirements."
        )

    _logger.info(
        "Extracted %d screens for project %s: %s",
        len(screens), project_id, [s["name"] for s in screens],
    )
    return await generate_stitch_designs(project_id, project_name, screens, design_content)


def _get_project_name(project_id: str) -> str:
    with DB() as db:
        row = db.fetch_one("SELECT name FROM projects WHERE id = %s", (project_id,))
    return row["name"] if row else project_id
