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
#   pipeline, outreach, learning, default, notifications
# One worker consumes all five because the free tier gives us exactly one
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

# Every line a child writes (stdout AND stderr) is prefixed with its name, so
# Render's single interleaved log stream says who said what. Pure bash, one
# line at a time, so nothing is held back in a buffer when a child dies.
prefix_lines() {
  local tag="$1" line
  while IFS= read -r line || [[ -n "${line}" ]]; do
    printf '[%s] %s\n' "${tag}" "${line}"
  done
}

# The `> >(prefix_lines …) 2>&1 &` form keeps `$!` as the PID of the child
# itself (not of the prefixer), which the PID files and the supervision below
# both depend on.
echo "[entrypoint] starting Celery worker (queues: pipeline,outreach,learning,default,notifications)"
celery -A app.workers.celery_app worker \
  -Q pipeline,outreach,learning,default,notifications \
  --concurrency "${CONCURRENCY}" \
  --loglevel "${LOGLEVEL}" > >(prefix_lines worker) 2>&1 &
WORKER_PID=$!
echo "${WORKER_PID}" > "${WORKER_PID_FILE}"

echo "[entrypoint] starting Celery beat"
celery -A app.workers.celery_app beat \
  --schedule "${BEAT_SCHEDULE}" \
  --loglevel "${LOGLEVEL}" > >(prefix_lines beat) 2>&1 &
BEAT_PID=$!
echo "${BEAT_PID}" > "${BEAT_PID_FILE}"

echo "[entrypoint] starting health server on 0.0.0.0:${PORT} (Render requires a bound port)"
uvicorn app.worker_health:app --host 0.0.0.0 --port "${PORT}" > >(prefix_lines health) 2>&1 &
HTTP_PID=$!

child_name() {
  case "$1" in
    "${WORKER_PID}") echo "worker" ;;
    "${BEAT_PID}")   echo "beat" ;;
    "${HTTP_PID}")   echo "health-server" ;;
    *)               echo "unknown (pid $1)" ;;
  esac
}

shutdown() {
  echo "[entrypoint] shutting down children"
  kill "${WORKER_PID}" "${BEAT_PID}" "${HTTP_PID}" 2>/dev/null || true
  wait || true
}

SIGNALLED=""
on_signal() {
  SIGNALLED="$1"
  echo "[entrypoint] received SIG${SIGNALLED}"
  shutdown
}
trap 'on_signal TERM' TERM
trap 'on_signal INT' INT

# Return as soon as any child exits — see SUPERVISION above.
#
# errexit is OFF for this block and only this block. `wait` returns the exit
# status of the child it reaped, so under `set -e` a child that failed made
# bash abort on the `wait` line itself: the lines that report the failure and
# stop the other children never ran, and the deploy died with no word on which
# process had gone or why.
EXITED_PID=""
EXIT_CODE=0
set +e
if (( BASH_VERSINFO[0] > 5 || (BASH_VERSINFO[0] == 5 && BASH_VERSINFO[1] >= 1) )) \
    && [[ -z "${ENTRYPOINT_FORCE_POLL:-}" ]]; then
  # bash >= 5.1: `-p` stores the PID of the child that `wait -n` reaped.
  wait -n -p EXITED_PID "${WORKER_PID}" "${BEAT_PID}" "${HTTP_PID}"
  EXIT_CODE=$?
else
  # Older bash has no `wait -n -p`: poll the three PIDs once a second, then
  # reap the one that has gone to collect its exit status.
  while [[ -z "${EXITED_PID}" && -z "${SIGNALLED}" ]]; do
    for pid in "${WORKER_PID}" "${BEAT_PID}" "${HTTP_PID}"; do
      if ! kill -0 "${pid}" 2>/dev/null; then
        EXITED_PID="${pid}"
        wait "${pid}"
        EXIT_CODE=$?
        break
      fi
    done
    [[ -z "${EXITED_PID}" ]] && sleep 1
  done
fi
set -e

if [[ -n "${SIGNALLED}" ]]; then
  # Render stopping the service (a deploy, a restart): not a child failure.
  echo "[entrypoint] stopped by SIG${SIGNALLED}"
  exit 143
fi

echo "[entrypoint] child '$(child_name "${EXITED_PID}")' exited with code ${EXIT_CODE}; stopping the service so Render restarts it"
shutdown
# Always non-zero, so Render restarts the service: a child that exits 0 has
# still gone, and this service is not doing its job without all three.
if [[ "${EXIT_CODE}" -eq 0 ]]; then
  EXIT_CODE=1
fi
exit "${EXIT_CODE}"
