"""Shared console objects, client factory, and error handler for the CLI.

All CLI commands import from here so tests can patch a single location
(``clienthunter.cli._console._get_client``) without worrying about which
submodule instantiated the client.
"""
from __future__ import annotations

import json
import sys
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme

from clienthunter.exceptions import (
    APIError,
    AuthError,
    ClientHunterError,
    ComplianceError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Console instances
# ---------------------------------------------------------------------------

_THEME = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "muted": "dim",
        "phase.done": "green",
        "phase.running": "cyan",
        "phase.pending": "dim",
    }
)

console = Console(theme=_THEME)
err_console = Console(stderr=True, theme=_THEME)


# ---------------------------------------------------------------------------
# Client factory — patched in tests
# ---------------------------------------------------------------------------


def _get_client(**kwargs: Any):  # -> ClientHunter, imported lazily to avoid circular
    """Create a configured ``ClientHunter`` from the current config + kwargs.

    This is the single instantiation point for CLI commands.  Tests patch
    ``clienthunter.cli._console._get_client`` to inject a mock client.
    """
    from clienthunter import ClientHunter

    return ClientHunter(**kwargs)


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------


def handle_error(exc: ClientHunterError | Exception, *, json_mode: bool = False) -> None:
    """Print a user-friendly error to stderr and exit 1.

    Compliance errors get a dedicated panel with the blocked rule and a
    plain-language remediation step — never a suggestion to bypass.
    Auth errors remind the user to run ``clienthunter init``.
    """
    if json_mode:
        # Machine-readable errors always on stderr so stdout stays clean
        payload: dict[str, Any] = {"error": type(exc).__name__}
        if isinstance(exc, ComplianceError):
            payload["rule"] = exc.rule
            payload["detail"] = exc.detail
            payload["remediation"] = exc.remediation
        elif isinstance(exc, ClientHunterError):
            payload["detail"] = str(exc)
        else:
            payload["detail"] = str(exc)
        err_console.print_json(json.dumps(payload))
        raise typer.Exit(1)

    if isinstance(exc, ComplianceError):
        lines = [f"[bold]Rule:[/bold] {exc.rule}", f"[bold]Detail:[/bold] {exc.detail}"]
        if exc.remediation:
            lines += ["", f"[bold]What to do:[/bold] {exc.remediation}"]
        err_console.print(
            Panel(
                "\n".join(lines),
                title="[error]⛔ Compliance Block[/error]",
                border_style="red",
            )
        )
    elif isinstance(exc, AuthError):
        err_console.print(
            f"[error]✗ Authentication failed:[/error] {exc}\n"
            "Run [bold]clienthunter init[/bold] to log in again."
        )
    elif isinstance(exc, NotFoundError):
        err_console.print(f"[error]✗ Not found:[/error] {exc}")
    elif isinstance(exc, RateLimitError):
        err_console.print(
            f"[warning]⚠ Rate limited.[/warning] {exc}\n"
            "The SDK already retried with back-off — please wait before trying again."
        )
    elif isinstance(exc, ValidationError):
        err_console.print(f"[error]✗ Validation error:[/error] {exc}")
    elif isinstance(exc, APIError):
        err_console.print(
            f"[error]✗ API error (HTTP {exc.status_code}):[/error] {exc.detail}\n"
            "If this persists, check [bold]clienthunter status[/bold] or file a bug."
        )
    else:
        err_console.print(f"[error]✗ Unexpected error:[/error] {exc}")

    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# JSON output helper
# ---------------------------------------------------------------------------


def print_json(data: Any) -> None:
    """Serialise *data* to pretty JSON on stdout."""
    console.print_json(json.dumps(data, default=str))
