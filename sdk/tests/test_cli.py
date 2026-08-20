"""CLI unit tests using Typer's CliRunner.

Covers:
- `version` prints the correct version string and --json variant
- `init` verifies connectivity, writes config on success
- `run` wizard YES/NO past-clients branches hit correct endpoints
- `status --strategy --json` emits valid JSON
- `status` all-strategies degrades gracefully when backend endpoint is missing
- `leads list --json` emits valid JSON
- `campaign pause/resume --yes` calls correct endpoints
- `serve` fails with a clear message when Docker is absent
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from clienthunter._version import __version__
from clienthunter.cli import app
from clienthunter.exceptions import APIError, AuthError, ComplianceError

from tests.conftest import (
    FAKE_STRATEGY_ID, STRATEGY_STATUS_RESP, CAMPAIGN_RESP,
    LEAD_LIST_RESP, PRODUCT_RESP, STRATEGY_RESP,
)

runner = CliRunner()  # mix_stderr not available in all typer versions

# ---------------------------------------------------------------------------
# Helper — patch the client factory in every CLI submodule
# ---------------------------------------------------------------------------

from contextlib import contextmanager


@contextmanager
def _patch_client(mock_ch):
    """Patch _get_client in every CLI submodule that imports it.

    ``from clienthunter.cli._console import _get_client`` creates a local
    binding per module.  We must patch EACH module's reference, not just the
    source module's attribute.
    """
    targets = [
        "clienthunter.cli._init._get_client",
        "clienthunter.cli._run._get_client",
        "clienthunter.cli._status._get_client",
        "clienthunter.cli._leads._get_client",
        "clienthunter.cli._campaign._get_client",
    ]
    with patch(targets[0], return_value=mock_ch), \
         patch(targets[1], return_value=mock_ch), \
         patch(targets[2], return_value=mock_ch), \
         patch(targets[3], return_value=mock_ch), \
         patch(targets[4], return_value=mock_ch):
        yield


# ---------------------------------------------------------------------------
# version command
# ---------------------------------------------------------------------------


def test_version_human():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_version_json():
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["version"] == __version__


# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


def test_init_success(tmp_path, mock_ch):
    """init writes config when health + login succeed."""
    config_dir = tmp_path / ".clienthunter"
    config_file = config_dir / "config.toml"

    with _patch_client(mock_ch), \
         patch("clienthunter.config._CONFIG_DIR", config_dir), \
         patch("clienthunter.config._CONFIG_FILE", config_file):
        result = runner.invoke(app, ["init"], input="y\n\nn\nme@test.com\npassword123\n")

    assert result.exit_code == 0, result.output
    assert "Connected" in result.output or "✓" in result.output
    mock_ch.ping.assert_called_once()


def test_init_auth_failure(mock_ch):
    """init exits 1 and shows a message when auth fails."""
    mock_ch.auth.login.side_effect = AuthError("invalid credentials")
    with _patch_client(mock_ch) as _:
        result = runner.invoke(app, ["init"], input="y\n\nn\nbad@test.com\nwrongpass\n")
    assert result.exit_code == 1


def test_init_connection_failure(mock_ch):
    """init exits 1 when the backend is unreachable."""
    mock_ch.ping.side_effect = APIError("connection refused")
    with _patch_client(mock_ch) as _:
        result = runner.invoke(app, ["init"], input="y\n\nn\nme@test.com\npassword\n")
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# run command — YES past clients branch
# ---------------------------------------------------------------------------


def test_run_with_past_clients(mock_ch):
    """YES path: creates product, adds past clients, creates strategy."""
    # Wizard input: name, description, type, email, has_clients=y,
    #               client details, acquisition story, no more clients
    wizard_input = (
        "My SaaS\n"                          # product name
        "Project management tool\n"          # description
        "product\n"                          # type
        "me@test.com\n"                      # email
        "y\n"                               # has past clients?
        "Acme Corp, Head of Engineering\n"  # client details
        "Found via LinkedIn\n"              # acquisition story
        "n\n"                               # add another client?
    )
    with _patch_client(mock_ch):
        result = runner.invoke(app, ["run", "--no-follow"], input=wizard_input)

    assert result.exit_code == 0, result.output
    mock_ch.products.create.assert_called_once()
    mock_ch.products.add_past_clients.assert_called_once()
    mock_ch.strategies.create.assert_called_once()


def test_run_no_past_clients(mock_ch):
    """NO path: creates product, skips past clients, creates strategy."""
    wizard_input = (
        "My SaaS\n"
        "Project management tool\n"
        "product\n"
        "me@test.com\n"
        "n\n"   # no past clients
    )
    with _patch_client(mock_ch):
        result = runner.invoke(app, ["run", "--no-follow"], input=wizard_input)

    assert result.exit_code == 0, result.output
    mock_ch.products.create.assert_called_once()
    mock_ch.products.add_past_clients.assert_not_called()
    mock_ch.strategies.create.assert_called_once()


def test_run_with_product_id(mock_ch):
    """--product-id skips product creation."""
    from clienthunter.models import Strategy
    mock_ch.strategies.create.return_value = Strategy(**STRATEGY_RESP)

    with _patch_client(mock_ch):
        result = runner.invoke(app, ["run", "--product-id", "abc-123", "--no-follow"])

    assert result.exit_code == 0, result.output
    mock_ch.products.create.assert_not_called()
    mock_ch.strategies.create.assert_called_once()


def test_run_compliance_error_shown_clearly(mock_ch):
    """ComplianceError shows the rule and remediation in the output."""
    mock_ch.strategies.create.side_effect = ComplianceError(
        "gdpr", "EU target requires lawful basis"
    )
    wizard_input = "My SaaS\nTool\nproduct\nme@test.com\nn\n"
    with _patch_client(mock_ch):
        result = runner.invoke(app, ["run", "--no-follow"], input=wizard_input)

    assert result.exit_code == 1
    # Compliance rule should appear in stderr
    assert "gdpr" in result.stderr or "gdpr" in result.output


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


def test_status_single_strategy_json(mock_ch):
    """--strategy ID --json emits valid JSON to stdout."""
    with _patch_client(mock_ch):
        result = runner.invoke(
            app, ["status", "--strategy", FAKE_STRATEGY_ID, "--json"]
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["id"] == FAKE_STRATEGY_ID
    assert "progress" in data


def test_status_single_strategy_human(mock_ch):
    """Human-readable detail view renders without error."""
    with _patch_client(mock_ch):
        result = runner.invoke(app, ["status", "--strategy", FAKE_STRATEGY_ID])
    assert result.exit_code == 0, result.output
    assert FAKE_STRATEGY_ID in result.output


def test_status_all_json(mock_ch):
    """All-strategies view --json emits a JSON list."""
    with _patch_client(mock_ch):
        result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 1


def test_status_all_degrades_when_endpoint_missing(mock_ch):
    """If GET /strategies returns 404/405 the CLI prints a helpful message."""
    mock_ch.strategies.list.side_effect = APIError("not found", status_code=404)
    with _patch_client(mock_ch):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "backend_additions" in result.stderr or "backend_additions" in result.output


# ---------------------------------------------------------------------------
# leads commands
# ---------------------------------------------------------------------------


def test_leads_list_json(mock_ch):
    """`leads list --json` produces valid JSON."""
    with _patch_client(mock_ch):
        result = runner.invoke(
            app, ["leads", "list", "--strategy", FAKE_STRATEGY_ID, "--json"]
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "items" in data
    assert data["total"] == 1


def test_leads_list_human(mock_ch):
    """Human table renders without error and shows core lead data."""
    with _patch_client(mock_ch):
        result = runner.invoke(
            app, ["leads", "list", "--strategy", FAKE_STRATEGY_ID]
        )
    assert result.exit_code == 0, result.output
    # Name and status are in the first columns (always visible regardless of terminal width)
    assert "Jane Smith" in result.output
    assert "verified" in result.output


def test_leads_export_csv(mock_ch, tmp_path):
    """Export writes a valid CSV file."""
    out = tmp_path / "leads.csv"
    with _patch_client(mock_ch):
        result = runner.invoke(
            app, ["leads", "export", "--strategy", FAKE_STRATEGY_ID,
                  "--output", str(out)]
        )
    assert result.exit_code == 0, result.output
    import csv
    rows = list(csv.DictReader(out.read_text().splitlines()))
    assert len(rows) == 1
    assert rows[0]["email"] == "jane@acme.com"


# ---------------------------------------------------------------------------
# campaign commands
# ---------------------------------------------------------------------------


def test_campaign_pause(mock_ch):
    """`campaign pause --yes` calls ch.campaigns.pause."""
    with _patch_client(mock_ch):
        result = runner.invoke(
            app, ["campaign", "pause", "--strategy", FAKE_STRATEGY_ID, "--yes"]
        )
    assert result.exit_code == 0, result.output
    mock_ch.campaigns.pause.assert_called_once_with(FAKE_STRATEGY_ID)


def test_campaign_resume(mock_ch):
    """`campaign resume --yes` calls ch.campaigns.resume."""
    with _patch_client(mock_ch):
        result = runner.invoke(
            app, ["campaign", "resume", "--strategy", FAKE_STRATEGY_ID, "--yes"]
        )
    assert result.exit_code == 0, result.output
    mock_ch.campaigns.resume.assert_called_once_with(FAKE_STRATEGY_ID)


def test_campaign_pause_json(mock_ch):
    """`campaign pause --yes --json` emits valid JSON."""
    with _patch_client(mock_ch):
        result = runner.invoke(
            app, ["campaign", "pause", "--strategy", FAKE_STRATEGY_ID, "--yes", "--json"]
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "campaign_state" in data


# ---------------------------------------------------------------------------
# serve — Docker absent
# ---------------------------------------------------------------------------


def test_serve_exits_clearly_when_docker_missing():
    """When Docker is not installed, serve prints a helpful message and exits 1."""
    with patch("clienthunter.cli._serve._check_docker", return_value=False):
        result = runner.invoke(app, ["serve"])

    assert result.exit_code == 1
    # Must mention Docker installation, not suggest bypasses
    combined = (result.output or "") + (result.stderr or "")
    assert "docker" in combined.lower()
    assert "install" in combined.lower() or "docs.docker.com" in combined.lower()
    # Must NOT suggest bypassing Docker or the compliance wrapper
    assert "bypass" not in combined.lower()
