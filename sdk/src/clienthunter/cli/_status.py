"""``clienthunter status`` — strategy and campaign status views.

    clienthunter status                        # table of all strategies
    clienthunter status --strategy UUID        # detailed per-strategy view
    clienthunter status --strategy UUID --watch # auto-refresh
    clienthunter status --strategy UUID --json  # machine-readable

NOTE: The all-strategies table requires ``GET /strategies`` on the backend,
which is not in M1–M5.  See ``backend_additions/strategies_list.py`` for
the endpoint to add.  Until it's deployed, the table falls back to a
helpful error message instead of crashing.
"""
from __future__ import annotations

import json
import time
from typing import Optional

import typer
from rich import box
from rich.live import Live
from rich.table import Table

from clienthunter.cli._console import _get_client, console, err_console, handle_error, print_json
from clienthunter.exceptions import APIError, ClientHunterError
from clienthunter.models import CampaignOverview, StrategyStatus

_WATCH_INTERVAL = 8  # seconds


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _strategy_row(s: StrategyStatus) -> list[str]:
    total_done = sum(pp.done for pp in s.progress)
    total_steps = sum(pp.total for pp in s.progress)
    progress_str = f"{total_done}/{total_steps}"

    v_passes = s.verification
    v_done = sum(1 for p in v_passes if p.get("result") == "PASS")
    v_str = f"{v_done}/{len(v_passes)}" if v_passes else "—"

    status_color = {
        "pending": "yellow", "researching": "cyan", "verifying": "cyan",
        "verified": "green", "executing": "green",
        "needs_human_review": "yellow", "failed": "red",
    }.get(s.status, "white")

    return [
        s.id[:8] + "…",
        s.flow_type,
        f"[{status_color}]{s.status}[/{status_color}]",
        progress_str,
        v_str,
    ]


def _all_strategies_table(strategies: list[StrategyStatus]) -> Table:
    t = Table(
        title="Strategies",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    t.add_column("ID (prefix)", style="muted", min_width=12)
    t.add_column("Flow")
    t.add_column("Status", min_width=20)
    t.add_column("Pipeline", justify="right")
    t.add_column("Verified", justify="right")
    for s in strategies:
        t.add_row(*_strategy_row(s))
    return t


def _detail_panel(s: StrategyStatus, campaign: CampaignOverview | None) -> Table:
    """Rich table for per-strategy detailed view."""
    root = Table.grid(padding=(0, 1))

    # Header
    root.add_row(f"[bold]Strategy[/bold]: {s.id}")
    root.add_row(f"[bold]Flow[/bold]: {s.flow_type}   [bold]Status[/bold]: {s.status}")
    if s.error:
        root.add_row(f"[error]Error:[/error] {s.error}")
    root.add_row("")

    # Pipeline phases
    for pp in s.progress:
        root.add_row(f"[bold]{pp.pipeline.upper()} Pipeline[/bold] ({pp.done}/{pp.total} steps)")
        pt = Table(box=box.SIMPLE, show_header=False)
        pt.add_column("", width=4)
        pt.add_column("Phase", min_width=24)
        pt.add_column("", min_width=20)
        pt.add_column("Steps", justify="right")
        for ph in pp.phases:
            pct = ph.done / ph.total if ph.total else 0
            bar = ("█" * int(pct * 14)) + ("░" * (14 - int(pct * 14)))
            style = "phase.done" if ph.done == ph.total else ("phase.running" if ph.done else "phase.pending")
            icon = "✓" if ph.done == ph.total else ("↻" if ph.done else "·")
            pt.add_row(f"[{style}]{icon}[/{style}]", f"[{style}]{ph.title}[/{style}]",
                       f"[{style}]{bar}[/{style}]", f"{ph.done}/{ph.total}")
        root.add_row(pt)
        root.add_row("")

    # Verification passes
    if s.verification:
        root.add_row("[bold]Verification Passes[/bold]")
        vt = Table(box=box.SIMPLE, show_header=False)
        vt.add_column("", width=3)
        vt.add_column("Pass", min_width=30)
        vt.add_column("Result", width=8)
        for p in s.verification:
            result = p.get("result", "—")
            name = p.get("name", f"Pass {p.get('pass_no', '?')}")
            fixes = p.get("fixes")
            if result == "PASS":
                icon, style = "✓", "phase.done"
            elif result == "FAIL":
                icon, style = "✗", "error"
            else:
                icon, style = "·", "phase.pending"
            vt.add_row(f"[{style}]{icon}[/{style}]",
                       f"[{style}]{name}[/{style}]" + (f"\n  [muted]{fixes}[/muted]" if fixes else ""),
                       f"[{style}]{result}[/{style}]")
        root.add_row(vt)
        root.add_row("")

    # Campaign stats
    if campaign:
        root.add_row("[bold]Campaign[/bold]")
        ct = Table(box=box.SIMPLE, show_header=False)
        ct.add_column("", min_width=22)
        ct.add_column("", min_width=20)

        state = campaign.campaign_state or "not started"
        ct.add_row("[bold]State[/bold]", state)
        if campaign.campaign_pause_reason:
            ct.add_row("[bold]Pause reason[/bold]", campaign.campaign_pause_reason)
        ct.add_row("[bold]Sent total[/bold]", str(campaign.sent_total))
        ct.add_row("[bold]Sends today[/bold]", f"{campaign.sends_today} / {campaign.daily_cap_today} cap")
        ct.add_row("[bold]Reply rate[/bold]", f"{campaign.reply_rate:.1%}")
        ct.add_row("[bold]Bounce rate[/bold]", f"{campaign.bounce_rate:.1%}")
        ct.add_row("[bold]Meetings booked[/bold]", str(campaign.meetings_booked))
        ct.add_row("[bold]Unsubscribed[/bold]", str(campaign.unsubscribed))

        for ch_name, ch_stats in campaign.channels.items():
            ct.add_row(f"[bold]{ch_name.upper()} sends today[/bold]",
                       f"{ch_stats.get('sends_today', 0)} / {ch_stats.get('daily_cap_today', 0)}")
        root.add_row(ct)

    return root


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def status(
    strategy: Optional[str] = typer.Option(
        None, "--strategy", "-s",
        help="Show detail for one strategy UUID.",
    ),
    watch: bool = typer.Option(
        False, "--watch", "-w",
        help="Poll and refresh every few seconds (Ctrl-C to stop).",
    ),
    output_json: bool = typer.Option(
        False, "--json",
        help="Output machine-readable JSON to stdout.",
    ),
) -> None:
    """Show pipeline progress, verification passes, and campaign stats.

    Without --strategy: table of all strategies (requires backend_additions endpoint).
    With --strategy UUID: full detail view with per-phase steps and channel stats.
    """
    ch = _get_client()

    if strategy:
        _show_one(ch, strategy, watch=watch, output_json=output_json)
    else:
        _show_all(ch, watch=watch, output_json=output_json)


def _show_all(ch, watch: bool, output_json: bool) -> None:
    def _fetch():
        try:
            return ch.strategies.list()
        except APIError as exc:
            if exc.status_code in (404, 405):
                err_console.print(
                    "[warning]⚠ The backend endpoint GET /strategies is not yet deployed.[/warning]\n"
                    "Add it by following the instructions in [bold]backend_additions/strategies_list.py[/bold].\n"
                    "Until then, use [bold]clienthunter status --strategy UUID[/bold] for per-strategy detail."
                )
                raise typer.Exit(1)
            raise

    if watch:
        with Live(console=console, refresh_per_second=0.2) as live:
            try:
                while True:
                    try:
                        strategies = _fetch()
                    except ClientHunterError as exc:
                        handle_error(exc, json_mode=output_json)
                    live.update(_all_strategies_table(strategies))
                    time.sleep(_WATCH_INTERVAL)
            except KeyboardInterrupt:
                pass
        return

    try:
        strategies = _fetch()
    except ClientHunterError as exc:
        handle_error(exc, json_mode=output_json)

    if output_json:
        print_json([s.model_dump() for s in strategies])
        return

    if not strategies:
        console.print("[muted]No strategies found. Run [bold]clienthunter run[/bold] to create one.[/muted]")
        return

    console.print(_all_strategies_table(strategies))


def _show_one(ch, strategy_id: str, watch: bool, output_json: bool) -> None:
    def _fetch():
        s = ch.strategies.progress(strategy_id)
        try:
            campaign = ch.campaigns.overview(strategy_id)
        except ClientHunterError:
            campaign = None
        return s, campaign

    if watch:
        with Live(console=console, refresh_per_second=0.2) as live:
            try:
                while True:
                    try:
                        s, campaign = _fetch()
                    except ClientHunterError as exc:
                        handle_error(exc, json_mode=output_json)
                    live.update(_detail_panel(s, campaign))
                    time.sleep(_WATCH_INTERVAL)
            except KeyboardInterrupt:
                pass
        return

    try:
        s, campaign = _fetch()
    except ClientHunterError as exc:
        handle_error(exc, json_mode=output_json)

    if output_json:
        data = s.model_dump()
        if campaign:
            data["campaign"] = campaign.model_dump()
        print_json(data)
        return

    console.print(_detail_panel(s, campaign))
