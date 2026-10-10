#!/usr/bin/env python3
"""PreToolUse hook (Edit/Write/MultiEdit/NotebookEdit): sealed files stay sealed.

CLAUDE.md seals the release gate's own definition: a threshold, seal or
baseline change must be its own reviewed PR with a written justification,
never a side effect of making something pass. This hook enforces the
"own PR" part mechanically: edits to the files below are allowed only on a
branch whose name starts with `gate/` or `claude/gate-`, so a gate change
can never ride along inside a feature branch.

Protected:
  - evals/registry.yaml, evals/compliance_testset.yaml, evals/baseline.json
  - the sealed compliance test files listed in evals/compliance_testset.yaml
  - .github/workflows/* (CI definitions, including eval-gate.yml)
  - gate infrastructure: .githooks/*, .claude/hooks/*, .claude/settings.json,
    scripts/gate/required_checks.txt

Limit: this sees Claude's file tools only. A shell `sed -i` is not caught;
the PR diff and review are the backstop. Exit 2 = block; 0 = no decision.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ALLOWED_BRANCH_PREFIXES = ("gate/", "claude/gate-")
SEALED_FILES = {
    "evals/registry.yaml",
    "evals/compliance_testset.yaml",
    "evals/baseline.json",
    ".claude/settings.json",
    "scripts/gate/required_checks.txt",
}
SEALED_DIRS = (".github/workflows/", ".githooks/", ".claude/hooks/")


def _git(cwd: str | None, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=cwd or None, capture_output=True,
                           text=True, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def sealed_test_files(root: Path) -> set[str]:
    path = root / "evals" / "compliance_testset.yaml"
    files: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("- ") and line.endswith(".py"):
                files.add(line[2:].strip())
    except OSError:
        pass
    return files


def is_sealed(rel: str, root: Path) -> bool:
    return (rel in SEALED_FILES or rel.startswith(SEALED_DIRS)
            or rel in sealed_test_files(root))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return 0
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        return 0
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return 0
    root = Path(top).resolve()
    path = Path(target)
    if not path.is_absolute():
        path = Path(cwd) / path
    try:
        rel = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return 0  # outside this repository
    if not is_sealed(rel, root):
        return 0
    branch = _git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD") or ""
    if branch.startswith(ALLOWED_BRANCH_PREFIXES):
        return 0
    print(f"Blocked by .claude/hooks/protect_sealed.py: {rel} is a sealed gate file. "
          f"Change it only in its own PR on a branch named gate/... or claude/gate-..., "
          f"with a written justification (CLAUDE.md, 'Sealed files').", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
