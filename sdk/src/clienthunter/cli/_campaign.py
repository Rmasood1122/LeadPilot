"""``clienthunter campaign`` — manual campaign controls.

    clienthunter campaign pause  --strategy UUID
    clienthunter campaign resume --strategy UUID

Pause stops outreach immediately (no more sends).
Resume clears a manual OR bounce-triggered pause.

After a bounce-rate pause the backend's 3% monitor will re-pause if bounces
continue.  Resuming is a deliberate human decision — fix your lead quality
first.
"""
from __future__ import annotations

import typer
from rich.prompt import Confirm

from clienthunter.cli._console import _get_client, console, handle_error
from clienthunter.exceptions import ClientHunterError

campaign_app = typer.Typer(name="campaign", help="Pause or resume a campaign.")


@campaign_app.command("pause")
def campaign_pause(
    strategy: str = typer.Option(..., "--strategy", "-s", help="Strategy UUID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Pause outreach for a strategy — no messages will be sent until resumed."""
    if not yes:
        confirmed = Confirm.ask(
            f"Pause campaign for strategy [bold]{strategy[:8]}…[/bold]? "
            "No messages will be sent until you resume."
        )
        if not confirmed:
            raise typer.Abort()

    ch = _get_client()
    try:
        result = ch.campaigns.pause(strategy)
    except ClientHunterError as exc:
        handle_error(exc, json_mode=output_json)

    if output_json:
        from clienthunter.cli._console import print_json
        print_json(result.model_dump())
        return

    console.print(
        f"[warning]⏸ Campaign paused.[/warning] "
        f"State: {result.campaign_state}.\n"
        f"Resume with: [bold]clienthunter campaign resume --strategy {strategy}[/bold]"
    )


@campaign_app.command("resume")
def campaign_resume(
    strategy: str = typer.Option(..., "--strategy", "-s", help="Strategy UUID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Resume a paused campaign.

    If paused due to a high bounce rate (> 3%), review your lead list quality
    before resuming — the backend monitor will pause again if bounces continue.
    """
    if not yes:
        confirmed = Confirm.ask(
            f"Resume campaign for strategy [bold]{strategy[:8]}…[/bold]?"
        )
        if not confirmed:
            raise typer.Abort()

    ch = _get_client()
    try:
        result = ch.campaigns.resume(strategy)
    except ClientHunterError as exc:
        handle_error(exc, json_mode=output_json)

    if output_json:
        from clienthunter.cli._console import print_json
        print_json(result.model_dump())
        return

    console.print(
        f"[success]▶ Campaign resumed.[/success] "
        f"State: {result.campaign_state}."
    )
