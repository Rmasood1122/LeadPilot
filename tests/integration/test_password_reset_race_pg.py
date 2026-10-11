"""Password reset under real concurrency, on PostgreSQL (review fix 3).

Two requests carrying the SAME reset link, in two connections: before the fix
both passed `used_at IS NULL` on a plain read, both set a password, and the
LAST commit won silently (probe: review-pg/reset_race_probe.py). Now the claim
is a conditional UPDATE: the second request blocks on the row, then matches
nothing and changes nothing.

Two concurrent reset REQUESTS for one account: the account row is locked
(SELECT ... FOR UPDATE), so the second waits, sees the first's link inside the
cooldown, and mints nothing -- one live link, never two.

Each test runs on its own throwaway database migrated to head.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from tests.integration.conftest import TEST_DATABASE_URL

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture()
def session_factory():
    base = make_url(TEST_DATABASE_URL)
    assert base.host in ("localhost", "127.0.0.1"), "scratch databases are local only"
    name = f"lp_reset_race_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    proc = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=str(REPO),
                          env={**os.environ, "DATABASE_URL": url},
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr[-1500:]
    engine = create_engine(url)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _account(S):
    from app.db.models import User
    from app.services import auth as auth_svc

    s = S()
    user = User(email=f"race-{uuid.uuid4().hex[:6]}@x.io", email_verified=True,
                password_hash=auth_svc.hash_password("original-pass-1"))
    s.add(user)
    s.commit()
    s.close()
    return user.id


def _blocked(thread: threading.Thread, seconds: float = 1.5) -> bool:
    thread.join(seconds)
    return thread.is_alive()


def test_two_redeems_of_one_link_change_the_password_once(session_factory):
    from app.db.models import User
    from app.services import auth as auth_svc
    from app.services import password_reset as pr

    S = session_factory
    uid = _account(S)
    s = S()
    raw = pr.issue_token(s, s.get(User, uid))
    s.commit()
    s.close()

    a, b = S(), S()
    assert pr.redeem(a, raw, "attacker-pass-A")[0] == pr.RESET   # A holds the row
    result: dict = {}

    def second():
        result["status"] = pr.redeem(b, raw, "victim-pass-B")[0]
        b.commit()

    t = threading.Thread(target=second)
    t.start()
    assert _blocked(t), "the second redeem must wait for the first"
    a.commit()
    t.join(10)
    assert not t.is_alive()
    assert result["status"] == pr.INVALID
    a.close()
    b.close()

    s = S()
    user = s.get(User, uid)
    assert auth_svc.verify_password("attacker-pass-A", user.password_hash)
    assert not auth_svc.verify_password("victim-pass-B", user.password_hash)
    s.close()


def test_two_concurrent_requests_mint_one_link(session_factory):
    from app.db.models import PasswordResetToken, User
    from app.services import password_reset as pr

    S = session_factory
    uid = _account(S)
    a, b = S(), S()
    first = pr.issue_token(a, a.get(User, uid))
    assert first is not None                                       # A holds the lock
    result: dict = {}

    def second():
        result["raw"] = pr.issue_token(b, b.get(User, uid))
        b.commit()

    t = threading.Thread(target=second)
    t.start()
    assert _blocked(t), "the second request must wait for the account lock"
    time.sleep(0.1)
    a.commit()
    t.join(10)
    assert not t.is_alive()
    assert result["raw"] is None                                   # inside the cooldown
    a.close()
    b.close()

    s = S()
    rows = s.query(PasswordResetToken).filter_by(user_id=uid).all()
    assert len(rows) == 1 and rows[0].used_at is None              # one live link
    s.close()
