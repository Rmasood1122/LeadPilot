# P0-6 — Broken Admin Endpoint (/admin/playbook/scores): Fix Report

- **Status:** FIXED
- **Date:** 2026-09-26
- **Commit:** 5ed9a3d on feature/8-new-features
- **Audit reference:** P0-6 (no source audit file in the repo cites it)

## The bug
`list_playbook_scores` (app/api/admin.py) built raw SQL and, when
`?user_id=` was passed, added `WHERE ps.user_id = :user_id`.
playbook_scores has never had a user_id column:
- migration 0001 created id, pattern_key, metric, score, sample_size and
  the created_at/updated_at timestamps;
- 0008 added variant, reply_rate, booking_rate, is_reliable,
  last_aggregated_at and re-keyed the table on (pattern_key, variant);
- 0010 added decay_half_life_days, effective_sample_size,
  oldest_outcome_ts and trend;
- models.PlaybookScore matches the migrations.

Every filtered call raised UndefinedColumn, and this block swallowed it:

```python
    except Exception as e:
        logger.error("admin.playbook_scores_failed", error=str(e))
        return {"scores": []}
```

The admin got a 200 with an empty list, the same response as "no data
yet".

## Correction to the audit documents
The audit says the endpoint always returns []. It does not. The unfiltered
call selected only real columns and worked on the old code:
`TestUnfiltered::test_returns_every_row` passed before the fix. Only the
`?user_id=` path was broken. The bigger defect was the swallowing, because
it hid that path's failure (and would hide any other DB error).

## The fix
- **Ownership path:** a row reaches a user only through
  playbook_scores.pattern_key → strategies.pattern_key →
  strategies.product_id → products.user_id. The filter is now
  `pattern_key IN (SELECT s.pattern_key FROM strategies s JOIN products p
  … WHERE p.user_id = :uid AND s.pattern_key IS NOT NULL)`. This is the
  same path app/services/playbook_service.py uses. An IN subquery was
  chosen over a JOIN so that two strategies sharing a key do not duplicate
  rows.
- **Query form:** the query is now written in SQLAlchemy Core instead of
  f-string SQL. user_id is typed as `uuid.UUID`, so the UUID binds
  correctly on Postgres and SQLite, and a malformed id returns 422 instead
  of reaching the DB.
- **Errors:** the try/except is removed. A DB error propagates as a 500.
- **Unchanged:** the response shape (`{"scores": [...]}`, same 11 keys),
  the ordering, pagination and degrading_only.

## score vs reply_rate — verdict: redundant (score always equals reply_rate)
Evidence (every writer of the table was checked):
- **The aggregation upsert:** the only production writer is
  `_upsert_playbook_score` (app/workers/learning_tasks.py:151). It binds
  the same `:reply_rate` parameter into both columns on INSERT, and sets
  `score = EXCLUDED.score` on conflict. Every aggregated row therefore has
  score == reply_rate.
- **Other code paths:** nothing else inserts or updates the table.
  scripts/backfill_pattern_key.py only reads and deletes orphaned rows.
  lead_scoring.py and playbook_service.py only read. Tests create rows
  through the ORM.
- **The only reader of score:** the upsert's own trend CASE, which
  compares the new value against the old `playbook_scores.score`, i.e. the
  previous reply_rate. `playbook_scores.reply_rate` would give the same
  result.
- **The one exception:** legacy M1 rows (pre-0008, keyed on metric) may
  hold a score with reply_rate NULL. Check production for such rows before
  any drop.
- **Side note:** the trend CASE branch `WHEN playbook_scores.score IS NULL
  THEN 'new'` is dead code, because score is NOT NULL since 0001.

No column was removed. Dropping score needs a migration and its own
change.

## Verification
- **Red:** 4 of 7 new tests in tests/test_admin_playbook_scores.py failed
  on the old code. The filtered call returned `[]`, and the log showed
  `no such column: ps.user_id`. A malformed id got 200 instead of 422. A
  dropped table got 200 instead of 500.
- **Green:** 7/7. The sweep covered the 9 modules that hit /admin/ plus
  the new module and the P0-2/3/4 modules: 440 passed.
- **PostgreSQL (2026-09-27):** tests/test_admin_playbook_scores.py passed
  7/7 against local PostgreSQL 16 (the docker-compose `db` service on
  localhost:5433), never against the .env database. The schema came from
  `alembic upgrade head` (0064_meeting_practice) into a fresh database, and
  each test got a new copy of it. A throwaway pytest plugin, not committed,
  pointed the root conftest's `db_session` engine at that copy. The UUID
  bind and the IN subquery both behave on Postgres as they do on SQLite.
- **Not run:** the integration harness (tests/integration/).

## Follow-ups logged (not fixed here)
- **update_user_plan** (app/api/admin.py) uses raw SQL with `NOW()`
  (`UPDATE users SET plan = :plan, updated_at = NOW()`). It writes its
  audit record into the task_errors table
  (`task_name='admin.plan_update'`, `error_type='AuditLog'`), which mixes
  audit history with error telemetry. `NOW()` is also Postgres/SQLite-
  divergent raw SQL.
- **GET /playbook/scores** (app/api/playbook.py, the user-facing
  endpoint) has the same `except Exception: return []` swallowing. Its
  query is valid.
- **AdminService.list_playbook_scores** (app/services/admin_service.py)
  is dead code (no callers) with the same bug. It uses `filter_by(user_id=…)`
  and also reads the nonexistent `last_updated` and `strategy_id`. Delete it
  or fix it.
- **score column:** drop it (see the verdict above) after checking for
  legacy M1 rows.
