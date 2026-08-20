"""Prove the test-only /debug router cannot be reached in production.

Boots a REAL uvicorn server per scenario and issues live HTTP requests.
A 404 is the only acceptable production result: a 401/403 would mean the
router mounted and merely rejected the caller, which is not good enough.

Scenario 4 is the control - if the routes are NOT reachable when the flag is
deliberately on, the other three scenarios prove nothing.

Run:  python scripts/verify_debug_router_guard.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Probe an unauthenticated route, an authenticated one and a state-mutating
# one, so a pass cannot be an artefact of auth rejecting before routing.
PROBES = [
    ("GET", "/debug/whatsapp-status?message_id=x"),   # unauthenticated by design
    ("GET", "/debug/deferred-sends"),                 # requires a bearer token
    ("POST", "/debug/inject-verification-fail"),      # state-mutating
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fernet_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def _base_env(**overrides: str) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("ENABLE_DEBUG_ROUTES", None)
    env.update({
        "DATABASE_URL": "postgresql://leadpilot:leadpilot@localhost:5433/clienthunter_test",
        "REDIS_URL": "redis://localhost:6380/15",
        "SECRET_KEY": "verify-only-not-a-real-secret",
        "ENCRYPTION_KEY": _fernet_key(),
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    })
    env.update(overrides)
    return env


def _request(url: str, method: str, timeout: float = 20.0) -> tuple[int, str]:
    """Never raises. Returns (-1, reason) on a transport failure."""
    req = urllib.request.Request(
        url, method=method,
        data=b"{}" if method == "POST" else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()[:120].decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:120].decode(errors="replace")
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def run_scenario(name: str, env_overrides: dict[str, str], expect_404: bool) -> bool:
    port = _free_port()
    env = _base_env(**env_overrides)

    # Server output goes to a FILE, never an unread subprocess.PIPE. Nothing
    # here drains a pipe, so uvicorn blocks on its first sizeable write and
    # every probe then times out - which looks exactly like a hung route.
    log_path = Path(tempfile.gettempdir()) / f"debug_guard_{port}.log"
    log_file = open(log_path, "w+", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(REPO), env=env, stdout=log_file, stderr=subprocess.STDOUT,
    )

    print(f"\n[{name}]")
    print(f"   APP_ENV={env.get('APP_ENV')!r} "
          f"ENABLE_DEBUG_ROUTES={env.get('ENABLE_DEBUG_ROUTES', '<unset>')!r}")
    try:
        base = f"http://127.0.0.1:{port}"
        ready = False
        for _ in range(200):
            if proc.poll() is not None:
                log_file.flush()
                out = log_path.read_text(encoding="utf-8", errors="replace")
                print(f"   server exited early (rc={proc.returncode})")
                print("   " + "\n   ".join(out.strip().splitlines()[-8:]))
                return False
            # _request never raises, so poll on the STATUS, not an exception.
            if _request(base + "/health", "GET", timeout=2.0)[0] > 0:
                ready = True
                break
            time.sleep(0.15)
        if not ready:
            print("   server never became ready")
            return False

        ok = True
        for method, path in PROBES:
            status, body = _request(base + path, method)
            if expect_404:
                good = status == 404
            else:
                # Reachable means a REAL http status that is not 404. A
                # transport failure (-1) must never count as "mounted".
                good = status > 0 and status != 404
            if not good:
                ok = False
            note = ""
            if expect_404 and status in (401, 403):
                note = "  <-- ROUTER MOUNTED (auth-rejected, not absent)"
            elif status == -1:
                note = f"  <-- transport failure: {body}"
            print(f"   {'PASS' if good else 'FAIL'}  {method:4} {path:45} -> {status}{note}")
        return ok
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()
        try:
            log_path.unlink()
        except OSError:
            pass


def main() -> int:
    results = [
        ("production, flag unset (the real deployment case)",
         run_scenario("1. PRODUCTION, flag unset",
                      {"APP_ENV": "production"}, expect_404=True)),
        ("production, flag wrongly set to true",
         run_scenario("2. PRODUCTION, ENABLE_DEBUG_ROUTES=true",
                      {"APP_ENV": "production", "ENABLE_DEBUG_ROUTES": "true"},
                      expect_404=True)),
        ("development, flag unset (default off)",
         run_scenario("3. DEVELOPMENT, flag unset",
                      {"APP_ENV": "development"}, expect_404=True)),
        ("test, flag on (CONTROL - routes must be REACHABLE here)",
         run_scenario("4. TEST, ENABLE_DEBUG_ROUTES=true",
                      {"APP_ENV": "test", "ENABLE_DEBUG_ROUTES": "true"},
                      expect_404=False)),
    ]

    print("\n" + "=" * 72)
    all_ok = True
    for label, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        all_ok = all_ok and ok
    print("=" * 72)
    print("RESULT:", "GUARD VERIFIED" if all_ok else "GUARD BROKEN")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
