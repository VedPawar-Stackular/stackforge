"""
Terminal renderer for a stage metrics report (Stage 1 or Stage 2).

Takes the dict produced by either metrics calculator and prints a rich table of
per-step token economics plus a savings summary. Kept separate from run_demo so the
same renderer can be reused by any CLI entry point.
"""

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def _fmt_usd(value: float) -> str:
    """Format a USD cost with enough precision to be non-zero for tiny amounts."""
    if value == 0:
        return "$0"
    if value < 0.01:
        return f"${value:.6f}"
    return f"${value:.4f}"


def render_stage_metrics(console: Console, report: dict, title: str) -> None:
    """Print a per-step token/cost table + savings summary for one pipeline stage."""
    steps = report.get("steps", [])

    if not steps:
        console.print(
            Panel(
                "[yellow]No metrics recorded for this stage yet.[/]",
                title=f"💰  {title}",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        return

    table = Table(box=box.SIMPLE, expand=True, header_style="bold cyan")
    table.add_column("Step", style="white", no_wrap=True)
    table.add_column("Model · Tier", style="dim")
    table.add_column("Input", justify="right", style="green")
    table.add_column("Output", justify="right", style="green")
    table.add_column("Thinking", justify="right", style="magenta")
    table.add_column("Total", justify="right", style="bold")
    table.add_column("Time", justify="right", style="dim")
    table.add_column("Actual", justify="right", style="bold green")
    table.add_column("Opus eq.", justify="right", style="red")
    table.add_column("×", justify="right", style="bold red")

    for s in steps:
        total = s["input_tokens"] + s["output_tokens"] + s.get("thinking_tokens", 0)
        mult = s.get("opus_multiplier", 0.0)
        table.add_row(
            s["step"],
            f"{s['model']} · {s['tier']}",
            f"{s['input_tokens']:,}",
            f"{s['output_tokens']:,}",
            f"{s.get('thinking_tokens', 0):,}",
            f"{total:,}",
            f"{s['duration_ms']:,}ms",
            _fmt_usd(s["cost_usd"]),
            _fmt_usd(s.get("opus_equivalent_cost_usd", 0.0)),
            f"{mult:g}×" if mult else "—",
        )

    actual = report.get("actual_cost_usd", 0.0)
    naive = report.get("naive_cost_usd", 0.0)
    savings = report.get("savings_pct", 0.0)
    thinking_total = report.get("actual_thinking_tokens", 0)

    cost_saved = naive - actual
    summary = (
        f"[bold green]Actual:[/] {_fmt_usd(actual)}    "
        f"[bold red]Naive all-Opus baseline:[/] {_fmt_usd(naive)}    "
        f"[bold cyan]Saved:[/] {savings:g}%  ([green]{_fmt_usd(cost_saved)}[/] saved)\n"
        f"[dim]Thinking tokens this stage: {thinking_total:,} "
        f"(0 expected — current Groq llama models are not reasoning models).[/]"
    )

    console.print(
        Panel(table, title=f"💰  {title}", border_style="cyan", box=box.ROUNDED)
    )
    console.print(Panel(summary, border_style="green", box=box.ROUNDED))
