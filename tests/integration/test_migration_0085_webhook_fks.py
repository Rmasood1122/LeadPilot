"""PD-2: migration 0085 adds the webhook foreign keys 0011 never created.

On PostgreSQL (the production engine) webhook_targets.user_id and
webhook_deliveries.target_id had no foreign key, so removing a user left its
targets and their delivery rows (lead-data payloads) owned by nobody. SQLite
never showed it: the offline suite builds tables from the model, which has
both constraints.

Each test runs alembic in a subprocess against its own throwaway database on
the integration server (same technique as test_migration_0071_webhook_schema).
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

from tests.integration.conftest import TEST_DATABASE_URL

REPO = Path(__file__).resolve().parents[2]
BEFORE = "0084_password_reset"
AFTER = "0085_webhook_foreign_keys"
NAMES = {"fk_webhook_targets_user_id_users",
         "fk_webhook_deliveries_target_id_webhook_targets"}


@pytest.fixture()
def scratch_url():
    base = make_url(TEST_DATABASE_URL)
    assert base.host in ("localhost", "127.0.0.1"), "scratch databases are local only"
    name = f"lp_mig0082_{uuid.uuid4().hex[:8]}"
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


def _fks(engine, table: str) -> dict[str, tuple]:
    return {f["name"]: (tuple(f["constrained_columns"]), f["referred_table"],
                        f["options"].get("ondelete"))
            for f in inspect(engine).get_foreign_keys(table)}


def _seed(engine) -> dict[str, uuid.UUID]:
    ids = {k: uuid.uuid4() for k in ("user", "t_live", "d_live", "t_orphan", "d_of_orphan",
                                     "d_orphan", "ghost")}
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id, email, plan, theme_json, is_admin, is_suspended, "
                       "email_verified) VALUES (:id, 'pd2@test.io', 'FREE', '{}', false, false, "
                       "true)"), {"id": ids["user"]})
        for tid, uid in ((ids["t_live"], ids["user"]), (ids["t_orphan"], ids["ghost"])):
            c.execute(text("INSERT INTO webhook_targets (id, user_id, url, event_types) "
                           "VALUES (:id, :uid, 'https://hooks.example.com/x', '[]')"),
                      {"id": tid, "uid": uid})
        for did, tid in ((ids["d_live"], ids["t_live"]), (ids["d_of_orphan"], ids["t_orphan"]),
                         (ids["d_orphan"], uuid.uuid4())):
            c.execute(text("INSERT INTO webhook_deliveries (id, target_id, event_type, "
                           "payload_json, status, attempts) VALUES (:id, :tid, "
                           "'meeting_booked', '{\"a\": 1}', 'failed', 1)"),
                      {"id": did, "tid": tid})
    return ids


def test_before_0082_postgres_has_no_webhook_fks(scratch_url):
    """The defect itself, on the real engine."""
    _alembic(scratch_url, "upgrade", BEFORE)
    engine = create_engine(scratch_url)
    try:
        assert _fks(engine, "webhook_targets") == {}
        assert _fks(engine, "webhook_deliveries") == {}
    finally:
        engine.dispose()


def test_upgrade_cleans_orphans_and_adds_cascading_fks(scratch_url):
    _alembic(scratch_url, "upgrade", BEFORE)
    engine = create_engine(scratch_url)
    try:
        ids = _seed(engine)
        _alembic(scratch_url, "upgrade", AFTER)

        assert _fks(engine, "webhook_targets") == {
            "fk_webhook_targets_user_id_users": (("user_id",), "users", "CASCADE")}
        assert _fks(engine, "webhook_deliveries") == {
            "fk_webhook_deliveries_target_id_webhook_targets":
                (("target_id",), "webhook_targets", "CASCADE")}
        with engine.connect() as c:
            targets = set(c.execute(text("SELECT id FROM webhook_targets")).scalars())
            deliveries = set(c.execute(text("SELECT id FROM webhook_deliveries")).scalars())
        assert targets == {ids["t_live"]}
        assert deliveries == {ids["d_live"]}

        # The point of PD-2: removing the user now removes its webhook rows.
        with engine.begin() as c:
            c.execute(text("DELETE FROM users WHERE id = :id"), {"id": ids["user"]})
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM webhook_targets")).scalar() == 0
            assert c.execute(text("SELECT count(*) FROM webhook_deliveries")).scalar() == 0
    finally:
        engine.dispose()


def test_orphans_can_no_longer_be_created(scratch_url):
    _alembic(scratch_url, "upgrade", AFTER)
    engine = create_engine(scratch_url)
    try:
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            with engine.begin() as c:
                c.execute(text("INSERT INTO webhook_targets (id, user_id, url, event_types) "
                               "VALUES (:id, :uid, 'https://h.example.com', '[]')"),
                          {"id": uuid.uuid4(), "uid": uuid.uuid4()})
    finally:
        engine.dispose()


def test_downgrade_drops_only_the_constraints(scratch_url):
    _alembic(scratch_url, "upgrade", BEFORE)
    engine = create_engine(scratch_url)
    try:
        ids = _seed(engine)
        _alembic(scratch_url, "upgrade", AFTER)
        _alembic(scratch_url, "downgrade", BEFORE)
        assert _fks(engine, "webhook_targets") == {}
        assert _fks(engine, "webhook_deliveries") == {}
        with engine.connect() as c:
            assert set(c.execute(text("SELECT id FROM webhook_targets")).scalars()) == {
                ids["t_live"]}
        _alembic(scratch_url, "upgrade", "head")  # and forward again
        assert set(_fks(engine, "webhook_targets")) | set(
            _fks(engine, "webhook_deliveries")) == NAMES
    finally:
        engine.dispose()
