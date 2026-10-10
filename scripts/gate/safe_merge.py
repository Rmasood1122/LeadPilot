#!/usr/bin/env python3
"""safe_merge: the only sanctioned way to merge a pull request into master.

WHY THIS EXISTS
---------------
The repository is private on GitHub Free, so branch protection and rulesets
are not available (docs/program/DECISIONS.md, GH-PRO). GitHub will happily
merge a draft PR, a PR whose CI is still running, or a PR whose CI failed.
All three happened on 2026-10-10 (INC-43, and PRs #44/#45, which left master
red). Merge policy B (DECISIONS.md MERGE-B) replaces the missing server-side
rule with this script: it refuses unless every condition below holds, and
then merges the exact commit it checked.

WHAT IT CHECKS (all must pass)
------------------------------
1. The PR is open, targets master, and is not a draft.
2. GitHub reports no merge conflict.
3. The PR head contains the latest master (strict mode). A PR that was green
   against an older master can still break master after merge.
4. Every check named in scripts/gate/required_checks.txt has run on the head
   commit, and every run of it concluded "success".
5. No other check run on the head commit is still running or failed.
6. No commit status on the head commit (for example a Vercel deployment) is
   pending or failed.

Then it squash-merges with the head SHA pinned, so a commit pushed between
the check and the merge makes GitHub reject the merge instead of merging
unchecked code.

USAGE
-----
    scripts/gate/safe_merge.sh 47            # check, then merge
    scripts/gate/safe_merge.sh 47 --dry-run  # check only, merge nothing

Requires the GitHub CLI (`gh`) authenticated for the repository. Exit codes:
0 merged (or dry-run passed), 1 refused, 2 usage or API error.

WHAT IT CANNOT DO
-----------------
Anyone can still press "Merge" in the GitHub web UI. This script is the rule;
deploy gating (Render "After CI Checks Pass", Vercel Deployment Checks) is the
backstop that keeps an unchecked merge out of production.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

BASE_BRANCH = "master"
REQUIRED_CHECKS_FILE = Path(__file__).resolve().parent / "required_checks.txt"

# A check run that ended in one of these counts as passed. "skipped" covers
# jobs whose path filter decided they do not apply to this PR.
PASSING_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})

# GitHub computes `mergeable` lazily and returns null until it has.
MERGEABLE_RETRIES = 5
MERGEABLE_RETRY_SECONDS = 2.0


class GitHubError(RuntimeError):
    """The GitHub API call failed (auth, network, 4xx/5xx)."""


class GitHubApi(Protocol):
    def get(self, path: str) -> Any: ...

    def put(self, path: str, fields: dict[str, str]) -> Any: ...


class GhCliApi:
    """GitHub REST access through the authenticated `gh` CLI.

    REST only: GraphQL is unavailable from Claude Code cloud sessions, and
    `gh pr merge` uses GraphQL, which is one more reason it is not used here.
    """

    def __init__(self, gh_binary: str = "gh") -> None:
        self._gh = gh_binary

    def _run(self, args: list[str]) -> Any:
        try:
            result = subprocess.run(
                [self._gh, "api", *args],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GitHubError(
                f"`{self._gh}` not found. Install the GitHub CLI and run `gh auth login`."
            ) from exc
        if result.returncode != 0:
            raise GitHubError(result.stderr.strip() or result.stdout.strip())
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def get(self, path: str) -> Any:
        return self._run([path])

    def put(self, path: str, fields: dict[str, str]) -> Any:
        args = ["-X", "PUT", path]
        for key, value in fields.items():
            args += ["-f", f"{key}={value}"]
        return self._run(args)


@dataclass
class Evaluation:
    head_sha: str
    title: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def load_required_checks(path: Path = REQUIRED_CHECKS_FILE) -> list[str]:
    """One check name per line; blank lines and # comments ignored."""
    names: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.append(line)
    if not names:
        raise ValueError(f"{path} lists no required checks; refusing to merge on nothing")
    return names


def repo_from_remote(remote_url: str) -> str:
    """'https://github.com/Owner/Repo(.git)' or 'git@github.com:Owner/Repo.git' -> 'Owner/Repo'."""
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", remote_url.strip())
    if not match:
        raise ValueError(f"cannot read owner/repo from remote URL {remote_url!r}")
    return f"{match.group(1)}/{match.group(2)}"


def _fetch_pr(api: GitHubApi, repo: str, number: int,
              sleep: Callable[[float], None]) -> dict:
    pr = api.get(f"repos/{repo}/pulls/{number}")
    for _ in range(MERGEABLE_RETRIES):
        if pr.get("mergeable") is not None or pr.get("state") != "open":
            break
        sleep(MERGEABLE_RETRY_SECONDS)
        pr = api.get(f"repos/{repo}/pulls/{number}")
    return pr


def evaluate(api: GitHubApi, repo: str, number: int, required: list[str],
             sleep: Callable[[float], None] = time.sleep) -> Evaluation:
    pr = _fetch_pr(api, repo, number, sleep)
    head_sha = pr["head"]["sha"]
    ev = Evaluation(head_sha=head_sha, title=pr.get("title", ""))

    if pr.get("state") != "open":
        merged = " (already merged)" if pr.get("merged_at") else ""
        ev.problems.append(f"PR #{number} is {pr.get('state')}{merged}, not open.")
    if pr["base"]["ref"] != BASE_BRANCH:
        ev.problems.append(
            f"PR #{number} targets '{pr['base']['ref']}', not '{BASE_BRANCH}'.")
    if pr.get("draft"):
        ev.problems.append(f"PR #{number} is a draft. Mark it ready for review first.")
    if pr.get("mergeable") is False:
        ev.problems.append(f"PR #{number} has merge conflicts with {BASE_BRANCH}.")
    elif pr.get("mergeable") is None and pr.get("state") == "open":
        ev.problems.append("GitHub has not finished computing mergeability; try again in a minute.")

    compare = api.get(f"repos/{repo}/compare/{BASE_BRANCH}...{head_sha}")
    behind = int(compare.get("behind_by", 0))
    if behind > 0:
        ev.problems.append(
            f"PR head is {behind} commit(s) behind {BASE_BRANCH}. Update the branch "
            f"(gh api -X PUT repos/{repo}/pulls/{number}/update-branch), wait for CI, retry.")

    runs = api.get(f"repos/{repo}/commits/{head_sha}/check-runs?per_page=100")
    check_runs = runs.get("check_runs", [])
    by_name: dict[str, list[dict]] = {}
    for run in check_runs:
        by_name.setdefault(run["name"], []).append(run)

    for name in required:
        name_runs = by_name.get(name, [])
        if not name_runs:
            ev.problems.append(f"Required check '{name}' has not run on {head_sha[:7]}.")
            continue
        for run in name_runs:
            if run.get("status") != "completed":
                ev.problems.append(f"Required check '{name}' is still {run.get('status')}.")
            elif run.get("conclusion") != "success":
                ev.problems.append(
                    f"Required check '{name}' concluded '{run.get('conclusion')}': "
                    f"{run.get('html_url', '')}".rstrip(": "))

    required_set = set(required)
    for run in check_runs:
        if run["name"] in required_set:
            continue
        if run.get("status") != "completed":
            ev.problems.append(f"Check '{run['name']}' is still {run.get('status')}.")
        elif run.get("conclusion") not in PASSING_CONCLUSIONS:
            ev.problems.append(
                f"Check '{run['name']}' concluded '{run.get('conclusion')}'.")

    combined = api.get(f"repos/{repo}/commits/{head_sha}/status")
    for status in combined.get("statuses", []):
        state = status.get("state")
        if state in ("failure", "error"):
            ev.problems.append(f"Status '{status.get('context')}' is {state}.")
        elif state == "pending":
            ev.problems.append(f"Status '{status.get('context')}' is still pending.")

    return ev


def merge(api: GitHubApi, repo: str, number: int, ev: Evaluation) -> dict:
    return api.put(
        f"repos/{repo}/pulls/{number}/merge",
        {
            "merge_method": "squash",
            "sha": ev.head_sha,  # GitHub rejects the merge if the head moved
            "commit_title": f"{ev.title} (#{number})",
        },
    )


def _origin_url() -> str:
    result = subprocess.run(["git", "remote", "get-url", "origin"],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ValueError("no git remote 'origin'; pass --repo OWNER/NAME")
    return result.stdout


def main(argv: list[str] | None = None, api: GitHubApi | None = None,
         sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(
        prog="safe_merge", description="Merge a PR into master only if every gate is green.")
    parser.add_argument("pr", type=int, help="pull request number")
    parser.add_argument("--dry-run", action="store_true", help="check only; do not merge")
    parser.add_argument("--repo", help="OWNER/NAME (default: from git remote origin)")
    args = parser.parse_args(argv)

    try:
        repo = args.repo or repo_from_remote(_origin_url())
        required = load_required_checks()
        api = api or GhCliApi()
        ev = evaluate(api, repo, args.pr, required, sleep=sleep)
    except (GitHubError, ValueError, KeyError) as exc:
        print(f"safe_merge: ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"safe_merge: PR #{args.pr} '{ev.title}' head {ev.head_sha[:7]}")
    print(f"safe_merge: required checks: {', '.join(required)}")
    if not ev.ok:
        print("safe_merge: REFUSED. Not merging:")
        for problem in ev.problems:
            print(f"  - {problem}")
        return 1

    if args.dry_run:
        print("safe_merge: all gates green. Dry run: nothing merged.")
        return 0

    try:
        result = merge(api, repo, args.pr, ev)
    except GitHubError as exc:
        print(f"safe_merge: ERROR: GitHub refused the merge: {exc}", file=sys.stderr)
        return 2
    print(f"safe_merge: MERGED PR #{args.pr} as {str(result.get('sha', ''))[:7]} (squash).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
