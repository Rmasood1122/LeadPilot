"""``clienthunter leads`` — list and export leads for a strategy.

    clienthunter leads list --strategy UUID [--status verified] [--json]
    clienthunter leads export --strategy UUID [--output leads.csv]
"""
from __future__ import annotations

import csv
import sys
from typing import Optional

import typer
from rich import box
from rich.table import Table

from clienthunter.cli._console import _get_client, console, err_console, handle_error, print_json
from clienthunter.exceptions import ClientHunterError

leads_app = typer.Typer(name="leads", help="List and export leads for a strategy.")

_CSV_FIELDS = [
    "id", "status", "source", "full_name", "title", "company",
    "email", "phone", "created_at",
]

_STATUS_CHOICES = [
    "sourced", "enriched", "email_found", "verified", "flagged", "dropped",
    "contacted", "replied", "meeting_booked",
]


@leads_app.command("list")
def leads_list(
    strategy: str = typer.Option(..., "--strategy", "-s", help="Strategy UUID."),
    status: Optional[str] = typer.Option(
        None, "--status",
        help=f"Filter by status. Choices: {', '.join(_STATUS_CHOICES)}",
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max leads to show."),
    offset: int = typer.Option(0, "--offset", help="Pagination offset."),
    output_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """List leads for a strategy with optional status filter."""
    ch = _get_client()
    try:
        result = ch.leads.list(
            strategy_id=strategy,
            status=status,
            limit=limit,
            offset=offset,
        )
    except ClientHunterError as exc:
        handle_error(exc, json_mode=output_json)

    if output_json:
        print_json({
            "total": result.total,
            "limit": result.limit,
            "offset": result.offset,
            "items": [lead.model_dump() for lead in result.items],
        })
        return

    if not result.items:
        console.print("[muted]No leads found.[/muted]")
        return

    t = Table(
        title=f"Leads (showing {len(result.items)} of {result.total})",
        box=box.ROUNDED, show_header=True, header_style="bold cyan",
    )
    t.add_column("Status", min_width=14)
    t.add_column("Name", min_width=20)
    t.add_column("Title", min_width=20)
    t.add_column("Company", min_width=20)
    t.add_column("Email", min_width=24)

    _STATUS_COLORS = {
        "verified": "green", "meeting_booked": "bold green", "replied": "cyan",
        "contacted": "blue", "dropped": "red", "flagged": "yellow",
    }

    for lead in result.items:
        color = _STATUS_COLORS.get(lead.status, "white")
        t.add_row(
            f"[{color}]{lead.status}[/{color}]",
            lead.full_name or "—",
            lead.title or "—",
            lead.company or "—",
            lead.email or "—",
        )

    console.print(t)
    if result.total > result.offset + result.limit:
        remaining = result.total - result.offset - result.limit
        console.print(
            f"[muted]  … {remaining} more. Use --offset {result.offset + result.limit} to page.[/muted]"
        )


@leads_app.command("export")
def leads_export(
    strategy: str = typer.Option(..., "--strategy", "-s", help="Strategy UUID."),
    output: Optional[str] = typer.Option(
        None, "--output", "-o",
        help="Output CSV file path. Defaults to stdout.",
    ),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status."),
    limit: int = typer.Option(1000, "--limit", "-n", help="Max leads to export."),
) -> None:
    """Export leads as CSV (to file or stdout)."""
    ch = _get_client()
    try:
        result = ch.leads.list(strategy_id=strategy, status=status, limit=limit)
    except ClientHunterError as exc:
        handle_error(exc)

    if output:
        out_file = open(output, "w", newline="", encoding="utf-8")
        target = out_file
    else:
        out_file = None
        target = sys.stdout

    try:
        writer = csv.DictWriter(target, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for lead in result.items:
            writer.writerow(lead.model_dump())
    finally:
        if out_file:
            out_file.close()

    if output:
        console.print(
            f"[success]✓ Exported {len(result.items)} leads to {output}[/success]"
        )
        if result.total > limit:
            err_console.print(
                f"[warning]⚠ {result.total - limit} leads not exported (limit {limit}). "
                f"Increase --limit to export all.[/warning]"
            )
