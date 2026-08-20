"""Tiny HTTP surface so Render's FREE tier will host the Celery worker.

Render's free plan has no background-worker service type — only Web Services,
which must bind to $PORT and answer HTTP. So the worker container runs a
minimal health server alongside the Celery processes purely to qualify. It
serves no application traffic: exactly one route, no database, no auth.

DO NOT mount the real API (app.main) here. That would publish all ~97 routes on
a second public origin whose CORS, rate limits and admin surface nobody
reasoned about.

WHY THIS REPORTS REAL LIVENESS INSTEAD OF ALWAYS 200
    The obvious version returns 200 unconditionally. That creates precisely the
    failure this project keeps hitting: the Celery worker dies, the HTTP server
    happily keeps answering, Render's health check stays green, and tasks pile
    up unconsumed with no error anywhere. (See CLAUDE_CODE_HANDOFF.md session
    update 9 — the queue-routing outage had the same shape: everything looked
    healthy while nothing was consumed.)

    So /health checks that the supervised child processes are actually alive
    and returns 503 if they are not, which makes Render restart the service.
    A crashed worker becomes a visible restart rather than silent nothing.

The PIDs come from the entrypoint script via WORKER_PID_FILE / BEAT_PID_FILE.
When those are unset — running this module by hand — the checks are skipped
rather than failing, so local use is not booby-trapped.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(
    title="LeadPilot worker health",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _pid_alive(pid: int) -> bool:
    """True if the process exists AND is not a zombie.

    The zombie check is the whole point. `os.kill(pid, 0)` succeeds for a
    process that has exited but not yet been reaped, because the PID still
    occupies the process table. Observed exactly that on 2026-08-20: the Celery
    worker and beat both died instantly on a missing dependency, and /health
    cheerfully reported {"worker": "ok", "beat": "ok"} with their PIDs — the
    silent-green-while-broken failure this endpoint exists to prevent.

    On Linux (which is what the container runs) /proc/<pid>/stat field 3 is the
    state character; 'Z' means zombie. Where /proc is unavailable we fall back
    to the signal check, which is better than nothing.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        # Windows raises a bare OSError (WinError 87) for an unknown PID rather
        # than ProcessLookupError. Treat anything unrecognised as not alive:
        # a false "down" costs one restart, a false "ok" hides a dead worker.
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return True  # no procfs — fall back to the signal result
    # comm can contain spaces and parentheses, so split after the final ')'.
    state = stat.rsplit(")", 1)[1].split()[0]
    return state != "Z"


def _check(pid_file_env: str) -> dict:
    path = os.getenv(pid_file_env)
    if not path:
        return {"status": "unmonitored", "reason": f"{pid_file_env} not set"}
    try:
        pid = int(Path(path).read_text().strip())
    except (OSError, ValueError) as exc:
        return {"status": "down", "reason": f"cannot read pid file: {exc}"}
    if _pid_alive(pid):
        return {"status": "ok", "pid": pid}
    return {"status": "down", "pid": pid, "reason": "process is gone"}


@app.get("/health")
def health() -> JSONResponse:
    """Liveness for Render's health check AND for the external keep-alive ping.

    The same URL serves both jobs, which is deliberate: the pinger that keeps
    this free service awake is also the thing that surfaces a dead worker.
    """
    components = {
        "worker": _check("WORKER_PID_FILE"),
        "beat": _check("BEAT_PID_FILE"),
    }
    degraded = [n for n, c in components.items() if c["status"] == "down"]
    body = {
        "status": "degraded" if degraded else "ok",
        "service": "celery-worker",
        "components": components,
    }
    if degraded:
        body["down"] = degraded
        return JSONResponse(body, status_code=503)
    return JSONResponse(body, status_code=200)


@app.get("/")
def root() -> dict:
    return {"service": "leadpilot-worker", "health": "/health"}
