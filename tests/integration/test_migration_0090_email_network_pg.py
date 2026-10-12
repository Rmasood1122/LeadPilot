"""Migration 0090 (email network) on PostgreSQL, the production engine.

The offline suite proves the SQLite path (tests/test_email_network_migration.py);
this proves the four tables, their UNIQUE constraints and FK actions on
PostgreSQL, and the downgrade. Same scratch-database technique as
test_migration_0089_voice_twin_pg.py.
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
BEFORE = "0089_voice_twin"
AFTER = "0090_email_network"
TABLES = {"email_network_imports", "email_contacts", "email_contact_matches",
          "email_network_messages"}


@pytest.fixture()
def scratch_url():
    base = make_url(TEST_DATABASE_URL)
    assert base.host in ("localhost", "127.0.0.1"), "scratch databases are local only"
    name = f"lp_mig0090_{uuid.uuid4().hex[:8]}"
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
              {"id": uid, "email": f"en-{uid.hex[:8]}@test.io"})
    return uid


def _product(c, user_id) -> uuid.UUID:
    pid = uuid.uuid4()
    c.execute(text("INSERT INTO products (id, user_id, name, description, type) VALUES "
                   "(:id, :u, 'P', 'd', 'skill')"), {"id": pid, "u": user_id})
    return pid


def _contact(c, user_id, email="ana@acme.com") -> uuid.UUID:
    cid = uuid.uuid4()
    c.execute(text("INSERT INTO email_contacts (id, user_id, email, domain) VALUES "
                   "(:id, :u, :e, 'acme.com')"), {"id": cid, "u": user_id, "e": email})
    return cid


def test_upgrade_on_postgres(scratch_url):
    _alembic(scratch_url, "upgrade", BEFORE)
    _alembic(scratch_url, "upgrade", AFTER)
    engine = create_engine(scratch_url)
    try:
        insp = inspect(engine)
        assert TABLES <= set(insp.get_table_names())
        uniques = {u["name"] for u in insp.get_unique_constraints("email_contacts")}
        assert "uq_email_contacts_user_id_email" in uniques
        fks = {f["name"]: f["options"].get("ondelete")
               for f in insp.get_foreign_keys("email_network_messages")}
        assert fks["fk_email_network_messages_lead_id_leads"] == "SET NULL"
        assert fks["fk_email_network_messages_contact_id_email_contacts"] == "CASCADE"
        with engine.begin() as c:
            a, b = _user(c), _user(c)
            ca = _contact(c, a)
            _contact(c, b)                                  # same address, other account
            pid = _product(c, a)
            c.execute(text("INSERT INTO email_contact_matches (id, user_id, contact_id, "
                           "product_id, score, segment, reasons_json, analyzed_at) VALUES "
                           "(:id, :u, :c, :p, 50, 's', '[]', now())"),
                      {"id": uuid.uuid4(), "u": a, "c": ca, "p": pid})
            c.execute(text("INSERT INTO email_network_messages (id, user_id, contact_id, "
                           "product_id, subject, body) VALUES (:id, :u, :c, :p, 's', 'b')"),
                      {"id": uuid.uuid4(), "u": a, "c": ca, "p": pid})
            c.execute(text("INSERT INTO email_network_imports (id, user_id, kind, "
                           "excluded_json) VALUES (:id, :u, 'mbox', '{\"automated\": 3}')"),
                      {"id": uuid.uuid4(), "u": a})
        with pytest.raises(IntegrityError):                 # one row per address per account
            with engine.begin() as c:
                _contact(c, a)
        # one ACTIVE Gmail scan per account (partial UNIQUE index); finished ones are free
        with engine.begin() as c:
            c.execute(text("INSERT INTO email_network_imports (id, user_id, kind, status) "
                           "VALUES (:id, :u, 'gmail_scan', 'running')"),
                      {"id": uuid.uuid4(), "u": b})
            c.execute(text("INSERT INTO email_network_imports (id, user_id, kind, status) "
                           "VALUES (:id, :u, 'gmail_scan', 'done')"),
                      {"id": uuid.uuid4(), "u": b})
        with pytest.raises(IntegrityError):
            with engine.begin() as c:
                c.execute(text("INSERT INTO email_network_imports (id, user_id, kind, status) "
                               "VALUES (:id, :u, 'gmail_scan', 'queued')"),
                          {"id": uuid.uuid4(), "u": b})
        with engine.begin() as c:
            row = c.execute(text("SELECT two_way, sent_to_count, status FROM email_contacts "
                                 "JOIN email_network_imports USING (user_id) "
                                 "WHERE email_contacts.user_id = :u"), {"u": a}).one()
            assert row == (False, 0, "done")                 # server defaults
            c.execute(text("DELETE FROM users WHERE id = :u"), {"u": a})
            for table in TABLES:
                left = c.execute(text(f"SELECT count(*) FROM {table} WHERE user_id = :u"),
                                 {"u": a}).scalar()
                assert left == 0, table
            assert c.execute(text("SELECT count(*) FROM email_contacts")).scalar() == 1
    finally:
        engine.dispose()


def test_downgrade_on_postgres(scratch_url):
    _alembic(scratch_url, "upgrade", AFTER)
    _alembic(scratch_url, "downgrade", BEFORE)
    engine = create_engine(scratch_url)
    try:
        assert not TABLES & set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
