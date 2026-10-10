#!/usr/bin/env python3
"""PreToolUse hook: block every way of putting code on master except safe_merge.

Claude Code runs this before each Bash call and each MCP tool call whose name
contains "merge" (.claude/settings.json). It reads the hook JSON on stdin and
exits 2 with a reason on stderr to block the call; exit 0 means "no decision"
and the normal permission flow continues.

Blocked:
  - `gh pr merge` (bypasses the checks safe_merge enforces)
  - any REST call to .../pulls/<n>/merge (curl or `gh api`)
  - `git push` whose destination is master or main, including HEAD:master,
    +master and refs/heads/master, and a bare `git push` while on master/main
  - MCP tools such as mcp__github__merge_pull_request

Allowed: scripts/gate/safe_merge.sh / safe_merge.py. They call the GitHub API
from their own subprocess, which Claude Code does not route through hooks.

Why a hook and not a CLAUDE.md line: CLAUDE.md is advice the model can skip;
a hook runs every time. Policy: docs/program/DECISIONS.md MERGE-B.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys

PROTECTED_BRANCHES = ("master", "main")
SAFE_MERGE_HINT = "Merge only with: scripts/gate/safe_merge.sh <PR number> (policy MERGE-B)."

_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")
_PR_MERGE_API = re.compile(r"pulls/\d+/merge\b")


def _block(reason: str) -> int:
    print(f"Blocked by .claude/hooks/guard_merge.py: {reason} {SAFE_MERGE_HINT}", file=sys.stderr)
    return 2


def _current_branch(cwd: str | None) -> str | None:
    try:
        # symbolic-ref also works on a branch with no commits yet.
        result = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                                cwd=cwd or None, capture_output=True, text=True,
                                check=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _push_targets_protected(tokens: list[str], cwd: str | None) -> bool:
    """tokens start right after `git push`."""
    positional = [t for t in tokens if not t.startswith("-")]
    refspecs = positional[1:]  # first positional is the remote
    if not refspecs:
        # `git push` / `git push origin` push the current branch.
        return _current_branch(cwd) in PROTECTED_BRANCHES
    for spec in refspecs:
        dest = spec.lstrip("+").split(":")[-1]
        dest = dest.removeprefix("refs/heads/")
        if dest in PROTECTED_BRANCHES:
            return True
        if ":" not in spec and spec.lstrip("+") == "HEAD":
            if _current_branch(cwd) in PROTECTED_BRANCHES:
                return True
    return False


def check_bash(command: str, cwd: str | None) -> str | None:
    """Return a block reason, or None if the command may run."""
    for segment in _SEGMENT_SPLIT.split(command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()
        # Drop leading VAR=value assignments.
        while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
            tokens.pop(0)
        if not tokens:
            continue

        if tokens[0] == "gh" and tokens[1:3] == ["pr", "merge"]:
            return "`gh pr merge` skips the merge gate."
        if tokens[0] in ("gh", "curl", "http", "wget") and _PR_MERGE_API.search(segment):
            return "direct calls to the pull-request merge API skip the merge gate."
        if tokens[0] == "git":
            # Skip git global options such as -C <dir> or -c key=value.
            i = 1
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 2 if tokens[i] in ("-C", "-c") else 1
            if i < len(tokens) and tokens[i] == "push":
                if _push_targets_protected(tokens[i + 1:], cwd):
                    return "pushing directly to master/main is not allowed."
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # not our input; no decision
    tool = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}

    if tool.startswith("mcp__") and "merge" in tool.lower():
        return _block(f"the MCP tool {tool} merges without the merge gate.")
    if tool == "Bash":
        reason = check_bash(str(tool_input.get("command", "")), payload.get("cwd"))
        if reason:
            return _block(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
