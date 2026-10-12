"""Migration 0089 (voice twin) on PostgreSQL, the production engine.

The offline suite proves the SQLite path (tests/test_voice_twin_migration.py);
this proves the batch ALTER of `calls` (lead_id -> nullable, four columns) and
the two new tables on PostgreSQL, the UNIQUE inbound-number constraint, and
the documented lossy downgrade. Same scratch-database technique as
test_migration_0085_webhook_fks.py.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from tests.integration.conftest import TEST_DATABASE_URL

REPO = Path(__file__).resolve().parents[2]
BEFORE = "0088_local_business"
AFTER = "0089_voice_twin"


@pytest.fixture()
def scratch_url():
    base = make_url(TEST_DATABASE_URL)
    assert base.host in ("localhost", "127.0.0.1"), "scratch databases are local only"
    name = f"lp_mig0089_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _alembic(url: str, *args: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=str(REPO),
        env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, f"alembic {' '.join(args)} failed:\n{proc.stdout}\n{proc.stderr}"


def _user(c) -> uuid.UUID:
    uid = uuid.uuid4()
    c.execute(text("INSERT INTO users (id, email, plan, theme_json, is_admin, is_suspended, "
                   "email_verified) VALUES (:id, :email, 'FREE', '{}', false, false, true)"),
              {"id": uid, "email": f"vt-{uid.hex[:8]}@test.io"})
    return uid


def test_upgrade_on_postgres(scratch_url):
    _alembic(scratch_url, "upgrade", BEFORE)
    _alembic(scratch_url, "upgrade", AFTER)
    engine = create_engine(scratch_url)
    try:
        insp = inspect(engine)
        calls = {c["name"]: c for c in insp.get_columns("calls")}
        assert calls["lead_id"]["nullable"] is True
        assert {"direction", "voice_clone_used", "from_number", "control_url"} <= set(calls)
        assert {"voice_clones", "voice_twin_settings",
                "voice_clone_deletions"} <= set(insp.get_table_names())
        uniques = {u["name"] for u in insp.get_unique_constraints("voice_twin_settings")}
        assert "uq_voice_twin_settings_inbound_phone_number_id" in uniques
        with engine.begin() as c:
            a, b = _user(c), _user(c)
            c.execute(text("INSERT INTO calls (id, lead_id, user_id, provider, to_number, "
                           "status, direction, from_number) VALUES (:id, NULL, :u, 'vapi', '', "
                           "'ringing', 'inbound', '+15550107777')"), {"id": uuid.uuid4(), "u": a})
            c.execute(text("INSERT INTO voice_twin_settings (id, user_id, "
                           "inbound_phone_number_id) VALUES (:id, :u, 'pn-1')"),
                      {"id": uuid.uuid4(), "u": a})
        with pytest.raises(IntegrityError):         # one number answers for one account
            with engine.begin() as c:
                c.execute(text("INSERT INTO voice_twin_settings (id, user_id, "
                               "inbound_phone_number_id) VALUES (:id, :u, 'pn-1')"),
                          {"id": uuid.uuid4(), "u": b})
        with engine.begin() as c:                    # existing default for old rows
            assert c.execute(text("SELECT direction FROM calls")).scalar() == "inbound"
            # erasing the user cascades the voice-twin rows
            c.execute(text("DELETE FROM users WHERE id = :u"), {"u": a})
            assert c.execute(text("SELECT count(*) FROM voice_twin_settings")).scalar() == 0
    finally:
        engine.dispose()


def test_downgrade_on_postgres_drops_lead_less_calls(scratch_url):
    _alembic(scratch_url, "upgrade", AFTER)
    engine = create_engine(scratch_url)
    try:
        with engine.begin() as c:
            u = _user(c)
            c.execute(text("INSERT INTO calls (id, lead_id, user_id, provider, to_number, "
                           "status, direction) VALUES (:id, NULL, :u, 'vapi', '', 'ended', "
                           "'inbound')"), {"id": uuid.uuid4(), "u": u})
        _alembic(scratch_url, "downgrade", BEFORE)
        insp = inspect(engine)
        calls = {c["name"]: c for c in insp.get_columns("calls")}
        assert calls["lead_id"]["nullable"] is False
        assert "direction" not in calls and "voice_clones" not in insp.get_table_names()
        assert "voice_clone_deletions" not in insp.get_table_names()
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM calls")).scalar() == 0
    finally:
        engine.dispose()
