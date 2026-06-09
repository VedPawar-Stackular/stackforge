"""
Stitch MCP diagnostic — lists available tools and tests create_project.

Run from c:\\StackForge\\poc\\ in a terminal where `npx` is available:
    python debug_stitch.py

This tells you exactly which tool names the installed stitch-mcp-server exposes
so stitch_designer.py can be updated with the correct names.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

STITCH_API_KEY = os.environ.get("STITCH_API_KEY", "")

if not STITCH_API_KEY:
    print("ERROR: STITCH_API_KEY not set in poc/.env")
    sys.exit(1)


async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command="npx",
        args=["--yes", "stitch-mcp-server"],
        env={**os.environ, "STITCH_API_KEY": STITCH_API_KEY},
    )

    print("Starting stitch-mcp-server via npx (first run downloads the package)...")
    print()

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. List all available tools
            tools_response = await session.list_tools()
            tools = tools_response.tools if hasattr(tools_response, "tools") else []

            print(f"=== Available tools ({len(tools)}) ===")
            for t in tools:
                print(f"  {t.name}")
                if hasattr(t, "description") and t.description:
                    desc = t.description[:80].replace("\n", " ")
                    print(f"    {desc}")
            print()

            if not tools:
                print("No tools found. The MCP server may have started but returned no tools.")
                return

            # 2. Look for project creation tools
            tool_names = {t.name for t in tools}
            create_candidates = [n for n in tool_names if "create" in n.lower() or "project" in n.lower()]
            print(f"=== Project/create related tools: {create_candidates} ===")
            print()

            # 3. Test create_project or closest match
            create_tool = None
            for candidate in ["create_project", "createProject", "new_project", "create"]:
                if candidate in tool_names:
                    create_tool = candidate
                    break
            if not create_tool and create_candidates:
                create_tool = create_candidates[0]

            # 3. Full flow test: create_project → generate_and_fetch_code
            print("=== Testing full flow: create_project(title=...) -> generate_and_fetch_code ===")

            # create_project with correct 'title' param
            cp_result = await session.call_tool("create_project", {"title": "StackForge Schema Test"})
            cp_text = getattr(cp_result.content[0], "text", "") if cp_result.content else ""
            print("create_project raw:", cp_text[:600])

            # Extract project name/id
            import json as _json
            project_id_to_use = ""
            try:
                lines = [l for l in cp_text.split("\n") if l.strip().startswith("{")]
                json_start = cp_text.index("{")
                cp_data = _json.loads(cp_text[json_start:])
                project_id_to_use = cp_data.get("name", "")
                print("Extracted project name:", project_id_to_use)
            except Exception as e:
                print("Could not parse project id:", e)

            if project_id_to_use and "generate_and_fetch_code" in tool_names:
                print()
                print(f"=== Testing generate_and_fetch_code(projectId={project_id_to_use!r}, prompt='...') ===")
                gfc_result = await session.call_tool(
                    "generate_and_fetch_code",
                    {"projectId": project_id_to_use, "prompt": "Simple patient login screen, mobile, clean medical UI"},
                )
                gfc_text = getattr(gfc_result.content[0], "text", "") if gfc_result.content else ""
                print("generate_and_fetch_code raw (first 600):", gfc_text[:600])

            # 4. Show schema for token/design-related tools
            design_tools = [n for n in tool_names if any(
                kw in n.lower() for kw in ["token", "design", "export", "screen", "generate"]
            )]
            print()
            print(f"=== Design/screen/token related tools: {design_tools} ===")


asyncio.run(main())
