#!/usr/bin/env python3
"""PreToolUse hook (Bash): no unchecked pushes and no skipped git hooks.

Blocks, in Claude Code sessions on this repo:
  - `git commit --no-verify` / `git commit -n`
  - `git push --no-verify`
  - `git push` of the checked-out HEAD when its tree has no quick-gate stamp
    (<git-common-dir>/leadpilot-gate/<tree>.ok, written by
    scripts/gate/quick_gate.py on a clean, fully passing run)

Not this hook's job: pushes to master/main (guard_merge.py blocks those).
Branch deletions (`--delete`, `:branch`) and `--dry-run` pushes are allowed.

Why: the pre-push git hook only runs where `core.hooksPath` is configured,
and a fresh cloud clone does not have it. This hook gives agents the same
rule without that setup. Exit 2 = block (reason on stderr); 0 = no decision.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")


def _git(cwd: str | None, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=cwd or None, capture_output=True,
                           text=True, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def stamp_exists(cwd: str | None) -> bool:
    tree = _git(cwd, "rev-parse", "HEAD^{tree}")
    common = _git(cwd, "rev-parse", "--git-common-dir")
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if not (tree and common and top):
        return True  # not a git repo we can read: no decision
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = Path(top) / common_path
    return (common_path / "leadpilot-gate" / f"{tree}.ok").is_file()


def _git_subcommand(tokens: list[str]) -> tuple[str | None, list[str]]:
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        i += 2 if tokens[i] in ("-C", "-c") else 1
    if i >= len(tokens):
        return None, []
    return tokens[i], tokens[i + 1:]


def check_bash(command: str, cwd: str | None) -> str | None:
    for segment in _SEGMENT_SPLIT.split(command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()
        while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
            tokens.pop(0)
        if not tokens or tokens[0] != "git":
            continue
        sub, rest = _git_subcommand(tokens)
        if sub == "commit" and ("--no-verify" in rest or "-n" in rest
                                or any(re.fullmatch(r"-[a-zA-Z]*n[a-zA-Z]*", t) for t in rest
                                       if not t.startswith("--"))):
            return "`git commit --no-verify` skips the repo's git hooks."
        if sub == "push":
            if "--no-verify" in rest:
                return "`git push --no-verify` skips the pre-push quick gate."
            if "--dry-run" in rest or "-n" in rest:
                continue
            positional = [t for t in rest if not t.startswith("-")]
            if "--delete" in rest or "-d" in rest or any(p.startswith(":") for p in positional[1:]):
                continue
            if not stamp_exists(cwd):
                return ("this commit has no quick-gate stamp. Run scripts/gate/quick_gate.sh "
                        "on a clean, committed tree, then push.")
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    reason = check_bash(str((payload.get("tool_input") or {}).get("command", "")), payload.get("cwd"))
    if reason:
        print(f"Blocked by .claude/hooks/require_gate.py: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
