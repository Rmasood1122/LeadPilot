# GET /playbook/scores (user-facing): Fix Report

- **Status:** FIXED
- **Date:** 2026-09-27
- **Commits:** 23443a6 (swallowed DB errors) and the "Fix raw-SQL UUID bind"
  commit that follows a0f6ad3, both on feature/8-new-features
- **Audit reference:** none. This was found as a follow-up to P0-6 (see
  P0-6-broken-admin-endpoint.md, "Follow-ups").

## The bugs
1. **Swallowed errors (fixed in 23443a6).** The query was wrapped in
   `except Exception: logger.error(...); return []`, so a paying customer
   got a 200 with an empty list on any DB error. The P0-6 follow-up quoted
   this as `return {"scores": []}`, but the handler actually returned `[]`.
2. **Dashed UUID in raw SQL.** The handler bound `str(current_user.id)` into
   `text()` SQL. On PostgreSQL the literal is cast to uuid and matches. On
   SQLite, where SQLAlchemy's `Uuid` is stored as 32 undashed hex digits, it
   matched nothing, so the root suite could not test the happy path (it was
   xfailed). `strategy_id` was a bare `str`, and a malformed value reached
   Postgres as `invalid input syntax for type uuid` (a 500).

## The fix
- The query is now written in SQLAlchemy Core, in the same style as the P0-6
  fix in app/api/admin.py. The owner filter is
  `Product.user_id == current_user.id`, bound through the `Uuid` type.
- `strategy_id` is `Optional[uuid.UUID]`, so a malformed id returns 422.
- **Unchanged:** the columns (including `strategy_id` per row), DISTINCT,
  the JOIN ownership path (playbook_scores.pattern_key → strategies →
  products.user_id), `ORDER BY reply_rate DESC NULLS LAST`, `LIMIT 200`,
  and the 402 plan gate.

## Verification
- **Red (SQLite, old handler):** 3 of the 5 tests in
  tests/test_playbook_scores.py failed. The happy path and the strategy
  filter both returned `[]`, and a malformed strategy_id got 200.
- **Red (PostgreSQL, old handler):** the malformed id raised
  `InvalidTextRepresentation`. The happy paths already passed there.
- **Green:** 5/5 on SQLite and 5/5 on local PostgreSQL 16, run with
  `python -m pytest -p tests.integration.pg_root_suite
  tests/test_playbook_scores.py` (see tests/integration/pg_root_suite.py).
- **Not run:** the integration harness (tests/integration/test_*.py).

## Follow-ups (not fixed here)
- `logger` in app/api/playbook.py has been unused since the swallow was
  removed.
- Two strategies that share a pattern_key each produce a row, because
  strategy_id is selected. This is existing behaviour and was left as-is.
