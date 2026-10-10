"""scripts/gate/safe_merge.py — the merge gate behind policy MERGE-B.

Production scenario: on 2026-10-10 three PRs were merged from the GitHub web
UI without this gate — one before CI finished (INC-43), one while still a
draft (#44) and one with failing CI (#45), which left master red. On a private
repo on GitHub Free nothing server-side stops that, so this script is the
rule. Every test drives the real `evaluate`/`main` against a scripted fake of
the GitHub REST API: offline, no `gh`, no network.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "gate_safe_merge", ROOT / "scripts" / "gate" / "safe_merge.py")
safe_merge = importlib.util.module_from_spec(_spec)
# dataclasses resolve annotations through sys.modules, so register first.
sys.modules[_spec.name] = safe_merge
_spec.loader.exec_module(safe_merge)

REPO = "Owner/Repo"
SHA = "a" * 40


def _green_world() -> dict:
    return {
        f"repos/{REPO}/pulls/7": {
            "state": "open", "draft": False, "mergeable": True, "merged_at": None,
            "title": "Add thing", "head": {"sha": SHA}, "base": {"ref": "master"},
        },
        f"repos/{REPO}/compare/master...{SHA}": {"behind_by": 0, "ahead_by": 2},
        f"repos/{REPO}/commits/{SHA}/check-runs?per_page=100": {"check_runs": [
            {"name": "gate", "status": "completed", "conclusion": "success"},
            {"name": "gate", "status": "completed", "conclusion": "success"},
            {"name": "Vercel Preview Comments", "status": "completed", "conclusion": "success"},
        ]},
        f"repos/{REPO}/commits/{SHA}/status": {"state": "success", "statuses": [
            {"context": "Vercel", "state": "success"},
        ]},
    }


class FakeApi:
    def __init__(self, world: dict) -> None:
        self.world = world
        self.puts: list[tuple[str, dict]] = []

    def get(self, path: str):
        return copy.deepcopy(self.world[path])

    def put(self, path: str, fields: dict):
        self.puts.append((path, fields))
        return {"sha": "b" * 40, "merged": True}


def _run(world: dict, *extra: str) -> tuple[int, FakeApi]:
    api = FakeApi(world)
    code = safe_merge.main(["7", "--repo", REPO, *extra], api=api, sleep=lambda s: None)
    return code, api


def test_all_green_merges_the_checked_sha_with_squash():
    code, api = _run(_green_world())
    assert code == 0
    assert api.puts == [(f"repos/{REPO}/pulls/7/merge", {
        "merge_method": "squash", "sha": SHA, "commit_title": "Add thing (#7)"})]


def test_dry_run_checks_but_never_merges():
    code, api = _run(_green_world(), "--dry-run")
    assert code == 0
    assert api.puts == []


def test_draft_pr_is_refused():  # PR #44 was merged while still a draft
    world = _green_world()
    world[f"repos/{REPO}/pulls/7"]["draft"] = True
    code, api = _run(world)
    assert code == 1 and api.puts == []


def test_failed_required_check_is_refused():  # PR #45 was merged with red CI
    world = _green_world()
    world[f"repos/{REPO}/commits/{SHA}/check-runs?per_page=100"]["check_runs"][1][
        "conclusion"] = "failure"
    code, api = _run(world)
    assert code == 1 and api.puts == []


def test_running_required_check_is_refused():  # INC-43: merged before CI finished
    world = _green_world()
    run = world[f"repos/{REPO}/commits/{SHA}/check-runs?per_page=100"]["check_runs"][0]
    run.update(status="in_progress", conclusion=None)
    code, api = _run(world)
    assert code == 1 and api.puts == []


def test_missing_required_check_is_refused():
    world = _green_world()
    world[f"repos/{REPO}/commits/{SHA}/check-runs?per_page=100"]["check_runs"] = [
        {"name": "Vercel Preview Comments", "status": "completed", "conclusion": "success"}]
    code, api = _run(world)
    assert code == 1 and api.puts == []


def test_other_failing_check_is_refused():
    world = _green_world()
    world[f"repos/{REPO}/commits/{SHA}/check-runs?per_page=100"]["check_runs"][2][
        "conclusion"] = "failure"
    code, api = _run(world)
    assert code == 1 and api.puts == []


def test_skipped_non_required_check_is_allowed():
    world = _green_world()
    world[f"repos/{REPO}/commits/{SHA}/check-runs?per_page=100"]["check_runs"][2][
        "conclusion"] = "skipped"
    code, _ = _run(world)
    assert code == 0


@pytest.mark.parametrize("state", ["failure", "error", "pending"])
def test_bad_commit_status_is_refused(state):
    world = _green_world()
    world[f"repos/{REPO}/commits/{SHA}/status"]["statuses"][0]["state"] = state
    code, api = _run(world)
    assert code == 1 and api.puts == []


def test_branch_behind_master_is_refused():
    world = _green_world()
    world[f"repos/{REPO}/compare/master...{SHA}"]["behind_by"] = 3
    code, api = _run(world)
    assert code == 1 and api.puts == []


def test_conflicting_pr_is_refused():
    world = _green_world()
    world[f"repos/{REPO}/pulls/7"]["mergeable"] = False
    code, api = _run(world)
    assert code == 1 and api.puts == []


def test_wrong_base_branch_is_refused():
    world = _green_world()
    world[f"repos/{REPO}/pulls/7"]["base"]["ref"] = "develop"
    code, api = _run(world)
    assert code == 1 and api.puts == []


def test_closed_pr_is_refused():
    world = _green_world()
    world[f"repos/{REPO}/pulls/7"].update(state="closed", merged_at="2026-10-10T00:00:00Z")
    code, api = _run(world)
    assert code == 1 and api.puts == []


def test_unknown_mergeability_is_retried_then_refused():
    world = _green_world()
    world[f"repos/{REPO}/pulls/7"]["mergeable"] = None
    sleeps: list[float] = []
    api = FakeApi(world)
    code = safe_merge.main(["7", "--repo", REPO], api=api, sleep=sleeps.append)
    assert code == 1 and api.puts == []
    assert len(sleeps) == safe_merge.MERGEABLE_RETRIES


def test_api_error_exits_2_without_merging():
    class Broken(FakeApi):
        def get(self, path):
            raise safe_merge.GitHubError("HTTP 401")
    api = Broken({})
    code = safe_merge.main(["7", "--repo", REPO], api=api, sleep=lambda s: None)
    assert code == 2 and api.puts == []


def test_required_checks_file_lists_the_eval_gate():
    assert "gate" in safe_merge.load_required_checks()


def test_empty_required_checks_file_is_rejected(tmp_path):
    empty = tmp_path / "required.txt"
    empty.write_text("# nothing\n\n", encoding="utf-8")
    with pytest.raises(ValueError):
        safe_merge.load_required_checks(empty)


@pytest.mark.parametrize("url", [
    "https://github.com/Rmasood1122/LeadPilot",
    "https://github.com/Rmasood1122/LeadPilot.git",
    "git@github.com:Rmasood1122/LeadPilot.git",
])
def test_repo_from_remote(url):
    assert safe_merge.repo_from_remote(url) == "Rmasood1122/LeadPilot"
