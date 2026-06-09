# Multica Go Daemon — Stitch Design Integration

This document describes the change required in the Multica Go daemon to inject
Google Stitch design assets into Stage 4 coding agent workspaces.

## What the Python side provides

After a StackForge project runs the Stitch generation step (via the UI or API),
design assets are written to:

```
poc/output/{project_id}/stitch/
├── DESIGN.md           — design tokens + rationale (Claude Code reads natively)
├── metadata.json       — stitch_project_id, stitch_project_url, screen list
└── screens/
    ├── patient_join.html
    └── ...
```

The `poc/pipeline/workspace_prep.py` script copies these into a Multica workspace:

```
{workspace}/
├── .claude/
│   └── DESIGN.md       ← Claude Code auto-loads this as design system context
├── design_screens/
│   ├── patient_join.html
│   └── ...
├── issue_context.md    ← design reference section appended
└── .mcp.json           ← configures Stitch MCP server for the agent session
```

## Required change in the Go daemon

Add this block to the workspace prep step, **between `LoadAgentSkills` and `BuildPrompt`**:

```go
// Inject StackForge Stitch design assets if available (non-fatal)
stackforgeRoot := cfg.StackforgeRoot // path to the poc/ directory, e.g. "/opt/stackforge/poc"
if stackforgeRoot != "" {
    cmd := exec.Command(
        "python",
        filepath.Join(stackforgeRoot, "pipeline", "workspace_prep.py"),
        "--project-id", task.ProjectID,
        "--workspace-path", workspacePath,
    )
    cmd.Env = append(os.Environ(), "STITCH_API_KEY="+cfg.StitchAPIKey)
    if err := cmd.Run(); err != nil {
        log.Printf("[warn] workspace_prep failed for project %s: %v", task.ProjectID, err)
        // Non-fatal: agent starts without design context
    }
}
```

## Config values to add

In the daemon config struct / environment:

| Key | Description |
|-----|-------------|
| `STACKFORGE_ROOT` | Absolute path to the `poc/` directory on the daemon host |
| `STITCH_API_KEY` | Google Stitch API key — passed through to `.mcp.json` so the agent can call Stitch MCP tools during coding |

## What the agent gets

After `workspace_prep.py` runs, the Claude Code agent starting in the workspace will:

1. **Auto-load DESIGN.md** — Claude Code natively reads `.claude/DESIGN.md` and applies
   design tokens (colors, typography, spacing) to all generated code without any
   explicit instruction.

2. **Reference screen files** — `design_screens/{name}.html` are available on disk.
   The agent can read these to understand the intended layout for each screen.

3. **Call Stitch MCP tools** — The `.mcp.json` file configures the Stitch MCP server.
   During coding, the agent can call tools like `get_screen_code`, `get_design_tokens`,
   or `get_screen_image` to fetch the latest design state from Stitch.

## Non-blocking design

`workspace_prep.py` exits with code 0 in all cases — both when designs are injected
and when they don't exist yet (e.g. Stitch generation hasn't been run for the project).
The daemon should treat a non-zero exit as a warning log, not a task failure.

This means Stage 4 agents always start regardless of whether Stitch integration is
configured. Design context is "best-effort enrichment", not a hard dependency.
