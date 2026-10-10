"""Local gate tooling (Phase 1 item 1.5): quick gate, secret scanner, pre-push
hook, and the Claude Code hooks require_gate / protect_sealed / stop_check.

Production scenario: a change is pushed without the cheap checks (a leaked
key, a broken sealed compliance test), a gate file is edited inside a feature
branch to make something pass, or an agent ends its turn with unchecked code.
Each test drives the real script against a throwaway git repository: offline,
no network, no GitHub.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "gate"
HOOKS = ROOT / ".claude" / "hooks"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scan_secrets = _load("gate_scan_secrets_t", GATE / "scan_secrets.py")
quick_gate = _load("gate_quick_gate_t", GATE / "quick_gate.py")

FAKE_ANTHROPIC = "sk-ant-api03-" + "A1b2" * 12        # built, never a literal key
FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo on master with origin/master set, then a feature branch."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "master")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    (r / "evals").mkdir()
    (r / "evals" / "compliance_testset.yaml").write_text(
        "files:\n  - tests/test_compliance.py\n", encoding="utf-8")
    (r / "README.md").write_text("x\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    _git(r, "update-ref", "refs/remotes/origin/master", "HEAD")
    _git(r, "checkout", "-q", "-b", "feature/x")
    return r


def _stamp(repo: Path) -> Path:
    tree = _git(repo, "rev-parse", "HEAD^{tree}")
    common = Path(_git(repo, "rev-parse", "--git-common-dir"))
    common = common if common.is_absolute() else repo / common
    return common / "leadpilot-gate" / f"{tree}.ok"


def _commit(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"add {rel}")


def _hook(script: str, payload, cwd: Path | None = None) -> int:
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOKS / script)], input=data, text=True,
                          capture_output=True, cwd=cwd, timeout=30).returncode


# --------------------------------------------------------------- scan_secrets

def _diff(file: str, lines: list[str], start: int = 1) -> str:
    body = "\n".join(lines)
    return f"+++ b/{file}\n@@ -0,0 +{start},{len(lines)} @@\n{body}\n"


def test_scanner_flags_added_key_with_file_and_line():
    findings = scan_secrets.scan_diff(_diff("app/x.py", ["+ok = 1", f"+KEY = '{FAKE_ANTHROPIC}'"], 10))
    assert [(f.file, f.line, f.kind) for f in findings] == [("app/x.py", 11, "Anthropic API key")]


def test_scanner_ignores_removed_lines_and_allow_marker():
    diff = _diff("a.py", [f"-OLD = '{FAKE_AWS}'", f"+K = '{FAKE_AWS}'  # gate: allow-secret"])
    assert scan_secrets.scan_diff(diff) == []


@pytest.mark.parametrize("url,flagged", [
    ("postgresql://user:hunter2pass@ep-cool.neon.tech/db", True),  # gate: allow-secret
    ("rediss://default:abcdef123456@x.upstash.io:6379", True),  # gate: allow-secret
    ("postgresql://leadpilot:leadpilot@localhost:5433/clienthunter_test", False),
])
def test_scanner_database_urls(url, flagged):
    assert bool(scan_secrets.scan_diff(_diff("c.py", [f"+URL = '{url}'"]))) is flagged


# ----------------------------------------------------------- quick_gate units

@pytest.mark.parametrize("path,module", [
    ("app/services/foo.py", "app.services.foo"),
    ("app/api/__init__.py", "app.api"),
    ("tests/test_x.py", None),
    ("frontend/src/a.ts", None),
])
def test_module_name(path, module):
    assert quick_gate.module_name(path) == module


def test_select_tests_finds_importers_changed_tests_and_sealed(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "compliance_testset.yaml").write_text(
        "files:\n  - tests/test_compliance.py\n", encoding="utf-8")
    (tmp_path / "tests" / "test_compliance.py").write_text("", encoding="utf-8")
    (tmp_path / "tests" / "test_a.py").write_text("from app.services import foo\n", encoding="utf-8")
    (tmp_path / "tests" / "test_b.py").write_text("import app.services.foo as f\n", encoding="utf-8")
    (tmp_path / "tests" / "test_c.py").write_text("from app.services import foobar\n", encoding="utf-8")
    (tmp_path / "tests" / "test_new.py").write_text("", encoding="utf-8")
    selected = quick_gate.select_tests(
        tmp_path, ["app/services/foo.py", "tests/test_new.py", "tests/integration/test_pg.py"])
    assert selected == ["tests/test_a.py", "tests/test_b.py", "tests/test_new.py",
                        "tests/test_compliance.py"]


def test_quick_gate_secret_step_fails_on_a_committed_key(repo, monkeypatch):
    shutil.copytree(GATE, repo / "scripts" / "gate")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "tools")
    _git(repo, "update-ref", "refs/remotes/origin/master", "HEAD")
    _commit(repo, "app/config_extra.py", f"KEY = '{FAKE_ANTHROPIC}'\n")
    monkeypatch.chdir(repo)
    assert quick_gate.main(["--steps", "secrets,syntax"]) == 1
    assert not _stamp(repo).exists()


def _all_pass(root, base, steps):
    return [quick_gate.StepResult(s, True, "ok") for s in steps], _git(root, "rev-parse", base)


def test_full_pass_on_clean_tree_writes_stamp(repo, monkeypatch):
    monkeypatch.setattr(quick_gate, "run", _all_pass)
    monkeypatch.chdir(repo)
    assert quick_gate.main([]) == 0
    assert _stamp(repo).is_file()


def test_pass_with_dirty_tree_or_partial_steps_does_not_stamp(repo, monkeypatch):
    monkeypatch.setattr(quick_gate, "run", _all_pass)
    monkeypatch.chdir(repo)
    assert quick_gate.main(["--steps", "secrets"]) == 0
    assert not _stamp(repo).exists()
    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    assert quick_gate.main([]) == 0
    assert not _stamp(repo).exists()


def test_unknown_step_is_a_usage_error():
    with pytest.raises(SystemExit):
        quick_gate.main(["--steps", "nope"])


# ------------------------------------------------------------------ pre-push

def _pre_push(repo: Path, line: str, py: str | None = None) -> int:
    env = {**os.environ}
    if py:
        env["PYTHON"] = py
    return subprocess.run(["sh", str(ROOT / ".githooks" / "pre-push"), "origin", "x"],
                          cwd=repo, input=line + "\n", text=True, capture_output=True,
                          env=env, timeout=60).returncode


def _ref_line(repo: Path, remote_ref: str) -> str:
    sha = _git(repo, "rev-parse", "HEAD")
    return f"refs/heads/feature/x {sha} {remote_ref} {'0' * 40}"


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh not installed")
def test_pre_push_refuses_master_even_with_stamp(repo):
    _stamp(repo).parent.mkdir(parents=True, exist_ok=True)
    _stamp(repo).write_text("ok", encoding="utf-8")
    assert _pre_push(repo, _ref_line(repo, "refs/heads/master")) == 1
    assert _pre_push(repo, _ref_line(repo, "refs/heads/main")) == 1


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh not installed")
def test_pre_push_accepts_stamped_commit(repo):
    _stamp(repo).parent.mkdir(parents=True, exist_ok=True)
    _stamp(repo).write_text("ok", encoding="utf-8")
    assert _pre_push(repo, _ref_line(repo, "refs/heads/feature/x")) == 0


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh not installed")
@pytest.mark.parametrize("stub_exit,expected", [(0, 0), (1, 1)])
def test_pre_push_runs_quick_gate_for_unstamped_head(repo, stub_exit, expected):
    stub = repo / "scripts" / "gate" / "quick_gate.py"
    stub.parent.mkdir(parents=True)
    tree = _git(repo, "rev-parse", "HEAD^{tree}")
    stub.write_text(
        "import pathlib, subprocess, sys\n"
        f"if {stub_exit}: sys.exit({stub_exit})\n"
        "c = subprocess.run(['git','rev-parse','--git-common-dir'],capture_output=True,text=True).stdout.strip()\n"
        f"p = pathlib.Path(c) / 'leadpilot-gate' / '{tree}.ok'\n"
        "p.parent.mkdir(parents=True, exist_ok=True); p.write_text('ok')\n",
        encoding="utf-8")
    assert _pre_push(repo, _ref_line(repo, "refs/heads/feature/x"), py=sys.executable) == expected


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh not installed")
def test_pre_push_refuses_unstamped_commit_that_is_not_head(repo):
    old = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "more.txt", "y\n")
    line = f"refs/heads/other {old} refs/heads/other {'0' * 40}"
    assert _pre_push(repo, line) == 1


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh not installed")
def test_pre_push_allows_branch_deletion(repo):
    assert _pre_push(repo, f"(delete) {'0' * 40} refs/heads/old-branch {'1' * 40}") == 0


# -------------------------------------------------------------- require_gate

def _bash_payload(command: str, cwd: Path) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


@pytest.mark.parametrize("command", [
    "git commit --no-verify -m x",
    "git commit -n -m x",
    "git commit -anm x",
    "git push --no-verify origin feature/x",
])
def test_require_gate_blocks_hook_skipping(repo, command):
    assert _hook("require_gate.py", _bash_payload(command, repo), cwd=repo) == 2


def test_require_gate_blocks_unstamped_push_and_allows_stamped(repo):
    payload = _bash_payload("git push -u origin feature/x", repo)
    assert _hook("require_gate.py", payload, cwd=repo) == 2
    _stamp(repo).parent.mkdir(parents=True, exist_ok=True)
    _stamp(repo).write_text("ok", encoding="utf-8")
    assert _hook("require_gate.py", payload, cwd=repo) == 0


@pytest.mark.parametrize("command", [
    "git push origin --delete old-branch",
    "git push origin :old-branch",
    "git push --dry-run origin feature/x",
    "git commit -m 'fix -n handling'",
    "git status",
    "ls -la",
])
def test_require_gate_allows(repo, command):
    assert _hook("require_gate.py", _bash_payload(command, repo), cwd=repo) == 0


# ------------------------------------------------------------ protect_sealed

def _edit(path: str, cwd: Path) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": path}, "cwd": str(cwd)}


@pytest.mark.parametrize("rel", [
    "evals/registry.yaml", "evals/baseline.json", "evals/compliance_testset.yaml",
    "tests/test_compliance.py", ".github/workflows/eval-gate.yml",
    ".claude/settings.json", ".claude/hooks/guard_merge.py", ".githooks/pre-push",
    "scripts/gate/required_checks.txt",
])
def test_protect_sealed_blocks_on_feature_branch(repo, rel):
    assert _hook("protect_sealed.py", _edit(str(repo / rel), repo), cwd=repo) == 2


@pytest.mark.parametrize("branch", ["gate/raise-floor", "claude/gate-baseline-refresh"])
def test_protect_sealed_allows_on_gate_branch(repo, branch):
    _git(repo, "checkout", "-q", "-b", branch)
    assert _hook("protect_sealed.py", _edit(str(repo / "evals/registry.yaml"), repo), cwd=repo) == 0


def test_protect_sealed_ignores_ordinary_and_outside_files(repo, tmp_path):
    assert _hook("protect_sealed.py", _edit(str(repo / "app/x.py"), repo), cwd=repo) == 0
    assert _hook("protect_sealed.py", _edit("app/x.py", repo), cwd=repo) == 0
    assert _hook("protect_sealed.py", _edit(str(tmp_path / "elsewhere.txt"), repo), cwd=repo) == 0
    assert _hook("protect_sealed.py", {"tool_name": "Read", "tool_input": {}}, cwd=repo) == 0


# ---------------------------------------------------------------- stop_check

def _stop(repo: Path, active: bool = False) -> int:
    return _hook("stop_check.py", {"hook_event_name": "Stop", "stop_hook_active": active,
                                   "cwd": str(repo)}, cwd=repo)


def test_stop_check_blocks_unchecked_code_once(repo):
    (repo / "app").mkdir()
    (repo / "app" / "x.py").write_text("x = 1\n", encoding="utf-8")
    assert _stop(repo) == 2
    assert _stop(repo, active=True) == 0  # never loops


def test_stop_check_allows_stamped_commit(repo):
    _commit(repo, "app/x.py", "x = 1\n")
    assert _stop(repo) == 2
    _stamp(repo).parent.mkdir(parents=True, exist_ok=True)
    _stamp(repo).write_text("ok", encoding="utf-8")
    assert _stop(repo) == 0


def test_stop_check_ignores_docs_only_and_master(repo):
    _commit(repo, "docs/note.md", "n\n")
    assert _stop(repo) == 0
    _git(repo, "checkout", "-q", "master")
    (repo / "app").mkdir()
    (repo / "app" / "y.py").write_text("y = 1\n", encoding="utf-8")
    assert _stop(repo) == 0
