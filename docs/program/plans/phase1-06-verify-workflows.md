# Phase 1 item 1.6 — deep verification workflows

New files: `.github/workflows/verify.yml`, `.github/workflows/post-merge-alarm.yml`.
`eval-gate.yml` (sealed) is not touched. `scripts/gate/required_checks.txt` is
**not** changed here: a job becomes required only after it has run green on
`master` (item 1.7 records that and updates the list in its own commit).

## Jobs in `verify.yml`

| Job | What it proves | Runs when (PR) | Est. minutes |
|---|---|---|---|
| `verify-backend-postgres` | single Alembic head; `upgrade head → downgrade -1 → upgrade head` on an empty PostgreSQL 16; the PostgreSQL integration suite (132 tests after #44/#46) with Redis 7 | `app/`, `alembic/`, `tests/integration/`, deps changed | ~7 |
| `verify-frontend` | `npm ci` (lockfile in sync), type-check, lint, vitest (721), production static build | `frontend/` changed | ~5 |
| `verify-image` | production Docker image builds; `app.main`, the Celery app and `firebase_admin` import **inside** the image (the structlog / firebase-admin outage class) | app, deps, Dockerfile changed | ~5 |
| `verify-security` | secrets in added lines (**blocking**, `scripts/gate/scan_secrets.py`); `pip-audit` and `npm audit` (**report only**, in the job summary) | every PR | ~2 |

Rules: heavy jobs run only on non-draft PRs and on pushes to `master`; a job
whose area a PR does not touch reports success after a one-second scope check
("skip but succeed"), so it can be made required without blocking unrelated
PRs; superseded PR runs are cancelled; actions pinned to commit SHAs
(checkout v4.4.0, setup-python v5.6.0, setup-node v4.4.0, github-script v7.1.0,
resolved with `git ls-remote` on 2026-10-10).

Why the audits are report-only: `scripts/gate/safe_merge.py` refuses a PR when
**any** check failed, required or not. Making audits blocking before the
existing findings are triaged would block every PR. Turning them blocking is a
later, separate decision.

## Pre-existing defects found while building this

- **PD-2:** `npm ci` failed on `master` — `frontend/package-lock.json` was out
  of sync with `package.json` (7 missing packages). Fixed in its own PR (#50).
  `verify-frontend` will fail until #50 is merged.
- `next lint` throws unless `NEXT_PUBLIC_API_URL` is set (`next.config.js`
  build guard). The job sets a non-local placeholder.

## `post-merge-alarm.yml`

On every completed `eval-gate` or `verify` run for a push to `master`:
failure → open (or comment on) one issue labelled `master-broken`; success →
close it only when **both** workflows are green on that commit. GitHub Free
cannot block a web-UI merge; this makes a red `master` impossible to miss.

## Minutes (GitHub Free, 2,000/month)

Per non-draft PR push touching backend + frontend: eval-gate 9 + postgres ~7 +
frontend ~5 + image ~5 + security ~2 ≈ 28 minutes. Docs-only or
frontend-only PRs cost much less (skipped jobs bill under a minute). Drafts:
eval-gate only. Measured numbers go into `GATES.md` (item 1.7) after the first
runs.

## Not covered (follow-ups)

- Playwright end-to-end (`frontend/e2e`) and the API + real Celery worker
  journeys (STAR R.1 J1–J10): need the stack running in CI; planned as the
  `verify-e2e-stack` job once the minutes budget is measured.
