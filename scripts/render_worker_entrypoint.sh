#!/usr/bin/env bash
#
# Render FREE-tier Celery worker: worker + beat + a health HTTP server, all in
# one service.
#
# WHY THIS EXISTS
# Render's free plan has no background-worker service type. Only Web Services
# are free, and a Web Service must bind $PORT and answer HTTP or Render marks
# the deploy failed. So the Celery processes ride along inside what Render
# believes is a web service. app/worker_health.py is that HTTP surface; it
# serves one route and no application traffic.
#
# ============================================================================
# READ THIS BEFORE RELYING ON IT: THIS SERVICE SLEEPS
# ============================================================================
# A free Render Web Service is spun down after ~15 MINUTES with no inbound HTTP
# request. A sleeping service runs NO PROCESSES — the Celery worker is not
# paused, it does not exist. Queued tasks are simply not consumed.
#
# Nothing errors. No alert fires. The queue depth in /admin/celery-stats grows
# and everything else looks fine. This is the same shape as the queue-routing
# outage in CLAUDE_CODE_HANDOFF.md session update 9, and it is just as invisible.
#
# An EXTERNAL PINGER hitting this service's /health every ~10 minutes is
# therefore REQUIRED, not optional — it is load-bearing infrastructure. See
# DEPLOY_RENDER_FREE.md for the cron-job.org setup. If the pinger stops, task
# processing stops silently.
#
# This is an accepted trade-off of running for $0, NOT a bug to fix in code.
# The real fix is $7/mo for a Render Background Worker, which never sleeps and
# needs no pinger. Do that first, before any other paid upgrade.
# ============================================================================
#
# QUEUES
# -Q lists every queue app/workers/celery_app.py routes to:
#   pipeline, outreach, learning, default
# One worker consumes all four because the free tier gives us exactly one
# service to work with. Omitting a queue here strands every task routed to it
# with no error anywhere — that exact bug (nothing consumed the queue tasks
# were published to) was a total production outage found in session update 9.
# If you add a route in celery_app.py's task_routes, add its queue here.
#
# SUPERVISION
# All three processes run as children and `wait -n` returns as soon as ANY of
# them exits. We then kill the rest and exit non-zero so Render restarts the
# whole service. Without this, a crashed Celery worker would leave the HTTP
# server answering 200 forever and Render would see a perfectly healthy service
# consuming nothing. app/worker_health.py independently reports 503 if a child
# died, which covers the window before the restart lands.

set -euo pipefail

PORT="${PORT:-10000}"
CONCURRENCY="${CELERY_CONCURRENCY:-2}"
LOGLEVEL="${CELERY_LOGLEVEL:-info}"

# Beat needs a writable schedule path. Render's free disk is ephemeral, so this
# lives in /tmp and is rebuilt on every boot — fine, the schedule is declared in
# code, not stored.
BEAT_SCHEDULE="${CELERY_BEAT_SCHEDULE:-/tmp/celerybeat-schedule}"

export WORKER_PID_FILE="${WORKER_PID_FILE:-/tmp/celery-worker.pid}"
export BEAT_PID_FILE="${BEAT_PID_FILE:-/tmp/celery-beat.pid}"

echo "[entrypoint] starting Celery worker (queues: pipeline,outreach,learning,default)"
celery -A app.workers.celery_app worker \
  -Q pipeline,outreach,learning,default \
  --concurrency "${CONCURRENCY}" \
  --loglevel "${LOGLEVEL}" &
WORKER_PID=$!
echo "${WORKER_PID}" > "${WORKER_PID_FILE}"

echo "[entrypoint] starting Celery beat"
celery -A app.workers.celery_app beat \
  --schedule "${BEAT_SCHEDULE}" \
  --loglevel "${LOGLEVEL}" &
BEAT_PID=$!
echo "${BEAT_PID}" > "${BEAT_PID_FILE}"

echo "[entrypoint] starting health server on 0.0.0.0:${PORT} (Render requires a bound port)"
uvicorn app.worker_health:app --host 0.0.0.0 --port "${PORT}" &
HTTP_PID=$!

shutdown() {
  echo "[entrypoint] shutting down children"
  kill "${WORKER_PID}" "${BEAT_PID}" "${HTTP_PID}" 2>/dev/null || true
  wait || true
}
trap shutdown TERM INT

# Return as soon as any child exits — see SUPERVISION above.
wait -n
EXIT_CODE=$?
echo "[entrypoint] a child process exited (code ${EXIT_CODE}); stopping the service so Render restarts it"
shutdown
exit "${EXIT_CODE:-1}"
