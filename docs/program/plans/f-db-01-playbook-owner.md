# F-DB-01 — playbook scores per account

Founder decision VIC-ORDER (2026-10-20): fix F-DB-01 before Phase 1 of the Victorae program.
Finding: `docs/FINDINGS_REGISTER.md` F-DB-01. Re-rated HIGH because sign-up stays open (`DECISIONS.md` P0-D-ENF).

## Problem

`playbook_scores` had no owner column. Its unique key was `(pattern_key, variant)`.

- **The nightly job pooled accounts.** `app/workers/learning_tasks.run_strategy_aggregation` →
  `app/services/score_decay.compute_scores_with_decay` bucketed every account's outcomes into one
  row whenever their strategies shared a `pattern_key`.
- **Pipeline prompts showed the pool as the account's own results.** Research steps in Phase 6
  and Phase 8 (`app/pipeline/engine.py:144`) receive `PlaybookService.get_insights`. That block is
  headed "learned from this account's real outcomes". Without a user id, it fell back to every
  account's rows.
- **Lead scoring used another account's booking rate.** `lead_scoring.playbook_rate` read the best
  rate on the pattern key from any account.
- **The user and admin APIs decided ownership by the pattern key alone.**

**Effect.** One customer's reply and booking rates reached another customer's prompts, scores and
API responses. The data is aggregate rates only, with no personal data. It is still cross-tenant
data, and it was presented under a false label.

## Behaviour after the fix

| Path | Before | After |
|---|---|---|
| Nightly aggregation | one row per (pattern_key, variant), pooled | one row per (account, pattern_key, variant); account = `products.user_id` of the outcome's strategy |
| Upsert key | `ON CONFLICT (pattern_key, variant)` | `ON CONFLICT (user_id, pattern_key, variant)` |
| Pipeline insights | rows on the account's pattern keys, from any account; every account's rows when no user id was known | only the account's own rows; the empty block when no user id is known |
| `GET /playbook/scores` | rows on the caller's pattern keys, from any account | rows the caller owns |
| `GET /admin/playbook/scores?user_id=` | rows on that user's pattern keys | rows that user owns; each row now carries `user_id` |
| Lead-scoring playbook factor | best rate on the key, from any account | best rate among the strategy owner's rows |
| Account export (GDPR Art. 15/20) | table excluded as "global aggregate" | the account's rows are exported |
| Account erasure (Art. 17) | not touched | the account's rows are deleted (`account_erasure.DELETED`, plus `ON DELETE CASCADE`) |

## Data and migration

Migration `0093_playbook_scores_owner` makes these changes:

- adds `user_id` (nullable, FK `users.id ON DELETE CASCADE`, indexed);
- replaces the unique constraint `pattern_variant` with `uq_playbook_scores_owner_pattern_variant (user_id, pattern_key, variant)`.

**Existing rows are not deleted and not attributed.** A pooled row cannot be split between
accounts, so it keeps `user_id` NULL. No reader returns it, and the aggregation never updates it.
The next nightly run rebuilds per-account rows from `outcomes`, which is the source of truth.
After that first run, each account's `trend` starts again at "new".

**Downgrade** deletes the per-account rows, restores the old constraint and drops the column. The
pooled rows survive, so the state before 0093 returns exactly.

Deleting the legacy NULL-owner rows is a separate, founder-approved step. It is not part of this
change.

Model drift found and fixed: `PlaybookScore.trend` was declared `String(20)`, but migration 0010
created `varchar(16)`. The model now says 16. The longest value is 7 characters.

## What stays the same

- The A/B promotion decision. It reads per-strategy outcomes (`learning_tasks.promote_winners`),
  not `playbook_scores`.
- Subject-line patterns (`subject_line_patterns`) and send-time scores (Redis). They are separate
  aggregates. **Whether they also pool across accounts was not checked in this change.** It is
  reported in PROGRESS.md for triage.
- `scripts/backfill_pattern_key.py` orphan clean-up. It works by pattern key and still applies.

## Tests

**Offline (SQLite, FakeClaude):**

- `tests/test_playbook_scores.py`:
  - shared-pattern isolation for the user API;
  - per-account aggregation;
  - pipeline insights (own rows only, no owner → empty, new account → empty);
  - lead-scoring isolation.
- `tests/test_admin_playbook_scores.py`: owner filter on a shared key, and `user_id` on each row.
- `tests/test_outcome_attribution.py`: new result key `<owner hex>::<pattern_key>::<variant>`.

**PostgreSQL 16:**

- `tests/integration/test_migration_0093_playbook_owner_pg.py`:
  - pooled rows kept;
  - uniqueness per account;
  - the real raw-SQL upsert writes and updates per-account rows;
  - cascade on account delete;
  - downgrade then upgrade.
- The full integration suite.
- The sealed export and erasure tests, run through `tests.integration.pg_root_suite`.

## Follow-up

`CLAUDE.md` requires new safety-guard test files to be sealed in the same commit. The isolation
tests were added to existing, unsealed files. Sealing `tests/test_playbook_scores.py`,
`tests/test_admin_playbook_scores.py` and the 0093 migration test needs a `gate/` branch PR, as was
done for the connector guards (F1).
