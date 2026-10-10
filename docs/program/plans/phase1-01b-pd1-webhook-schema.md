# Phase 1, item 1b — PD-1: webhook schema drift on PostgreSQL

Session: cloud, 2026-10-10. Branch `claude/pd1-webhook-schema`, stacked on
PR #44 (`claude/nice-allen-8wgv8a`). Merge after #44.

## Defect

`app/services/webhook_delivery.py` writes `webhook_targets` and
`webhook_deliveries` through the ORM model. The PostgreSQL schema built by
the migrations does not match it:

| Column | Migrated (0011 + 0029) | Model | Effect on PostgreSQL |
|---|---|---|---|
| `webhook_targets.event_types` | `text[]` | `JSON` | every `create_target` fails: `DatatypeMismatch` |
| `webhook_deliveries.payload_json` | `text` | `JSON` | |
| `webhook_deliveries.last_status_code` | missing (old name `last_response_code`) | present | every delivery INSERT fails: `UndefinedColumn` |
| `webhook_deliveries.delivered_at` | missing | present | same |

So outbound webhooks, including Zapier/Make subscriptions, cannot be created or
delivered on any PostgreSQL deployment. The SQLite offline suite builds tables
from the model and cannot see this.

### Correction to the scope stated in PR #44

`docs/program/plans/phase1-01-integration-repair.md` listed
`subject_line_patterns.updated_at` as part of PD-1. That was wrong. The live
writer, `app/services/subject_intelligence.py::persist_patterns`, uses raw SQL
with `last_updated`, which **matches** the migrated table. The stale side is
the ORM model (`SubjectLinePattern.updated_at`). PostgreSQL is fine; nothing
changes there. Reported below as an out-of-scope model/migration mismatch.

## Fix

`alembic/versions/0071_webhook_schema_sync.py` (PostgreSQL only):

- `webhook_targets.event_types` text[] → json, values kept (`to_json`).
- `webhook_deliveries.payload_json` text → json. Text that is not valid JSON
  is kept as `{"legacy_text": "<original>"}` instead of failing the deploy.
- `webhook_deliveries.last_status_code` added and copied from
  `last_response_code`; `delivered_at` added.
- Nothing dropped. `last_response_code` and `max_retries` stay (nullable /
  server default 5, so ORM inserts succeed).
- Downgrade restores the 0070 shapes, unwraps `legacy_text` back to the
  original text and copies status codes back. `delivered_at` values are
  dropped on downgrade (the column did not exist before).
- `SET LOCAL lock_timeout = '15s'` in both directions. Both type changes take
  ACCESS EXCLUSIVE and `app/db/migrate.py` sets no timeout, so an open
  transaction on these tables would otherwise hang API startup and queue every
  webhook query behind it. With the timeout the migration fails, the
  entrypoint never starts uvicorn, and the previous instance keeps serving.
- `scripts/activate_with_keys.py` `TARGET_REVISION` → `0071_webhook_schema_sync`
  (required by `tests/test_activation_script.py`; 0070 moved it the same way).

## Evidence

| Check | Command | Result |
|---|---|---|
| New tests, before the migration | `pytest tests/integration/test_migration_0071_webhook_schema.py` | 3 failed (revision missing; ORM round-trip `DatatypeMismatch`) |
| New tests + ported webhook tests, after | same + `test_chunk5_production_launch.py::TestWebhookDelivery` | 8 passed |
| Full PostgreSQL suite | `python -m pytest tests/integration -q -p no:cacheprovider` | **132 passed, 0 failed, exit 0**, 261 s |
| Single head | `python -m alembic heads` | `0071_webhook_schema_sync (head)` |
| Strengthened downgrade test vs. the first version of 0071 (no unwrap) | `pytest tests/integration/test_migration_0071_webhook_schema.py` | 1 failed (`'{"legacy_text": ...}' == 'not json {'`), proving the assertion bites; passes on the fix |
| Full PostgreSQL suite, final | same | 132 passed, 0 failed, exit 0, 265 s |
| Offline gate, first run | four `CLAUDE.md` commands | **BLOCK**: 1 failure, `test_activation_script.py::test_target_revision_matches_the_latest_migration` (TARGET_REVISION still 0070). Fixed. |
| Offline gate, final | four `CLAUDE.md` commands | all exit 0; 3,319 tests, 0 failed; PROMOTE (soft runtime warning, 629 s) |
| Drift after upgrade | `alembic.autogenerate.compare_metadata` on a fresh migrated DB | No breaking webhook differences left (see remaining list) |

The three new tests: legacy rows converted on upgrade (arrays, JSON payload,
status code, invalid-JSON payload kept); create/deliver/fail through the ORM
after upgrade; downgrade restores the old shapes and data.

## Deploy

Production applies migrations at API start (`scripts/render_api_entrypoint.sh`
→ `python -m app.db.migrate`). The first API deploy after this merges runs
0071 on Neon. Auto-deploy is OFF on `leadpilot-api` (founder statement,
2026-10-10), so that happens only when a founder deploys.

Before that deploy, run this read-only query on Neon to see what 0071 will
convert (UNVERIFIED: not run, no production access in this session):

```sql
SELECT
  (SELECT count(*) FROM webhook_targets)                       AS targets,
  (SELECT count(*) FROM webhook_deliveries)                    AS deliveries,
  (SELECT count(*) FROM webhook_deliveries
     WHERE payload_json IS NOT NULL AND payload_json !~ '^\s*[\[{]') AS non_json_payloads,
  (SELECT version_num FROM alembic_version)                    AS current_revision,
  (SELECT data_type FROM information_schema.columns
     WHERE table_name = 'webhook_targets' AND column_name = 'event_types') AS event_types_type;
```

Expected today: `current_revision = 0070_linkedin_network_messages`,
`event_types_type = ARRAY`. Anything else means production differs from the
migration chain and 0071 must be re-checked before deploying.

## Remaining differences (reported, not fixed)

- No foreign keys on `webhook_targets.user_id` → `users` and
  `webhook_deliveries.target_id` → `webhook_targets` (the model declares both,
  with `ON DELETE CASCADE`). Deleting a user leaves orphan targets and
  deliveries on PostgreSQL. Relevant to GDPR account deletion (open HIGH).
- `webhook_targets.secret_encrypted` nullable in the DB, NOT NULL in the model.
- Width/timezone differences (`VARCHAR(64)` vs 60, `timestamp` vs
  `timestamptz`) — not failures.
- `subject_line_patterns`: model says `updated_at`, table and live SQL say
  `last_updated`; any ORM use of `SubjectLinePattern` would fail on PostgreSQL.
- `strategies.icp_industry`, `strategies.icp_company_size_bucket` exist in the
  DB only (nullable, harmless).
