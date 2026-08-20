# Free-tier deployment — Render + Neon + Upstash + Vercel

A $0, no-credit-card path to a live deployment.

**This is additive.** `railway/*.json` and `DEPLOY_RAILWAY.md` remain the
documented paid-tier path and are untouched. Nothing here replaces them; if you
later move to Railway, that config still works.

| Piece | Provider | Free plan reality |
|---|---|---|
| Frontend | Vercel | Static export, no sleep |
| API | Render Web Service (Docker) | **Sleeps after 15 min idle**, 30–60s cold start |
| Worker + beat | Render Web Service (Docker) | **Sleeps after 15 min idle — needs an external pinger** |
| PostgreSQL | Neon | 0.5 GB, autosuspends |
| Redis | Upstash | 256 MB, 500k commands/month |

> Read **KNOWN LIMITATIONS OF THIS FREE STACK** at the bottom before relying on
> this for anything with a paying customer attached. The worker is the sharp
> edge.

---

## Part 1 — Render: the API service

`render.yaml` at the repo root is a Render **Blueprint**: point Render at the
GitHub repo and it creates both services from that file rather than from
dashboard clicks. Same reasoning as `railway/*.json` — start commands and
health-check paths live in a reviewed file, not in a text box nobody can diff.

The API builds the Dockerfile's named `production` stage.

### Verified before writing this

Built locally with `docker build --target production` on 2026-08-20 and
inspected the result. Three real defects surfaced; all are fixed, and all of
them would have broken the Railway deploy too:

1. **`app.main` did not import inside the image at all.** `structlog` is
   imported unconditionally by `app/core/logging.py`, which six `app/api/*`
   modules import — and it was never declared in `pyproject.toml`, so
   `pip install .` never installed it. The API could not boot in *any*
   container. It only worked locally because dev machines had structlog from
   somewhere else. `typer` and `rich` were missing the same way, which would
   have broken the documented `python -m app.cli.create_admin` step.
2. **No `.dockerignore` existed**, so `COPY . .` copied the whole working tree:
   `/code` was **877 MB** and contained `/code/.env` with the live
   `ANTHROPIC_API_KEY`, `SECRET_KEY` and `ENCRYPTION_KEY`. See the note under
   *Scope of the `.env` finding* below — it is narrower than it first looks,
   but it is still worth closing. After adding `.dockerignore`: **4.8 MB**, no
   `.env`, build context down from 213 MB+ to 22 kB.
3. **`app/workers/webhook_tasks.py` imported `services.webhook_delivery`** —
   there is no top-level `services` package; the module is
   `app/services/webhook_delivery.py`. Every *signed* outbound webhook raised
   `ModuleNotFoundError` and retried forever, while unsigned deliveries worked
   fine and hid it.

#### Scope of the `.env` finding

Render builds from a **git clone**, and `.env` is gitignored (verified: 398
tracked files, 3.6 MB, and `.env` has never been committed — the key does not
appear in any commit). So `.env` was never going to reach Render's build
context.

The exposure was for builds from a **local working tree**, which is exactly
what `docker-compose.prod.yml` does (`context: .`). Anyone running
`docker compose -f docker-compose.prod.yml build` produced an image with live
secrets baked into a layer. `.dockerignore` closes that, and as a bonus makes
local builds byte-for-byte comparable to what Render produces.

### Environment variables — Render dashboard → leadpilot-api → Environment

Every name below is what the code actually reads (`app/config.py` and
`app/core/config.py`), not a guess.

| Variable | Value | Notes |
|---|---|---|
| `APP_ENV` | `production` | Already in `render.yaml`. Turns on `production_guard`. |
| `LOG_LEVEL` | `INFO` | Already in `render.yaml`. |
| `DATABASE_URL` | Neon connection string | See Part 3. |
| `REDIS_URL` | Upstash `rediss://…` | Cache, rate limiter, heartbeat. |
| `CELERY_BROKER_URL` | Upstash + `?ssl_cert_reqs=required` | See Part 3 — **the suffix is mandatory**. |
| `CELERY_RESULT_BACKEND` | same as broker | Same suffix. |
| `SECRET_KEY` | 48+ random bytes | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `ENCRYPTION_KEY` | Fernet key | `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
| `ANTHROPIC_API_KEY` | your key | |
| `CORS_ORIGINS` | `https://your-app.vercel.app` | **Comma-separated, never a JSON array.** |
| `PUBLIC_BASE_URL` | `https://leadpilot-api.onrender.com` | Builds unsubscribe links (CAN-SPAM). |
| `FRONTEND_URL` | your Vercel URL | |
| `SENDER_IDENTITY` | real postal address | CAN-SPAM footer. A placeholder is rejected at boot. |
| `ADMIN_EMAIL` | your email | Promotes an existing user; does not create one. |

`app/core/production_guard.py` refuses to boot when `APP_ENV=production` and
any of `SECRET_KEY`, `ENCRYPTION_KEY`, `CORS_ORIGINS`, `PUBLIC_BASE_URL` or
`SENDER_IDENTITY` is missing or unsafe, and reports every problem at once.
Low-entropy values (`xxxx…`) are rejected too.

**First-deploy admin sequence** (unchanged from Railway): deploy with
`ADMIN_EMAIL` set → sign up once with that address → restart the api service.

---

## Part 2 — Render: Celery worker + beat in ONE free service

Render's free plan has **no free background-worker type** — `type: worker` is
paid-only. A free Web Service must bind `$PORT` and answer HTTP. So the worker
service runs three processes:

```
scripts/render_worker_entrypoint.sh
  ├── celery worker -Q pipeline,outreach,learning,default   (background)
  ├── celery beat                                            (background)
  └── uvicorn app.worker_health:app --port $PORT             (background)
      └── wait -n  →  if ANY child exits, kill the rest and exit non-zero
```

`app/worker_health.py` serves exactly one route and no application traffic. The
real API is deliberately **not** mounted there — that would publish all ~97
routes on a second origin whose CORS, rate limits and admin surface nobody
reasoned about.

### The `-Q` list is load-bearing

`-Q pipeline,outreach,learning,default` lists every queue
`app/workers/celery_app.py` routes to. Omitting one strands every task routed
to it, with no error anywhere. That exact bug — nothing consuming the queue
tasks were published to — was a total production outage found in session
update 9 of `CLAUDE_CODE_HANDOFF.md`. **If you add a route to `task_routes`,
add its queue here.**

### Two failure modes, and which one is handled

| Failure | Handled? |
|---|---|
| Worker process crashes | **Yes.** `wait -n` exits the service → Render restarts it. `/health` also returns 503 (zombie-aware) as a backstop. |
| Service asleep from no traffic | **No — this is on you.** See the pinger below. |

Verified live on 2026-08-20 against the built image: worker reported
`celery@… ready` bound to all four queues, `/health` returned
`{"worker":{"status":"ok"},"beat":{"status":"ok"}}`, a `leadpilot.ping`
round-tripped through the container (`received` → `succeeded: 'pong'` in its own
log, with no other worker running), and `kill -9` on the worker made the
container exit 137 instead of sitting there looking healthy.

The zombie check matters: an earlier run had both Celery processes dead on the
missing-`structlog` error while `/health` cheerfully reported both `ok`,
because `os.kill(pid, 0)` succeeds for an unreaped process. `/health` now reads
`/proc/<pid>/stat` and treats state `Z` as down.

### Environment variables — leadpilot-worker

**Every variable from the API table above, with identical values**, plus
`CELERY_CONCURRENCY=2` (already in `render.yaml`; free instances are 512 MB and
each Celery child is a full Python process).

A first-deploy failure here is almost always a variable set on the api and
forgotten on the worker — the production guard runs on both.

---

## Part 2b — THE PINGER IS REQUIRED, NOT OPTIONAL

> A free Render Web Service is spun down after **~15 minutes** with no inbound
> HTTP request. **A sleeping service runs no processes.** The Celery worker is
> not paused — it does not exist. Queued tasks are simply not consumed.
>
> **Nothing errors. No alert fires.** Queue depth in `/admin/celery-stats`
> grows and every dashboard stays green. If the pinger stops, task processing
> stops silently.
>
> This is an accepted trade-off of running for $0, **not a bug to fix in
> code.** The fix is $7/mo (below).

### Set this up at cron-job.org (you, in a browser)

1. Create a free account at <https://cron-job.org>.
2. **Create cronjob** →
   - **URL**: `https://leadpilot-worker.onrender.com/health`
     *(your worker service's URL — the worker, not the api)*
   - **Schedule**: every **10 minutes** (under the 15-minute sleep threshold
     with margin for a missed run)
   - **Enable "Notify on failure"** — you will then hear about a dead worker,
     since `/health` returns 503 when the Celery children are gone.
3. Optionally add a second job against the **api**'s `/health` to keep
   first-request latency down. Cosmetic, not correctness.

Ten-minute pings ≈ 4,320 requests/month, comfortably inside Render's free
750 instance-hours (one always-awake service is ~730 h/month, so two free
services being pinged constantly will exceed the shared allowance — pin the
worker and let the api sleep if you need to economise).

---

## Part 3 — Neon (Postgres) and Upstash (Redis)

Both verified live on 2026-08-20 against the real providers.

### Which env var name goes where

Read from `app/config.py` and `app/core/config.py` — these are the names the
code actually reads, not guesses.

| Provider value | Env var(s) | Required suffix |
|---|---|---|
| Neon connection string | `DATABASE_URL` | `?sslmode=require` |
| Neon **direct** (non-pooled) string | `MIGRATION_DATABASE_URL` | `?sslmode=require` |
| Upstash TCP string | `REDIS_URL` | none — bare `rediss://` |
| Upstash TCP string | `CELERY_BROKER_URL` | **`?ssl_cert_reqs=required`** |
| Upstash TCP string | `CELERY_RESULT_BACKEND` | **`?ssl_cert_reqs=required`** |

`settings.broker_url` falls back to `redis_url` when `CELERY_BROKER_URL` is
unset — so setting only `REDIS_URL` would hand Celery a bare `rediss://` and
break the worker at boot. Set all three explicitly.

### Why Celery needs `?ssl_cert_reqs=required`

Not a guess — reproduced directly. Celery's Redis **result backend** refuses a
bare `rediss://`:

```
ValueError: A rediss:// URL must have parameter ssl_cert_reqs and this must be
set to CERT_REQUIRED, CERT_OPTIONAL, or CERT_NONE
```

With the suffix it resolves to `SSLConnection` / `ssl_cert_reqs=2`
(`CERT_REQUIRED`), which is what you want — certificates verified.

The **broker** tolerates a bare `rediss://`, and so does `redis-py`, which is
why plain `REDIS_URL` needs nothing. Only the result backend is strict.

### Neon: `sslmode=require` needs no code change

`app/db/base.py` passes the URL straight to `create_engine`, psycopg2 handles
`sslmode` natively, and `pool_pre_ping=True` was already set — which is what
makes Neon's autosuspend survivable rather than a source of dead connections.

`pg_stat_ssl` reports `ssl = false` on Neon. That is a reporting artifact of
Neon terminating TLS at its proxy, **not** an unencrypted connection —
confirmed by attempting `sslmode=disable`, which Neon **refuses**. TLS is
mandatory on the wire.

### Migrations must NOT run through the Neon POOLER

The single most important finding of Part 3.

`app/db/migrate.py` serialises concurrent migrators with
`pg_advisory_lock`, which is **session-scoped**. Neon's pooled endpoint
(`…-pooler…`) is PgBouncer in transaction mode: it hands each statement
whatever server connection is free, so the lock is taken on one backend and
the next statement runs on another.

Measured against the live database, two migrators behaving exactly as
`migrate.py` does:

| Endpoint | Second migrator's `pg_try_advisory_lock` | Verdict |
|---|---|---|
| Pooled (`-pooler`) | **acquired the lock A was holding** | lock does nothing |
| Direct (no `-pooler`) | correctly refused | works |

So the race protection added in session update 11 is silently inert on the
pooled endpoint. Fix: set **`MIGRATION_DATABASE_URL`** to Neon's *direct*
connection string while `DATABASE_URL` stays pooled for normal traffic.
`app/db/migrate.py::_migration_url()` prefers it and passes it through to
Alembic, so the lock and the migration act on the same endpoint. Unset, the
behaviour is exactly as before.

Neon's own guidance matches: direct connection for migrations and DDL, pooled
for application traffic.

### Verified results

```
Neon PostgreSQL       connect OK   server_version 18.6   database neondb
Upstash (broker)      connect OK   transport rediss
Upstash (backend)     PING PONG    SSLConnection   ssl_cert_reqs=2
Upstash (app client)  PING PONG    SSLConnection
```

Alembic chain applied clean on the first run — all 17 revisions,
`0001_initial_models` → `0014_strategy_pattern_inputs`, exit 0, advisory lock
acquired and released. Resulting schema: **26 tables, 85 indexes, 25 foreign
keys**, and zero model tables missing versus `Base.metadata`.

## Part 4 — Vercel (frontend)

*(filled in during Part 4)*

---

## KNOWN LIMITATIONS OF THIS FREE STACK

Read this before pointing a customer at it.

### 1. Worker depends on an external pinger — highest risk
No pinger, no task processing, no error. Everything upstream keeps accepting
work. This is the single most fragile part of the stack.

**Fix first, before any other paid upgrade: move the worker to a Render
Background Worker at $7/mo.** It never sleeps, needs no pinger, needs no health
server, and removes an entire failure mode. Do this the moment there is any
revenue.

### 2. API cold starts: 30–60 seconds
After 15 minutes idle the first request hangs while the container boots. A
visitor hitting the site cold may think it is broken. Strategy generation is a
~60-minute pipeline, so the cold start is irrelevant *once work is queued* —
it is a first-impression problem, not a throughput one.

### 3. Neon free tier
0.5 GB storage and the compute autosuspends after ~5 minutes idle, adding a
few hundred ms to the first query. `create_engine(..., pool_pre_ping=True)` is
already set in `app/db/base.py`, which is what makes a dropped idle connection
reconnect instead of erroring — this stack would be flaky without it.

### 4. Upstash free tier
256 MB and **500,000 commands/month**. Celery polls the broker continuously;
an always-awake worker can burn through that. Ironically the 15-minute sleep
helps here. Watch the Upstash dashboard in week one.

### 5. No horizontal scale, no persistent disk
One instance each. Render's free disk is ephemeral — anything written to it is
gone on restart, which is why beat's schedule lives in `/tmp` and is rebuilt
from code on boot. Uploaded theme backgrounds (`media/`) will **not** survive a
restart; that needs object storage before it is a real feature.

### 6. Migrations run from the api service only
`preDeployCommand: python -m app.db.migrate` is on the api, not the worker, so
they cannot race. It is wrapped in a `pg_advisory_lock` regardless (session
update 11: 3 of 4 concurrent migrators died without it).

### Upgrade order, when money exists
1. **Render Background Worker — $7/mo.** Removes the pinger dependency.
2. Render API to a paid instance — removes cold starts.
3. Neon / Upstash paid tiers — only when you actually hit the caps.
