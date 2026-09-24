# P0-4 — Duplicate Message Send: Fix Report

- **Status:** FIXED
- **Date:** 2026-09-24
- **Commit:** cda7fc3 on feature/8-new-features (parent 58680cc, the audit HEAD)
- **Audit reference:** "DUPLICATE SEND BUG" in audit_findings.md (RF-5 adjacent)

## The bug
`send_message_impl` read a SCHEDULED message, ran ~200 lines of compliance
gates, then claimed it with a plain ORM write (`message.status = SENDING;
commit()`). The status guards at the top of the function are reads, not
locks: two Celery workers (or two queue deliveries of the same message_id
from `dispatch_due_messages_impl`) could both read the message as SCHEDULED,
both pass every guard, both claim, and both transmit. With 31 workers this
is a when, not an if.

## The fix
The claim is now an atomic conditional UPDATE — the same at-most-once
pattern already used by `_claim` in `app/workers/meeting_prep_tasks.py`:

    UPDATE messages SET status = 'SENDING'
    WHERE id = :id AND status = 'SCHEDULED'

Only the worker whose UPDATE changed the row (rowcount == 1) may transmit.
The loser returns `"lost_claim_race"`, releases any LinkedIn/phone daily
slot it reserved in its prepare step, and never touches the message row,
which now belongs to the winner. One file changed:
`app/workers/outreach_tasks.py` (+34 lines, 1 line modified).

## Corrections to the audit documents
- `send_message_impl` is in `app/workers/outreach_tasks.py` (~line 131).
  The audit's `app/services/message_sender.py` does not exist.
- Models are in `app/db/models.py`, not the audit's `app/models.py`.
- The audit says "SELECT FOR UPDATE SKIP LOCKED"; the codebase's actual
  reference pattern (and this fix) is a conditional UPDATE, which is
  correct for claiming one specific row and is not silently ignored by
  SQLite the way FOR UPDATE is.

## Verification
- Red proof: on unfixed code the new test fails with
  `AssertionError: assert 'sent' == 'lost_claim_race'` — worker B
  transmitted. Reproduced on two machines.
- Green: with the fix, the full send-path sweep (18 test files, including
  the new `tests/test_duplicate_send_claim.py`) = **441 passed, 0 failed**.

## Known limits
The suite runs on in-memory SQLite (single writer, shared StaticPool
connection), so the test proves the losing worker's logic, not
PostgreSQL's locking mechanism. A real race test needs PostgreSQL, one
connection per worker, a threading.Barrier before the claim, and ~50
iterations — scoped to the P1 "real PostgreSQL test suite" item. See the
comment inside `tests/test_duplicate_send_claim.py`.

## Follow-ups logged (not fixed here)
- `fakeredis` is imported by `tests/conftest.py` but missing from
  requirements.txt.
- `core.autocrlf` line-ending noise on Windows checkouts — consider
  `.gitattributes`.
- PydanticDeprecatedSince20 warnings in `app/api/admin.py` class-based
  configs.
