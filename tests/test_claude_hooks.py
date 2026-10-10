""".claude/hooks/guard_merge.py — the Claude Code hook behind policy MERGE-B.

Production scenario: an agent (or a founder through an agent) merges a PR or
pushes straight to master without the merge gate. The hook runs before every
Bash call and every MCP "merge" tool call and must block those paths, while
leaving ordinary branch work and scripts/gate/safe_merge.sh alone. Each test
runs the real script as Claude Code does: hook JSON on stdin, exit code 2 =
blocked, 0 = no decision.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "guard_merge.py"


def _run_hook(payload, cwd: Path | None = None) -> subprocess.CompletedProcess:
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK)], input=data, text=True,
                          capture_output=True, cwd=cwd, timeout=30)


def _bash(command: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return _run_hook(payload, cwd=cwd)


@pytest.mark.parametrize("command", [
    "gh pr merge 47 --squash",
    "cd repo && gh pr merge 47",
    "gh api -X PUT repos/Owner/Repo/pulls/47/merge -f merge_method=squash",
    "curl -X PUT https://api.github.com/repos/Owner/Repo/pulls/47/merge",
    "git push origin master",
    "git push origin HEAD:master",
    "git push --force origin +master",
    "git push origin refs/heads/main",
    "git push origin feature:master",
    "git -C /tmp/x push origin master",
    "GIT_TRACE=1 git push origin master",
    "git push origin --delete master",
])
def test_blocked_commands(command):
    result = _bash(command)
    assert result.returncode == 2, (command, result.stderr)
    assert "safe_merge" in result.stderr


@pytest.mark.parametrize("command", [
    "scripts/gate/safe_merge.sh 47",
    "scripts/gate/safe_merge.sh 47 --dry-run",
    "git push -u origin claude/gate-safe-merge",
    "git push origin claude/master-notes",
    "git fetch origin master",
    "git merge origin/master",
    "gh api repos/Owner/Repo/pulls/47",
    "python3 evals/run_evals.py",
])
def test_allowed_commands(command):
    result = _bash(command)
    assert result.returncode == 0, (command, result.stderr)


def test_mcp_merge_tool_is_blocked():
    result = _run_hook({"tool_name": "mcp__github__merge_pull_request",
                        "tool_input": {"pull_number": 47}})
    assert result.returncode == 2


def test_unrelated_tools_are_not_touched():
    assert _run_hook({"tool_name": "Read", "tool_input": {"file_path": "x"}}).returncode == 0
    assert _run_hook({"tool_name": "mcp__github__create_pull_request",
                      "tool_input": {}}).returncode == 0


def test_malformed_input_makes_no_decision():
    assert _run_hook("not json").returncode == 0


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
@pytest.mark.parametrize("branch,expected", [("master", 2), ("feature/x", 0)])
def test_bare_push_depends_on_current_branch(tmp_path, branch, expected):
    subprocess.run(["git", "init", "-q", "-b", branch, str(tmp_path)], check=True)
    assert _bash("git push", cwd=tmp_path).returncode == expected
    assert _bash("git push origin", cwd=tmp_path).returncode == expected


def test_settings_wire_the_hook_for_bash_and_mcp_merge_tools():
    settings = json.loads((HOOK.parents[1] / "settings.json").read_text(encoding="utf-8"))
    matchers = {entry["matcher"]: entry["hooks"][0]["command"]
                for entry in settings["hooks"]["PreToolUse"]}
    assert "Bash" in matchers
    assert any(m.startswith("mcp__") and "erge" in m for m in matchers)
    assert all("guard_merge.py" in cmd for cmd in matchers.values())
