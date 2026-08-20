#!/usr/bin/env bash
#
# Render entrypoint for the API service: migrate, then serve.
#
# WHY THIS FILE EXISTS INSTEAD OF AN INLINE dockerCommand
#
# render.yaml used to carry the whole thing inline:
#
#     dockerCommand: sh -c "python -m app.db.migrate && uvicorn app.main:app ..."
#
# Render's deploy failed with status 127 and:
#
#     sh: 1: python -m app.db.migrate && uvicorn app.main:app --host 0.0.0.0
#     --port 10000 --proxy-headers --forwarded-allow-ips='*': not found
#
# The entire command — every flag, the `&&`, the lot — was looked up as ONE
# program name. Whatever tokenizer Render applies to `dockerCommand` did not
# preserve the nested double quotes around the `sh -c` argument, so the shell
# never saw `&&` as a separator. Render's Blueprint spec does not document
# whether `dockerCommand` is shell-interpreted or exec'd as argv, and its only
# examples are single commands with no operators or quoting — so there is no
# documented escaping to get right.
#
# A script sidesteps the question completely. `bash scripts/…` is two bare
# tokens with no quotes and no operators, which is the shape Render's own
# examples use and the shape the worker service already uses successfully. All
# the shell logic lives in here, where a real shell is unambiguously in charge.
#
# BEHAVIOUR IS IDENTICAL TO THE INLINE VERSION IT REPLACES
#   * `set -e` gives the `&&` semantics: a failed migration aborts the boot and
#     uvicorn is never started, so a half-migrated schema cannot serve traffic.
#   * `exec` hands PID 1 to uvicorn, so Render's SIGTERM on shutdown/redeploy
#     reaches the server directly rather than a bash wrapper that would ignore
#     it and force a 30-second kill.
#
# --proxy-headers + --forwarded-allow-ips is what makes request.client.host the
# real client IP behind Render's proxy. app/core/rate_limiting.py's client_ip()
# keys the auth rate limiter on it; without these every request on the internet
# would share a single bucket.

set -euo pipefail

# Render injects $PORT. The fallback only matters when running the image by
# hand, and matches the port Render's own default happens to use.
PORT="${PORT:-10000}"

echo "[api-entrypoint] running database migrations"
python -m app.db.migrate

echo "[api-entrypoint] migrations complete; starting uvicorn on 0.0.0.0:${PORT}"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
