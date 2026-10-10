# Phase 1, item 1 — PostgreSQL integration suite repair

Session: cloud, 2026-10-10. Base: `master @ 268a81f`. PostgreSQL 16 and
Redis 7 from the VM (not docker compose), reached with
`TEST_DATABASE_URL=postgresql://leadpilot:leadpilot@localhost:5432/clienthunter_test`
and `TEST_REDIS_URL=redis://localhost:6379/15`. Python 3.12.3, anthropic 1.13.0,
respx 0.23.1, httpx 0.28.1.

## Result

| State | Command | Result | Runtime |
|---|---|---|---|
| Before (master) | `python -m pytest tests/integration -q -p no:cacheprovider` | **54 failed, 70 passed**, exit 1 | 157 s |
| After, run 1 | same | **125 passed, 4 errors**, exit 1 | 260 s |
| After, run 2 | same | 125 passed, 4 errors, exit 1 | 260 s |
| After, files in reverse order | same, files listed `sort -r` | 125 passed, 4 errors, exit 1 | 253 s |
| After review fixes | same | 125 passed, 4 errors, exit 1 | 263 s |

Collected tests: 124 before, 129 after (5 new self-tests in
`test_harness_guards.py`). No test was skipped, deleted or marked xfail.

**The suite is not green.** The 4 errors are a product defect (PD-1 below),
which the ported tests now expose. Fixing it needs a migration and is outside
this item. It is reported, not fixed.

## Root causes of the 54 failures

| Group | Tests | Root cause | Fix (all in `tests/integration/`) |
|---|---|---|---|
| G1 | 50 (`test_flows` 20, `test_notifications_wiring` 9, `test_compliance` 8, `test_security` 7, `test_idempotency` 6) | Root `tests/conftest.py::no_real_anthropic` (autouse) makes `get_client()` raise. These tests mock Anthropic at HTTP with respx instead. 47 raised directly; 3 were the same error wrapped in a Celery `Retry`. | Override `no_real_anthropic` in `tests/integration/conftest.py` (details below). 39 of the 50 then pass. The other 11 had a second cause hidden behind the first (G2, G3). |
| G2 | 7 of G1 (`test_security` 2, `test_notifications_wiring` 2, `test_idempotency` 1, `test_flows` 2) | `calendly_mock.sign_payload` signed with fixed `t=1700000000` (2023-11-14). F-OPS-02 later made `verify_webhook_signature` refuse a `t` older than the tolerance, so every Calendly delivery returned 401 as a replay. | Sign with the current time by default. Same HMAC, still verified by the real verifier. |
| G3 | 4 of G1 (`test_compliance` 3, `test_flows` 1), plus 1 passing test that could not fail (`test_security::test_valid_signed_unsubscribe_token_works_without_auth`) | `GET`/`POST /suppression` became admin-only (F-SEC-04). The tests called it as `user_a` and never checked the response, so the POST was a silent 403 and nothing was suppressed. The send and sourcing paths were correct to proceed. | Call `/suppression` with `admin_tokens`, and assert 201/200 on it, so a setup failure is loud. Every original assertion is unchanged. The fifth test asserted `len(resp.json()) >= 1` on the 403 body (always true); it now asserts the email is in `entries`. |
| G4 | 4 (`test_chunk5_production_launch::TestWebhookDelivery`) | `app/services/webhook_delivery.py` was rebuilt in `41cea92`. `create_delivery(db_session=, target_id=, event_type=)` and `mark_failed_attempt` no longer exist (TypeError / ImportError / AttributeError). | Ported to the current API, same test names and intent, on real PostgreSQL rows instead of a `MagicMock` session. They now error in setup on PD-1. |

### G1 in detail — why the guard could not simply be removed

Narrowing the guard to "allow the real client while a respx route exists" was
tried first. A request then reached the real `api.anthropic.com` (HTTP 401
`invalid x-api-key` with a live `request_id`). The anthropic SDK 1.x sends
through its own `httpx2` package; respx patches `httpx`/`httpcore` only, so the
HTTP-level mock in `tests/integration/mocks/anthropic_mock.py` has never
intercepted the SDK on this version. The root guard was the only thing
stopping real calls.

The override therefore:

1. hands out a `ClaudeClient` whose SDK `http_client` is an explicit
   `MockTransport` forwarding to the test's respx router (`router.handler`).
   An unrouted request raises inside respx and never opens a socket;
2. does so only when the test's router has an `api.anthropic.com` route;
   every other integration test keeps the refusal;
3. patches every loaded `app.*` module that binds the gateway's `get_client`
   by name at import (12 modules today). Patching only `anthropic_client.get_client` left a
   module first imported during an earlier test holding that test's function,
   so results depended on test order;
4. never builds or touches the module singleton.

`tests/integration/test_harness_guards.py` pins this. Against the master
conftest, 2 of its 5 tests fail (the routed call is refused); with the fix,
5 pass.

## PD-1 — product defect found (reported, not fixed)

`webhook_targets.event_types` is `postgresql.ARRAY(Text)` in
`alembic/versions/0011_m8c5_production_launch.py:34`. The model declares it
`JSON` (`app/db/models.py`, `WebhookTarget.event_types`). No later migration
converts it. On PostgreSQL, `webhook_delivery.create_target` fails:

```
psycopg2.errors.DatatypeMismatch: column "event_types" is of type text[] but expression is of type json
```

Effect: on any PostgreSQL deployment (production runs on Neon), registering an
outbound webhook or a Zapier/Make subscription raises, so Feature Group 4
outbound webhooks cannot work. The SQLite offline suite cannot see this,
because `create_all` builds the column from the model. Whether production's
column is still `text[]` is UNVERIFIED (no production access in this session).

PD-1 is wider than that one column. With `event_types` patched to JSON in a
local throwaway edit of migration 0011 (reverted), the same four tests then
fail on `column "last_status_code" of relation "webhook_deliveries" does not
exist`. `alembic.autogenerate.compare_metadata` of the ORM against a freshly
migrated PostgreSQL 16 database (`alembic upgrade head` exit 0) shows these
material differences (TIMESTAMP-vs-DATETIME and similar name-only diffs
omitted):

| Table | Migrated schema | Model expects |
|---|---|---|
| `webhook_targets` | `event_types text[]` | `JSON` |
| `webhook_deliveries` | no `last_status_code`, no `delivered_at` | both columns |
| `webhook_deliveries` | `payload_json text`, two columns the model lacks | `JSON` |
| `subject_line_patterns` | no `updated_at` | column present |
| `strategies` | two columns the model lacks | — |

So outbound-webhook creation **and** delivery fail on PostgreSQL. Fix shape
for its own PR: one migration bringing `webhook_targets`, `webhook_deliveries`
and `subject_line_patterns` in line with the model (with a downgrade), plus a
single-head / no-drift check in `verify-backend-postgres` so the next drift
fails CI. The four ported tests are its proof.

## Other observations (reported, not fixed)

- `requirements.txt` / `pyproject.toml` pin `anthropic>=0.28.0` with no upper
  bound. The SDK moved to `httpx2` somewhere in that range; any test anywhere
  that relies on respx to intercept the SDK is not intercepting it.
- `tests/integration/conftest.py` defaults to `localhost:5433` and Redis
  `6380` (docker compose ports). This VM runs 5432/6379, so the run used the
  env overrides above.
