# Phase 1 item 1.2 — eval-gate.yml triggers (sealed-file change)

`.github/workflows/eval-gate.yml` is sealed (`CLAUDE.md`). This PR changes only
when it runs. No step, threshold, test list, baseline or registry entry
changes.

## Change

| | Before | After |
|---|---|---|
| `push` | every branch | `master` only |
| `pull_request` | yes | yes (unchanged) |
| superseded PR runs | keep running | cancelled (`concurrency`, PR events only) |
| `master` runs | — | never cancelled |

## Why

1. **Minutes.** The repo is private on GitHub Free: 2,000 Actions minutes a
   month (`docs/program/BASELINE.md` §11). One gate run bills 9 minutes
   (measured on run 38038727255). With both triggers, every push to a PR
   branch ran the gate twice; Phase 0 measured 3 + 2N runs per PR. Four runs
   on two commits of PR #43 confirmed it.
2. **No loss of coverage on PRs.** The `pull_request` run tests the merge of
   the PR into current `master`, which is a stronger check than the `push`
   run of the branch alone. `scripts/gate/safe_merge.py` requires the `gate`
   check on the PR head to succeed and the head to be up to date with
   `master`, so every merged commit has a green gate run on its exact tree.
3. **`master` still runs on every merge.** That run is what the post-merge
   alarm (item 1.6) and Render "After CI Checks Pass" (item 1.7) read.

## What is given up

- A branch pushed **without** a PR gets no CI. Agents and founders open a
  draft PR to get CI; drafts still run `eval-gate`.
- A run superseded by a newer commit on the same PR is cancelled. Its result
  was about a commit nobody will merge.

## Expected effect

Per PR with N follow-up pushes: before `3 + 2N` runs, after `1 + N` runs.
At N = 2: 63 → 27 billed minutes per PR, about 74 PRs/month instead of 31
before the Phase 1 `verify-*` jobs are added.

## Verification

- This PR's own checks: exactly one `gate` run per pushed commit (event
  `pull_request`), no `push` run on the branch.
- After merge: the merge commit on `master` gets a `push` run.
