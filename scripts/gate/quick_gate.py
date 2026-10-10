#!/usr/bin/env python3
"""Quick gate: the fast local check that runs before every push.

WHAT IT IS FOR
--------------
Catch the cheap mistakes before they cost 9 billed CI minutes: a leaked key,
a syntax error, an undefined name, a second Alembic head, a broken sealed
compliance test, a failing test next to the code you changed, a TypeScript
error. It is NOT the release gate: CI (`eval-gate`, and the `verify-*` jobs)
remains the authority. `scripts/gate/full_gate.sh` runs what CI runs.

WHAT IT RUNS (against the diff from the merge-base with origin/master)
----------------------------------------------------------------------
  secrets     added lines scanned by scripts/gate/scan_secrets.py
  syntax      every changed .py file compiles
  lint        ruff, critical rules only (E9,F63,F7,F82), on changed .py files
  migrations  Alembic has exactly one head
  registry    evals/tools/registry_lint.py
  tests       changed test files + tests that import changed app modules +
              the sealed compliance files (evals/compliance_testset.yaml)
  frontend    type-check, lint, unit tests -- only if frontend/ changed

On success with a clean working tree it writes a stamp,
<git-common-dir>/leadpilot-gate/<tree-sha>.ok. The pre-push hook and the
Claude Code require_gate hook accept a push only when the pushed commit's
tree has a stamp, so the stamp proves THIS exact content passed.

Usage: scripts/gate/quick_gate.sh [--base origin/master] [--steps a,b,...]
Exit 0 = all selected steps passed, 1 = something failed.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ALL_STEPS = ("secrets", "syntax", "lint", "migrations", "registry", "tests", "frontend")
RUFF_CRITICAL = "E9,F63,F7,F82"
MAX_SELECTED_TEST_FILES = 60


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str
    seconds: float = 0.0


def _git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def repo_root() -> Path:
    return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())


def stamp_path(root: Path, tree: str) -> Path:
    common = Path(_git(root, "rev-parse", "--git-common-dir").strip())
    if not common.is_absolute():
        common = root / common
    return common / "leadpilot-gate" / f"{tree}.ok"


def merge_base(root: Path, base: str) -> str:
    out = _git(root, "merge-base", "HEAD", base, check=False).strip()
    if not out:
        raise RuntimeError(f"no merge-base between HEAD and {base}; run `git fetch origin master`")
    return out


def changed_files(root: Path, base_sha: str) -> list[str]:
    """Committed changes since the merge-base plus uncommitted and untracked ones."""
    names: set[str] = set()
    names.update(_git(root, "diff", "--name-only", "--diff-filter=ACMR", base_sha).split())
    names.update(_git(root, "ls-files", "--others", "--exclude-standard").split())
    return sorted(n for n in names if (root / n).is_file())


def is_dirty(root: Path) -> bool:
    return bool(_git(root, "status", "--porcelain").strip())


def sealed_test_files(root: Path) -> list[str]:
    import yaml  # project dependency
    data = yaml.safe_load((root / "evals" / "compliance_testset.yaml").read_text(encoding="utf-8"))
    return list(data.get("files", []))


def module_name(path: str) -> str | None:
    if not path.endswith(".py") or not path.startswith("app/"):
        return None
    module = path[:-3].replace("/", ".")
    return module[: -len(".__init__")] if module.endswith(".__init__") else module


def select_tests(root: Path, changed: list[str]) -> list[str]:
    """Tests worth running for this change, offline suite only (not tests/integration)."""
    def offline_test(p: str) -> bool:
        return (p.startswith("tests/") and not p.startswith("tests/integration/")
                and Path(p).name.startswith("test_") and p.endswith(".py"))

    selected = {p for p in changed if offline_test(p)}
    modules = [m for m in (module_name(p) for p in changed) if m]
    if modules:
        patterns = []
        for module in modules:
            parent, _, leaf = module.rpartition(".")
            patterns.append(re.escape(module) + r"\b")
            if parent:
                patterns.append(rf"from\s+{re.escape(parent)}\s+import\s+[^\n]*\b{re.escape(leaf)}\b")
        needle = re.compile("|".join(patterns))
        for test in sorted((root / "tests").glob("test_*.py")):
            rel = test.relative_to(root).as_posix()
            if rel not in selected and needle.search(test.read_text(encoding="utf-8", errors="ignore")):
                selected.add(rel)
    ordered = sorted(selected)[:MAX_SELECTED_TEST_FILES]
    for sealed in sealed_test_files(root):
        if sealed not in ordered and (root / sealed).exists():
            ordered.append(sealed)
    return ordered


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.returncode, (result.stdout + result.stderr)


def _tail(text: str, lines: int = 25) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def step_secrets(root: Path, base_sha: str, changed: list[str]) -> StepResult:
    spec = importlib.util.spec_from_file_location("gate_scan_secrets", root / "scripts/gate/scan_secrets.py")
    scanner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = scanner
    spec.loader.exec_module(scanner)
    diff = _git(root, "diff", "-U0", base_sha)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard").split()
    for name in untracked:
        path = root / name
        if path.is_file() and path.stat().st_size < 1_000_000:
            body = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            diff += f"\n+++ b/{name}\n@@ -0,0 +1,{len(body)} @@\n" + "\n".join("+" + l for l in body)
    findings = scanner.scan_diff(diff)
    if findings:
        return StepResult("secrets", False, "\n".join(str(f) for f in findings)
                          + "\n(deliberate fake? add the comment marker 'gate: allow-secret')")
    return StepResult("secrets", True, "no credentials in added lines")


def step_syntax(root: Path, changed: list[str]) -> StepResult:
    errors = []
    for name in (p for p in changed if p.endswith(".py")):
        code, out = _run([sys.executable, "-m", "py_compile", name], root)
        if code != 0:
            errors.append(_tail(out, 6))
    if errors:
        return StepResult("syntax", False, "\n".join(errors))
    return StepResult("syntax", True, f"{sum(p.endswith('.py') for p in changed)} file(s) compile")


def step_lint(root: Path, changed: list[str]) -> StepResult:
    files = [p for p in changed if p.endswith(".py")]
    if not files:
        return StepResult("lint", True, "no Python files changed")
    ruff = shutil.which("ruff")
    cmd = [ruff] if ruff else [sys.executable, "-m", "ruff"]
    code, out = _run([*cmd, "check", "--select", RUFF_CRITICAL, "--no-cache", *files], root)
    if code != 0 and "No module named ruff" in out:
        return StepResult("lint", False, "ruff is not installed: pip install ruff")
    return StepResult("lint", code == 0, "clean (critical rules)" if code == 0 else _tail(out))


def step_migrations(root: Path) -> StepResult:
    probe = (
        "from alembic.config import Config\n"
        "from alembic.script import ScriptDirectory\n"
        "heads = ScriptDirectory.from_config(Config('alembic.ini')).get_heads()\n"
        "print(' '.join(heads))\n"
    )
    code, out = _run([sys.executable, "-c", probe], root)
    if code != 0:
        return StepResult("migrations", False, _tail(out))
    heads = out.split()
    if len(heads) != 1:
        return StepResult("migrations", False, f"{len(heads)} Alembic heads: {' '.join(heads)}")
    return StepResult("migrations", True, f"single head {heads[0]}")


def step_registry(root: Path) -> StepResult:
    code, out = _run([sys.executable, "evals/tools/registry_lint.py", "evals/registry.yaml"], root)
    return StepResult("registry", code == 0, _tail(out, 5))


def step_tests(root: Path, changed: list[str]) -> StepResult:
    tests = select_tests(root, changed)
    code, out = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests], root)
    summary = _tail(out, 1)
    detail = f"{len(tests)} file(s): {summary}" if code == 0 else _tail(out)
    return StepResult("tests", code == 0, detail)


def step_frontend(root: Path, changed: list[str]) -> StepResult:
    if not any(p.startswith("frontend/") for p in changed):
        return StepResult("frontend", True, "frontend unchanged")
    fe = root / "frontend"
    if not (fe / "node_modules").is_dir():
        return StepResult("frontend", False, "frontend/ changed but node_modules is missing: run `npm ci` in frontend/")
    npm = shutil.which("npm") or "npm"
    for script in ("type-check", "lint", "test"):
        code, out = _run([npm, "run", "--silent", script], fe)
        if code != 0:
            return StepResult("frontend", False, f"npm run {script} failed:\n{_tail(out)}")
    return StepResult("frontend", True, "type-check, lint, test passed")


def run(root: Path, base: str, steps: list[str]) -> tuple[list[StepResult], str]:
    base_sha = merge_base(root, base)
    changed = changed_files(root, base_sha)
    runners = {
        "secrets": lambda: step_secrets(root, base_sha, changed),
        "syntax": lambda: step_syntax(root, changed),
        "lint": lambda: step_lint(root, changed),
        "migrations": lambda: step_migrations(root),
        "registry": lambda: step_registry(root),
        "tests": lambda: step_tests(root, changed),
        "frontend": lambda: step_frontend(root, changed),
    }
    results = []
    for name in steps:
        start = time.monotonic()
        result = runners[name]()
        result.seconds = time.monotonic() - start
        results.append(result)
    return results, base_sha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quick_gate", description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="origin/master")
    parser.add_argument("--steps", default=",".join(ALL_STEPS),
                        help=f"comma list from: {','.join(ALL_STEPS)} (a partial run never stamps)")
    args = parser.parse_args(argv)
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    unknown = [s for s in steps if s not in ALL_STEPS]
    if unknown:
        parser.error(f"unknown step(s): {', '.join(unknown)}")

    try:
        root = repo_root()
        results, base_sha = run(root, args.base, steps)
    except RuntimeError as exc:
        print(f"quick_gate: ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"quick_gate: diff base {base_sha[:7]} ({args.base})")
    for r in results:
        print(f"  [{'PASS' if r.ok else 'FAIL'}] {r.name:<10} {r.seconds:6.1f}s  {r.detail.splitlines()[0] if r.detail else ''}")
        if not r.ok:
            for line in r.detail.splitlines()[1:]:
                print(f"         {line}")
    ok = all(r.ok for r in results)
    if not ok:
        print("quick_gate: FAILED. Fix the above before pushing.")
        return 1

    full = steps == list(ALL_STEPS)
    if full and not is_dirty(root):
        tree = _git(root, "rev-parse", "HEAD^{tree}").strip()
        stamp = stamp_path(root, tree)
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(f"quick_gate passed {time.strftime('%Y-%m-%dT%H:%M:%S')}\n", encoding="utf-8")
        print(f"quick_gate: PASSED. Stamped tree {tree[:7]}; this commit may be pushed.")
    elif full:
        print("quick_gate: PASSED, but the working tree has uncommitted changes, so nothing was "
              "stamped. Commit, then run it again before pushing.")
    else:
        print("quick_gate: PASSED (partial run; not stamped).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
