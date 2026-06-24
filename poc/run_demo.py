"""
CLI demo runner for StackForge Stage 1.

Usage (from c:\\StackForge\\poc):
    python run_demo.py
    python run_demo.py --docs ..\\sample_client_docs\\SOW_CareFlow_v1.4.docx
    python run_demo.py --client "CareFlow" --project "CareFlow Platform 2026" --docs <file1> <file2>
"""

import argparse
import asyncio
import os
import sys
import uuid

# Force UTF-8 on Windows (default terminal uses cp1252 which can't encode emoji/✓)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from db import DB
from pipeline.runner import ingest_document

# legacy_windows=False prevents cp1252 encoding errors on Windows terminals
console = Console(legacy_windows=False)

DEFAULT_DOCS = [
    r"..\sample_client_docs\BRD_MediBook_Apex_Health.docx",
    r"..\sample_client_docs\SOW_MediBook_Apex_Health.docx",
    r"..\sample_client_docs\Technical_Spec_MediBook.pdf",
    r"..\sample_client_docs\Discovery_Call_Transcript_Dec15.txt",
    r"..\sample_client_docs\Client_Email_Jan12.txt",
]


# ─── DB helpers ──────────────────────────────────────────────────────────────

def create_project(client_name: str, project_name: str) -> str:
    with DB() as db:
        row = db.fetch_one("SELECT id FROM clients WHERE name = %s", (client_name,))
        if row:
            client_id = str(row["id"])
        else:
            client_id = str(uuid.uuid4())
            db.execute("INSERT INTO clients (id, name) VALUES (%s, %s)", (client_id, client_name))

        row = db.fetch_one(
            "SELECT id FROM projects WHERE client_id = %s AND name = %s",
            (client_id, project_name),
        )
        if row:
            project_id = str(row["id"])
            console.print(f"[yellow]Using existing project:[/] {project_name} ({project_id[:8]}...)")
        else:
            project_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO projects (id, client_id, name, status) VALUES (%s, %s, %s, 'pending')",
                (project_id, client_id, project_name),
            )
            console.print(f"[green]Created project:[/] {project_name} ({project_id[:8]}...)")

    return project_id


_TYPE_ICONS = {
    "functional": ("⚡", "cyan"),
    "non_functional": ("🔒", "magenta"),
    "constraint": ("📌", "yellow"),
    "assumption": ("💭", "blue"),
}

_SDLC_ICONS = {
    "requirements":     ("📋", "cyan"),
    "design":           ("🎨", "magenta"),
    "technical":        ("⚙️ ", "blue"),
    "timeline":         ("📅", "green"),
    "budget":           ("💰", "yellow"),
    "testing":          ("🧪", "red"),
    "integrations":     ("🔗", "white"),
    "team_and_process": ("👥", "bright_white"),
}


def print_requirements(project_id: str) -> None:
    with DB() as db:
        reqs = db.fetch_all(
            "SELECT req_type, sdlc_topic, title, description, confidence FROM requirements "
            "WHERE project_id = %s ORDER BY req_type, confidence DESC",
            (project_id,),
        )

    if not reqs:
        console.print("[red]No requirements found.[/]")
        return

    # ── View 1: grouped by req_type ──────────────────────────────────────────
    console.print("\n[bold]By Requirement Type[/]")
    type_groups: dict[str, list] = {}
    for r in reqs:
        type_groups.setdefault(r["req_type"], []).append(r)

    for req_type, items in type_groups.items():
        icon, colour = _TYPE_ICONS.get(req_type, ("•", "white"))
        label = req_type.replace("_", " ").title()

        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style=f"bold {colour}",
            expand=True,
        )
        table.add_column("Title", style=colour, no_wrap=False, ratio=2)
        table.add_column("Description", no_wrap=False, ratio=4)
        table.add_column("SDLC Topic", width=16)
        table.add_column("Conf", justify="right", width=6)

        for r in items:
            conf = r["confidence"] or 0
            conf_str = f"[green]{conf:.0%}[/]" if conf >= 0.8 else f"[yellow]{conf:.0%}[/]"
            topic = r.get("sdlc_topic") or "requirements"
            t_icon, t_colour = _SDLC_ICONS.get(topic, ("•", "white"))
            table.add_row(
                r["title"],
                r["description"],
                f"[{t_colour}]{t_icon} {topic}[/]",
                conf_str,
            )

        console.print(Panel(table, title=f"{icon}  {label} ({len(items)})", border_style=colour))

    # ── View 2: grouped by SDLC topic ────────────────────────────────────────
    console.print("\n[bold]By SDLC Topic[/]")
    sdlc_groups: dict[str, list] = {}
    for r in reqs:
        topic = r.get("sdlc_topic") or "requirements"
        sdlc_groups.setdefault(topic, []).append(r)

    for topic, items in sorted(sdlc_groups.items()):
        icon, colour = _SDLC_ICONS.get(topic, ("•", "white"))
        label = topic.replace("_", " ").title()

        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style=f"bold {colour}",
            expand=True,
        )
        table.add_column("Title", style=colour, no_wrap=False, ratio=2)
        table.add_column("Description", no_wrap=False, ratio=4)
        table.add_column("Type", width=14)
        table.add_column("Conf", justify="right", width=6)

        for r in items:
            conf = r["confidence"] or 0
            conf_str = f"[green]{conf:.0%}[/]" if conf >= 0.8 else f"[yellow]{conf:.0%}[/]"
            rt = r.get("req_type", "functional")
            rt_icon, rt_colour = _TYPE_ICONS.get(rt, ("•", "white"))
            table.add_row(
                r["title"],
                r["description"],
                f"[{rt_colour}]{rt_icon} {rt.replace('_', ' ')}[/]",
                conf_str,
            )

        console.print(Panel(table, title=f"{icon}  {label} ({len(items)})", border_style=colour))

    # ── Summary distribution ─────────────────────────────────────────────────
    summary = Table(box=box.SIMPLE, show_header=True, header_style="bold white", expand=False)
    summary.add_column("SDLC Topic", style="white")
    summary.add_column("Count", justify="right", style="cyan")
    for topic in [
        "requirements", "design", "technical", "timeline",
        "budget", "testing", "integrations", "team_and_process",
    ]:
        count = len(sdlc_groups.get(topic, []))
        if count:
            icon, colour = _SDLC_ICONS.get(topic, ("•", "white"))
            summary.add_row(f"[{colour}]{icon} {topic}[/]", str(count))
    console.print(Panel(summary, title="SDLC Topic Distribution", border_style="dim white"))


def print_clarifications(project_id: str) -> None:
    with DB() as db:
        qs = db.fetch_all(
            "SELECT question, context, priority FROM clarifications "
            "WHERE project_id = %s AND status = 'open' ORDER BY priority DESC",
            (project_id,),
        )

    if not qs:
        console.print("[yellow]No open clarification questions.[/]")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold white", expand=True)
    table.add_column("#", width=3, justify="right")
    table.add_column("Priority", width=8)
    table.add_column("Question", ratio=3)
    table.add_column("Context", ratio=2)

    priority_style = {"high": "red", "medium": "yellow", "low": "green"}
    for i, q in enumerate(qs, 1):
        style = priority_style.get(q["priority"], "white")
        table.add_row(
            str(i),
            f"[{style}]{q['priority'].upper()}[/]",
            q["question"],
            q.get("context") or "—",
        )

    console.print(Panel(table, title="💬  Clarification Questions", border_style="white"))


# ─── Main ────────────────────────────────────────────────────────────────────

async def run(client_name: str, project_name: str, doc_paths: list[str]) -> None:
    console.rule("[bold cyan]StackForge — Stage 1: Requirement Ingestion[/]")

    # Validate files exist
    valid_paths = []
    for path in doc_paths:
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            console.print(f"[red]✗ File not found:[/] {abs_path}")
        else:
            valid_paths.append(abs_path)
            console.print(f"[green]✓[/] {os.path.basename(abs_path)}")

    if not valid_paths:
        console.print("[red]No valid files to process. Exiting.[/]")
        return

    project_id = create_project(client_name, project_name)

    for path in valid_paths:
        filename = os.path.basename(path)
        ext = filename.rsplit(".", 1)[-1].lower()

        with open(path, "rb") as f:
            file_bytes = f.read()

        console.print(f"\n[bold]Processing:[/] {filename}")

        with console.status(f"  [cyan]Parsing & chunking...[/]"):
            pass  # status shown during actual async work below

        try:
            with DB() as db:
                db.execute(
                    "UPDATE projects SET status = 'processing' WHERE id = %s",
                    (project_id,),
                )

            console.print(f"  [dim]→ chunking text[/]")
            await _run_with_progress(project_id, file_bytes, filename, ext)
            console.print(f"  [green]✓ done[/]")

        except Exception as e:
            console.print(f"  [red]✗ failed:[/] {e}")

    # Mark project ready
    with DB() as db:
        db.execute("UPDATE projects SET status = 'ready' WHERE id = %s", (project_id,))

    # Print results
    console.print()
    console.rule("[bold green]Extracted Requirements[/]")
    print_requirements(project_id)

    console.print()
    console.rule("[bold white]Clarification Questions[/]")
    print_clarifications(project_id)

    # ── Stage 1 token economics ───────────────────────────────────────────────
    from pipeline.metrics_terminal import render_stage_metrics
    from pipeline.stage1_metrics_calculator import get_report as get_stage1_report

    console.print()
    console.rule("[bold yellow]Stage 1 — Token Economics[/]")
    render_stage_metrics(console, get_stage1_report(project_id), "Stage 1 — Requirement Ingestion")

    # ── Stage 2: Epic & User Story generation (so the demo shows full economics) ─
    console.print()
    console.rule("[bold magenta]Stage 2 — Epic & User Story Generation[/]")
    try:
        from pipeline.metrics_calculator import get_metrics_report as get_stage2_report
        from pipeline.stage2_runner import run_stage2

        with console.status("  [magenta]Generating epics & user stories...[/]"):
            stage2_result = await run_stage2(project_id)
        console.print(
            f"  [green]✓[/] {stage2_result.get('epic_count', 0)} epics, "
            f"{stage2_result.get('story_count', 0)} user stories"
        )
        console.print()
        render_stage_metrics(console, get_stage2_report(project_id), "Stage 2 — Epics & Stories")
    except Exception as e:
        console.print(f"  [yellow]⚠ Stage 2 skipped:[/] {e}")

    # ── Stage 3: Sprint & Task Planning ───────────────────────────────────────
    console.print()
    console.rule("[bold cyan]Stage 3 — Sprint & Task Planning[/]")
    try:
        from pipeline.stage3_metrics_calculator import get_metrics_report as get_stage3_report
        from pipeline.stage3_runner import run_stage3
        from db import DB as _DB

        with console.status("  [cyan]Assigning stories to sprints and generating tasks…[/]"):
            stage3_result = await run_stage3(project_id)

        sprint_count = stage3_result.get("sprint_count", 0)
        task_count = stage3_result.get("task_count", 0)
        console.print(
            f"  [green]✓[/] {sprint_count} sprints, {task_count} tasks generated"
        )
        console.print()

        # ── Sprint plan table ─────────────────────────────────────────────────
        from rich.table import Table

        sprint_rows = []
        with _DB() as db:
            sprint_rows = db.fetch_all(
                "SELECT sprint_number, name, total_points, capacity_points FROM sprints "
                "WHERE project_id = %s ORDER BY sprint_number",
                (project_id,),
            )
            story_counts = db.fetch_all(
                "SELECT sprint_id, COUNT(*) AS cnt FROM sprint_stories "
                "WHERE project_id = %s GROUP BY sprint_id",
                (project_id,),
            )
            # Map sprint_id → story count
            sprint_id_rows = db.fetch_all(
                "SELECT id, sprint_number FROM sprints WHERE project_id = %s",
                (project_id,),
            )

        sprint_id_map = {str(r["id"]): r["sprint_number"] for r in sprint_id_rows}
        sc_by_num = {
            sprint_id_map.get(str(r["sprint_id"])): int(r["cnt"])
            for r in story_counts
            if str(r["sprint_id"]) in sprint_id_map
        }

        tbl = Table(
            title="Sprint Plan",
            border_style="dim",
            header_style="bold cyan",
            show_lines=False,
        )
        tbl.add_column("Sprint", style="bold white", width=10)
        tbl.add_column("Stories", justify="center", width=8)
        tbl.add_column("Points", justify="center", width=8)
        tbl.add_column("Capacity", justify="center", width=10)
        tbl.add_column("Utilisation", width=28)

        for row in sprint_rows:
            num = row["sprint_number"]
            used = row["total_points"]
            cap = row["capacity_points"]
            stories = sc_by_num.get(num, 0)
            pct = round(used / cap * 100) if cap else 0
            bar_filled = int(pct / 5)
            bar = "[green]" + "█" * bar_filled + "[/][dim]" + "░" * (20 - bar_filled) + "[/]"
            util_str = f"{bar} {pct}%"
            tbl.add_row(row["name"], str(stories), str(used), str(cap), util_str)

        console.print(tbl)
        console.print()

        # ── Sample task breakdown (first sprint only) ─────────────────────────
        if sprint_rows:
            first_sprint_id = None
            with _DB() as db:
                first_sprint = db.fetch_one(
                    "SELECT id FROM sprints WHERE project_id = %s ORDER BY sprint_number LIMIT 1",
                    (project_id,),
                )
                if first_sprint:
                    first_sprint_id = str(first_sprint["id"])
                    sample_stories = db.fetch_all(
                        """
                        SELECT us.title, us.story_points,
                               t.title as task_title, t.task_type, t.estimated_hours
                        FROM sprint_stories ss
                        JOIN user_stories us ON us.id = ss.story_id
                        LEFT JOIN tasks t ON t.story_id = ss.story_id
                        WHERE ss.sprint_id = %s
                        ORDER BY ss.priority_order, t.task_type, t.created_at
                        """,
                        (first_sprint_id,),
                    )

            if first_sprint_id and sample_stories:
                console.print("[bold]Sample Task Breakdown — Sprint 1[/]")
                current_story = None
                TASK_TYPE_COLOR = {
                    "backend": "blue", "frontend": "violet", "testing": "red",
                    "devops": "green", "design": "yellow", "documentation": "white",
                }
                for row in sample_stories:
                    if row["title"] != current_story:
                        current_story = row["title"]
                        pts = row.get("story_points") or "?"
                        console.print(
                            f"\n  [bold white]{current_story}[/] "
                            f"[dim]({pts} pts)[/]"
                        )
                    if row.get("task_title"):
                        tt = row.get("task_type", "backend")
                        color = TASK_TYPE_COLOR.get(tt, "white")
                        hrs = row.get("estimated_hours", 0)
                        hrs_str = f"{int(hrs)}h" if hrs == int(hrs) else f"{hrs}h"
                        console.print(
                            f"    [dim]├─[/] [{color}][{tt}][/{color}]  "
                            f"{row['task_title']}  [dim]({hrs_str})[/]"
                        )
                console.print()

        render_stage_metrics(console, get_stage3_report(project_id), "Stage 3 — Sprint & Tasks")

    except Exception as e:
        console.print(f"  [yellow]⚠ Stage 3 skipped:[/] {e}")

    # Write SDLC docs
    try:
        from pipeline.doc_writer import write_sdlc_docs
        output_dir = write_sdlc_docs(project_id, project_name)
        rel_dir = os.path.relpath(output_dir, os.path.dirname(__file__))
        console.print()
        console.rule("[bold cyan]SDLC Documents[/]")
        console.print(f"\n[bold]Docs written to:[/] {rel_dir}\\")
        for topic in [
            "requirements", "design", "technical", "timeline",
            "budget", "testing", "integrations", "team_and_process",
        ]:
            console.print(f"  [dim]→[/] {topic}.md")
        console.print("\n[dim]Open the Documents tab in the Streamlit UI to read and edit docs.[/]")
    except Exception as e:
        console.print(f"[yellow]⚠ Doc generation skipped:[/] {e}")

    console.rule()
    console.print(f"\n[bold]Project ID:[/] {project_id}")
    console.print("[dim]Open the Streamlit UI to answer clarifications and run RAG queries.[/]")


async def _run_with_progress(project_id, file_bytes, filename, ext):
    """Thin wrapper that prints step labels while the pipeline runs."""
    from pipeline.parser import parse
    from pipeline.chunker import chunk
    from pipeline.summarizer import summarize_all
    from pipeline.extractor import extract_requirements
    from pipeline.embedder import embed_chunk_summaries, embed_requirements
    from pipeline.clarifier import generate_clarifications
    from pipeline.stage1_metrics_calculator import record_step
    import hashlib
    import time

    content_hash = hashlib.sha256(file_bytes).hexdigest()
    doc_id = str(uuid.uuid4())

    with DB() as db:
        existing = db.fetch_one(
            "SELECT id, status FROM documents WHERE project_id = %s AND content_hash = %s",
            (project_id, content_hash),
        )
        if existing and existing["status"] == "done":
            console.print("  [yellow]→ already processed (skipping)[/]")
            return existing["id"]

        db.execute(
            "INSERT INTO documents (id, project_id, filename, file_type, content_hash, status) "
            "VALUES (%s, %s, %s, %s, %s, 'processing') ON CONFLICT DO NOTHING",
            (doc_id, project_id, filename, ext, content_hash),
        )

    text = parse(file_bytes, ext)
    chunks = chunk(text)
    console.print(f"  [dim]→ {len(chunks)} chunks — summarising with {MODEL_CHEAP_NAME}...[/]")

    _t0 = time.perf_counter()
    summaries, summ_usage = await summarize_all(chunks, doc_name=filename)
    record_step(project_id, "summarization", MODEL_CHEAP_NAME, summ_usage,
                int((time.perf_counter() - _t0) * 1000))

    chunk_rows = []
    with DB() as db:
        for i, (raw, summary) in enumerate(zip(chunks, summaries)):
            chunk_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO doc_chunks (id, document_id, chunk_index, raw_text, summary) "
                "VALUES (%s, %s, %s, %s, %s)",
                (chunk_id, doc_id, i, raw, summary),
            )
            chunk_rows.append({"id": chunk_id, "document_id": doc_id, "chunk_index": i,
                                "raw_text": raw, "summary": summary})

    console.print(f"  [dim]→ extracting requirements with {MODEL_CAPABLE_NAME}...[/]")
    _t0 = time.perf_counter()
    reqs, extr_usage = await extract_requirements(summaries, [doc_id])
    record_step(project_id, "extraction", MODEL_CAPABLE_NAME, extr_usage,
                int((time.perf_counter() - _t0) * 1000))

    req_rows = []
    with DB() as db:
        for r in reqs:
            req_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO requirements (id, project_id, req_type, sdlc_topic, title, description, "
                "source_document_ids, confidence) VALUES (%s, %s, %s, %s, %s, %s, %s::uuid[], %s)",
                (req_id, project_id, r["req_type"], r.get("sdlc_topic", "requirements"),
                 r["title"], r["description"], "{" + doc_id + "}", r["confidence"]),
            )
            req_rows.append({**r, "id": req_id})

    with DB() as db:
        embed_chunk_summaries(db, project_id, chunk_rows)
        embed_requirements(db, project_id, req_rows)

    console.print(f"  [dim]→ generating clarification questions...[/]")
    all_reqs = _fetch_reqs(project_id)
    _t0 = time.perf_counter()
    clarifications, clar_usage = await generate_clarifications(all_reqs)
    record_step(project_id, "clarification", MODEL_CHEAP_NAME, clar_usage,
                int((time.perf_counter() - _t0) * 1000))

    with DB() as db:
        db.execute("DELETE FROM clarifications WHERE project_id = %s AND status = 'open'",
                   (project_id,))
        for c in clarifications:
            db.execute(
                "INSERT INTO clarifications (id, project_id, question, context, priority) "
                "VALUES (%s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), project_id, c["question"],
                 c.get("context", ""), c.get("priority", "medium")),
            )
        db.execute("UPDATE documents SET status = 'done' WHERE id = %s", (doc_id,))

    return doc_id


def _fetch_reqs(project_id):
    with DB() as db:
        return db.fetch_all(
            "SELECT req_type, title, description, confidence FROM requirements WHERE project_id = %s",
            (project_id,),
        )


# Import model names for display
from config import MODEL_CHEAP as MODEL_CHEAP_NAME, MODEL_CAPABLE as MODEL_CAPABLE_NAME


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StackForge Stage 1 CLI demo")
    parser.add_argument("--client", default="CareFlow", help="Client name")
    parser.add_argument("--project", default="CareFlow Platform 2026", help="Project name")
    parser.add_argument("--docs", nargs="+", default=DEFAULT_DOCS,
                        help="Paths to PDF/DOCX/TXT files to ingest")
    args = parser.parse_args()

    asyncio.run(run(args.client, args.project, args.docs))
