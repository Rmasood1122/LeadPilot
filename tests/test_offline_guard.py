"""The offline suite is enforced: a test that reaches the network fails.

BEFORE: nothing enforced "offline". The app swallows network errors by design,
so tests that ran the pipeline task fetched news.google.com, called
api.apollo.io and (through a get_client bound before the guard was installed)
sent a real request to api.anthropic.com -- and still passed.

Pinned here: the guard refuses non-loopback connections, allows loopback (the
local Redis/Postgres the integration suite uses), and FAILS the test even when
the application caught the error.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.services import anthropic_client, market_intel


def test_external_connection_is_refused(no_external_network):
    with pytest.raises(OSError, match="real network connection to example.com:443"):
        socket.create_connection(("example.com", 443), timeout=1)
    with pytest.raises(OSError):
        socket.getaddrinfo("api.anthropic.com", 443)
    assert no_external_network == ["example.com:443", "api.anthropic.com:443"]
    no_external_network.clear()  # this test made the attempts on purpose


def test_loopback_is_allowed(no_external_network):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
    assert no_external_network == []


def test_market_intel_fetchers_are_stubbed():
    with pytest.raises(RuntimeError, match="market-intel"):
        market_intel.fetch_google_news("fire protection")
    with pytest.raises(RuntimeError, match="market-intel"):
        market_intel._apollo_org_search(["fire protection"])


def test_every_from_import_of_get_client_is_refused():
    import app.services.icp_extraction as icp  # binds get_client by name

    for module in (anthropic_client, icp):
        with pytest.raises(RuntimeError, match="real Anthropic call"):
            module.get_client()


def test_a_swallowed_network_error_still_fails_the_test(tmp_path):
    # Run a throwaway test in a subprocess: it reaches for the network and
    # catches the error, as the application does. It must FAIL anyway.
    tests_dir = Path(__file__).parent
    probe = tests_dir / f"_offline_probe_{tmp_path.name}.py"
    probe.write_text(textwrap.dedent("""
        import socket

        def test_swallows_a_network_error():
            try:
                socket.create_connection(("example.com", 80), timeout=1)
            except OSError:
                pass
    """))
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(probe), "-q", "-p", "no:cacheprovider"],
            cwd=tests_dir.parent, capture_output=True, text=True, timeout=120)
    finally:
        probe.unlink(missing_ok=True)
    assert result.returncode != 0, result.stdout
    assert "the offline suite reached for the network: example.com:80" in result.stdout
