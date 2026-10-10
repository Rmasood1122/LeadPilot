#!/usr/bin/env python3
"""Stop hook: don't end a turn with unchecked code changes.

If the branch changes code (app/, alembic/, evals/, tests/, scripts/,
frontend/src/) relative to origin/master and the current commit has no
quick-gate stamp, or such changes are still uncommitted, Claude is asked to
continue once and run scripts/gate/quick_gate.sh before finishing.

It never loops: when the stop was already caused by this hook
(`stop_hook_active` in the hook input), it lets the turn end. It never blocks
on master, outside a git repo, or for docs-only changes.
Exit 2 = continue working (reason on stderr); 0 = allow the stop.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

GATED_PREFIXES = ("app/", "alembic/", "evals/", "tests/", "scripts/", "frontend/src/")


def _git(cwd: str | None, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=cwd or None, capture_output=True,
                           text=True, check=False, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def needs_gate(cwd: str | None) -> bool:
    branch = (_git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD") or "").strip()
    if not branch or branch in ("master", "main"):
        return False
    base = (_git(cwd, "merge-base", "HEAD", "origin/master") or "").strip()
    if not base:
        return False
    changed = set((_git(cwd, "diff", "--name-only", base) or "").split())
    changed |= set((_git(cwd, "ls-files", "--others", "--exclude-standard") or "").split())
    if not any(p.startswith(GATED_PREFIXES) for p in changed):
        return False
    if (_git(cwd, "status", "--porcelain") or "").strip():
        return True
    tree = (_git(cwd, "rev-parse", "HEAD^{tree}") or "").strip()
    common = (_git(cwd, "rev-parse", "--git-common-dir") or "").strip()
    top = (_git(cwd, "rev-parse", "--show-toplevel") or "").strip()
    common_path = Path(common) if Path(common).is_absolute() else Path(top) / common
    return not (common_path / "leadpilot-gate" / f"{tree}.ok").is_file()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("stop_hook_active"):
        return 0
    if needs_gate(payload.get("cwd")):
        print("Code changed on this branch and the current state has not passed the quick "
              "gate. Commit your work and run scripts/gate/quick_gate.sh, then report its "
              "result. If you are stopping to ask the user something, say so and stop.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
