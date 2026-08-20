# Railway deployment — service topology and migration handling

Written 2026-08-20. Every backend service's build and start command lives in a
committed file under `railway/` — there is deliberately **no** root
`railway.json`, because a service without an explicit config path would inherit
it and a worker would silently run the API's uvicorn command.

## Migrations: two layers, on purpose

**Layer 1 — Railway pre-deploy command** (`railway/api.json` →
`deploy.preDeployCommand`). Railway runs this in a *separate container* after
the build and before the new version starts, with the service's environment
variables (including `DATABASE_URL`) available. A non-zero exit aborts the
deployment, which is what you want from a failed migration. Railway's docs note
the pre-deploy container has **no volume access** — irrelevant here, migrations
touch only the database.

**Layer 2 — PostgreSQL advisory lock** (`app/db/migrate.py`). Railway's
documentation does not state whether the pre-deploy command runs once per
deployment or once per replica, so the lock makes the answer irrelevant. It also
covers the self-hosted `docker-compose.prod.yml` path, which has no pre-deploy
concept at all.

Why both were needed — measured, not assumed:

> Four migrators started simultaneously against a fresh database.
> **Without the lock: 3 of 4 exited non-zero** with
> `IntegrityError` on the `alembic_version` insert. In a container that is a
> crash-loop on every deploy, and failed health checks while it flaps.
> **With the lock: 4 of 4 exited 0**, schema at head, one `alembic_version` row.

The lock is the blocking `pg_advisory_lock`, not `pg_try_advisory_lock`: a
replica that cannot get the lock must *wait* for the migration to finish rather
than boot against the old schema. It is session-scoped and released in a
`finally`, and PostgreSQL drops it if the connection dies — a killed migrator
cannot wedge future deploys.

Never put `alembic upgrade head` in a `startCommand`. Use
`python -m app.db.migrate`.

## Services

Six services in one Railway project. **PostgreSQL** and **Redis** are Railway
plugins — they inject `DATABASE_URL` and `REDIS_URL`; do not set those by hand.

### Start commands live in files, not in the dashboard

Every backend service's start command — **including the `-Q` queue flags** — is
committed under `railway/`. Railway resolves config-as-code **over** dashboard
values, so the file wins even if someone edits the dashboard field.

For each service, set **Settings → Config-as-code → Config File Path** to the
absolute repo path below. That path is the only thing typed by hand, and a typo
in it fails loudly (Railway cannot find the config) rather than silently.

| service | Config File Path | queues consumed |
|---|---|---|
| api | `/railway/api.json` | — |
| worker-pipeline | `/railway/worker-pipeline.json` | `pipeline` |
| worker-outreach | `/railway/worker-outreach.json` | `outreach` |
| worker-learning | `/railway/worker-learning.json` | `learning,default` |
| beat | `/railway/beat.json` | — (publishes only) |
| frontend | root dir `frontend/`, no config file | — |

`tests/test_celery_routing.py` parses `railway/*.json` and fails if any worker
lacks `-Q`, if the union of queues does not cover every routed task, or if a
root `railway.json` reappears (a service without an explicit path would inherit
the API's uvicorn command and consume nothing).

### If you must set a start command by hand

Only if config-as-code is unavailable. Copy these EXACTLY — the `-Q` list is
not optional:

```
# worker-pipeline
celery -A app.workers.celery_app worker -Q pipeline -c 2 --loglevel=info

# worker-outreach
celery -A app.workers.celery_app worker -Q outreach -c 4 --loglevel=info

# worker-learning
celery -A app.workers.celery_app worker -Q learning,default -c 2 --loglevel=info

# beat  (NO -Q: beat publishes, it never consumes)
celery -A app.workers.celery_app beat --loglevel=info
```

A worker started **without** `-Q` consumes only Celery's implicit `celery`
queue, which nothing in this project publishes to. It boots, reports healthy,
logs nothing unusual, and processes nothing. That exact mismatch was a silent
total outage before it was found (session update 9).

## POST-DEPLOY: verify queue consumption before trusting the deploy

A healthy worker is not a working worker. Run these after the workers are live —
do not assume the configuration took effect.

**1. Health endpoint reports celery ok** (requires beat + a worker on `default`):

```
curl -s https://api.leadpilot.com/health
```

Expect `"celery": {"status": "ok", "last_beat_seconds_ago": <60}`. A
`"degraded"` with `"no heartbeat key found"` means beat is not publishing or no
worker is consuming `default`.

**2. Every worker is registered and answers** — from any backend service shell:

```
celery -A app.workers.celery_app inspect ping
```

Expect one `pong` per worker service. A missing worker is a service that failed
to start.

**3. The queues each worker is actually consuming** — this is the check that
catches a wrong `-Q`:

```
celery -A app.workers.celery_app inspect active_queues
```

Every one of `pipeline`, `outreach`, `learning`, `default` must appear. If a
worker reports the queue named `celery`, its `-Q` flag did not take effect —
fix the Config File Path and redeploy.

**4. Queue depths are draining, not growing** — `/admin/celery-stats` (admin
auth) reports depth per queue. Depths that only climb mean tasks are being
published to a queue nobody consumes.

**5. End to end:** create a strategy and confirm it leaves `pending`. If it
sits in `pending` forever, `leadpilot.run_pipeline` is queued to `pipeline` and
nothing is consuming it — check 3 again.

### `NEXT_PUBLIC_API_URL` is baked in at build time

The frontend is a Next.js static export, so this value is compiled into the
bundle. Changing it requires a rebuild and redeploy — editing the variable and
restarting does nothing.

**Set it as a BUILD variable on the frontend service before the first build:**

```
NEXT_PUBLIC_API_URL=https://api.leadpilot.com
```

`frontend/next.config.js` now **fails the production build** when this variable
is unset *or* points at a loopback origin:

```
BUILD FAILED: NEXT_PUBLIC_API_URL is a local origin (http://localhost:8000).
```

That guard exists because the previous behaviour was silent:
`src/lib/api/client.ts` fell back to `http://localhost:8000`, so a build with
the variable missing compiled cleanly, deployed green, passed every health
check, and then sent each visitor's browser to their own machine.

Note the guard checks for localhost specifically, not just "unset" —
`frontend/.env` ships `NEXT_PUBLIC_API_URL=http://localhost:8000` for local
development and Next loads `.env` before evaluating `next.config.js`, so an
unset-only check was already defeated by a file inside the repo.

Verified both ways: `next build` exits 1 with no `out/` directory when the value
is missing or local, and succeeds with `https://api.leadpilot.com`, whose bundle
contains zero occurrences of `localhost:8000`.

## Environment variables

Set on **every** backend service (api, all three workers, beat): `APP_ENV`,
`SECRET_KEY`, `ENCRYPTION_KEY`, `CORS_ORIGINS`, `PUBLIC_BASE_URL`,
`SENDER_IDENTITY`, `ADMIN_EMAIL`, `ANTHROPIC_API_KEY`, `FRONTEND_URL`, plus any
integration credentials in use.

`PUBLIC_BASE_URL` builds unsubscribe links and `SENDER_IDENTITY` is the CAN-SPAM
postal address in every email footer — both default to unusable development
values, so the guard rejects them.

`app/core/production_guard.py` refuses to start the api when `APP_ENV` is
production and any of `SECRET_KEY`, `ENCRYPTION_KEY`, `CORS_ORIGINS`,
`PUBLIC_BASE_URL` or `SENDER_IDENTITY` is missing or unsafe, reporting every
problem at once. A failed boot on first deploy is
almost always a variable that was set on api but not on the workers.

`CORS_ORIGINS` is a **plain comma-separated list**, never a JSON array — see
`tests/test_cors_format.py`.

## First-deploy sequence

`ADMIN_EMAIL` promotes an existing user; it does not create one:

1. Deploy with `ADMIN_EMAIL` already set.
2. Sign up once with that address through the deployed frontend or API.
3. Restart the api service — startup promotes the account to admin.

## Rollback

Railway keeps previous deployments: open the service → Deployments → the last
good one → Redeploy. Note that a rollback does **not** revert a migration, so a
schema change must be backwards-compatible with the previous image, or the
rollback needs a matching downgrade applied deliberately.
