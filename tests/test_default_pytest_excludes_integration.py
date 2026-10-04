"""F-QA-01 -- a bare `pytest` must not co-collect tests/integration.

The integration directory needs real Postgres/Redis and leaves state behind;
collected alongside the offline suite it produced 9 order-dependent WhatsApp
failures that pass per-file. The eval gate dodges this with an explicit
`--ignore=tests/integration`; a developer running plain `pytest` got the
failures. The default is now the offline suite, and the integration directory
is still runnable when named explicitly.
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _collect(*args: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode in (0, 5), result.stdout[-2000:] + result.stderr[-2000:]
    return [line for line in result.stdout.splitlines() if "::" in line]


def test_bare_pytest_does_not_collect_the_integration_directory():
    nodes = _collect()
    assert nodes, "bare pytest collected nothing"
    leaked = [n for n in nodes if n.startswith("tests/integration/")]
    assert leaked == [], f"{len(leaked)} integration tests collected by default"


def test_the_integration_directory_is_still_runnable_when_named():
    nodes = _collect("tests/integration")
    assert any(n.startswith("tests/integration/") for n in nodes)
