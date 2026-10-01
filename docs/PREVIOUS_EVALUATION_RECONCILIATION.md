# LeadPilot — Previous Evaluation Reconciliation

Supporting detail for `docs/FULL_PRODUCT_AUDIT.md`. Audit date 2026-10-01.

## Preamble — a material limitation

The original evaluation by the previous evaluator/co-founder ("Ahmad") was
delivered as a file named `audit_findings.md` (referenced by the fix reports as
"RF-2", "RF-3", etc.). **That file is not committed anywhere in the repository or
its git history** — searched across all refs and the full commit graph; no file
matching `audit_findings`/`ahmad`/`evaluation`/`gap` exists in any tree.

Therefore the previous findings were **reconstructed from the founder's own
fix-report documents** (`docs/audit-fixes/P0-*.md` on `feature/8-new-features`).
Those reports are **self-attestations**. Each checkable claim in them was verified
against the actual code on both branches. Statuses below use the required
vocabulary: CONFIRMED (still present), FIXED, PARTIALLY FIXED, INVALIDATED, STILL
PRESENT, REGRESSED, UNVERIFIED.

**The overriding reconciliation fact:** every P0 fix landed **only on
`feature/8-new-features`**. On `master` (the default branch) **all four P0 issues
are STILL PRESENT.**

## Reconciliation table

| Prev. finding (restated) | Founder's claim | Where the fix is | On master? | Independent verdict |
|---|---|---|---|---|
| **RF-2** — free-plan escalation: with `STRIPE_SECRET_KEY` empty, stub mode activates any paid tier for free in production | FIXED `4f5fd4c` — block plan changes in prod when stub mode on (503) | `feature/8` `app/api/billing.py:82–84` | **No** | **FIXED on feature/8 only** · STILL PRESENT on master (CONFIRMED by reading billing.py on both branches). Founder's framing ("stub mode is deliberate, guard it in prod only") is accurate. |
| **RF-3** — account-suspension bypass: `get_current_user` never checks `is_suspended` | FIXED `6e11abe` — suspension check in `get_current_user` | `feature/8` `app/services/auth.py:207` | **No** | **FIXED on feature/8 only** · **STILL PRESENT on master → F-SEC-01 (CRITICAL)**. CONFIRMED by reading auth.py on both + `git branch -r --contains 6e11abe`. |
| **"Duplicate send bug"** (RF-5 adjacent) — two workers can both send one scheduled message | FIXED `cda7fc3` — atomic conditional claim in `send_message_impl` | `feature/8` `app/workers/outreach_tasks.py:369,384` | **No** | **FIXED on feature/8 only** (live path) · STILL PRESENT on master. **Gap:** a *second*, non-atomic send path (`send_tasks.py`) remains on both (F-REL-01) — the fix did not cover it (it is orphaned, so low live risk). CONFIRMED. |
| **P0-6** — `/admin/playbook/scores` broken (filters nonexistent column, swallows the error) | FIXED `5ed9a3d` — SQLAlchemy Core rewrite, swallow removed | `feature/8` `app/api/admin.py` | **No** | **FIXED on feature/8 only** · **STILL PRESENT on master** (`admin.py:291` raw `ps.user_id`, `:310` bare except → F-DB-02). CONFIRMED. |
| Follow-up — `GET /playbook/scores` (user-facing) swallows DB errors + dashed-UUID raw SQL | FIXED `23443a6` + UUID-bind commit | `feature/8` `app/api/playbook.py` | **No** | **FIXED on feature/8 only** (CONFIRMED present there; the swallow/raw-SQL remains on master). |
| Ahmad cited `app/core/dependencies.py` (for the suspension fix) | Founder: "does not exist; real file is `app/services/auth.py`" | — | — | **INVALIDATED** — path confirmed nonexistent; founder's correction accurate. |
| Ahmad cited `app/services/message_sender.py` (for the send fix) | Founder: "does not exist; real file is `app/workers/outreach_tasks.py`" | — | — | **INVALIDATED** — path confirmed nonexistent; correction accurate. |
| Ahmad cited `app/models.py` | Founder: "real file is `app/db/models.py`" | — | — | **INVALIDATED** — correct; models live in `app/db/models.py`. |
| Ahmad: "`/admin/playbook/scores` always returns `[]`" | Founder: "only the `?user_id=` path was broken; unfiltered worked" | — | — | **PARTIALLY CORRECT** — the unfiltered path selected only real columns and worked; only the filtered path raised. Founder's correction accurate. |
| Ahmad: fix should use `SELECT … FOR UPDATE SKIP LOCKED` | Founder: used a conditional UPDATE (correct for one row; FOR UPDATE is silently ignored by SQLite) | — | — | **Founder's engineering judgment is sound** — a conditional UPDATE is the right at-most-once claim here. |

## What this means

1. **The founder's remediation work is real and, where checkable, technically
   correct.** The fix reports are unusually rigorous (red→green evidence, path
   corrections, PostgreSQL verification notes).
2. **Several of Ahmad's findings were imprecise** — wrong file paths (3) and one
   over-broad behavioral claim — which the founder correctly identified and
   corrected. These are INVALIDATED/PARTIALLY-CORRECT in their *specifics*, though
   the underlying defects (where they map to real files) were genuine.
3. **The fixes never reached the default branch.** This is the crux: anyone
   checking `master` — a new evaluator, a deploy, CI — sees none of the P0 fixes.
   This fully explains the founder's sense that "parts of the previous evaluation
   may have been incorrect" (the paths were) *and* that the gaps were fixed (they
   were — on another branch).
4. **The LP-T-002 tenancy findings are a separate, later audit track** (on master)
   and are unfixed on **both** branches. They are not part of Ahmad's P0 set.

## Recommended register action

Treat P0-A (branch reconciliation) as the gating step: once `feature/8` is merged
into the trunk **with the release gate preserved**, re-run the fix tests on the
merged branch to convert each "FIXED on feature/8 only" into "FIXED on trunk,
guarded by a regression test present on trunk."
