"""Migration 0093 (F-DB-01: playbook_scores owner) on PostgreSQL.

What must hold on the production engine:
  * upgrade keeps every pre-0093 row (pooled, user_id NULL) -- nothing is
    deleted or attributed;
  * after upgrade, two accounts can each own a row for the same
    (pattern_key, variant), and one account cannot have two;
  * the nightly upsert (app/workers/learning_tasks._upsert_playbook_score,
    raw PostgreSQL SQL) writes per-account rows and updates them in place;
  * erasing an account removes its rows (ON DELETE CASCADE), not the pooled ones;
  * downgrade restores the pre-0093 table: per-account rows go, pooled rows stay.

Same scratch-database technique as test_migration_0090_email_network_pg.py.
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
from sqlalchemy.orm import Session

from tests.integration.conftest import TEST_DATABASE_URL

REPO = Path(__file__).resolve().parents[2]
BEFORE = "0092_agent_runs"
AFTER = "0093_playbook_scores_owner"


@pytest.fixture()
def scratch_url():
    base = make_url(TEST_DATABASE_URL)
    assert base.host in ("localhost", "127.0.0.1"), "scratch databases are local only"
    name = f"lp_mig0093_{uuid.uuid4().hex[:8]}"
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
              {"id": uid, "email": f"pb-{uid.hex[:8]}@test.io"})
    return uid


def _pooled_row(c, pattern_key: str, variant: str) -> None:
    c.execute(text("INSERT INTO playbook_scores (id, pattern_key, variant, score, "
                   "sample_size, is_reliable, created_at, updated_at) VALUES "
                   "(:id, :pk, :v, 0.2, 40, true, now(), now())"),
              {"id": uuid.uuid4(), "pk": pattern_key, "v": variant})


def _owned_row(c, user_id, pattern_key: str, variant: str) -> None:
    c.execute(text("INSERT INTO playbook_scores (id, user_id, pattern_key, variant, score, "
                   "sample_size, is_reliable, created_at, updated_at) VALUES "
                   "(:id, :u, :pk, :v, 0.2, 40, true, now(), now())"),
              {"id": uuid.uuid4(), "u": user_id, "pk": pattern_key, "v": variant})


def _score_data(user_id, reply_rate: float, raw_n: int) -> dict:
    return {"user_id": user_id, "pattern_key": "pk-shared", "variant": "A",
            "reply_rate": reply_rate, "booking_rate": 0.01, "raw_n": raw_n,
            "effective_n": float(raw_n), "half_life_days": 30, "oldest_outcome_ts": None,
            "is_reliable": True}


def test_upgrade_keeps_pooled_rows_and_scopes_uniqueness_per_account(scratch_url):
    _alembic(scratch_url, "upgrade", BEFORE)
    engine = create_engine(scratch_url)
    with engine.begin() as c:
        _pooled_row(c, "pk-shared", "A")
        _pooled_row(c, "pk-other", "A")

    _alembic(scratch_url, "upgrade", AFTER)
    insp = inspect(engine)
    cols = {col["name"]: col for col in insp.get_columns("playbook_scores")}
    assert cols["user_id"]["nullable"] is True
    uniques = {u["name"]: u["column_names"] for u in insp.get_unique_constraints("playbook_scores")}
    assert uniques == {"uq_playbook_scores_owner_pattern_variant":
                       ["user_id", "pattern_key", "variant"]}
    fks = insp.get_foreign_keys("playbook_scores")
    assert [(fk["referred_table"], fk["options"].get("ondelete")) for fk in fks] == [
        ("users", "CASCADE")]

    with engine.begin() as c:
        assert c.execute(text("SELECT count(*) FROM playbook_scores "
                              "WHERE user_id IS NULL")).scalar() == 2
        alice, bob = _user(c), _user(c)
        # Same (pattern_key, variant) as a pooled row and as each other.
        _owned_row(c, alice, "pk-shared", "A")
        _owned_row(c, bob, "pk-shared", "A")
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            _owned_row(c, alice, "pk-shared", "A")
    engine.dispose()


def test_nightly_upsert_writes_and_updates_per_account_rows(scratch_url):
    from app.workers.learning_tasks import _upsert_playbook_score

    _alembic(scratch_url, "upgrade", AFTER)
    engine = create_engine(scratch_url)
    with engine.begin() as c:
        alice, bob = _user(c), _user(c)
        _pooled_row(c, "pk-shared", "A")

    with Session(engine) as db:
        _upsert_playbook_score(db, _score_data(alice, 0.10, 10))
        _upsert_playbook_score(db, _score_data(bob, 0.90, 10))
        _upsert_playbook_score(db, _score_data(alice, 0.30, 20))   # next night

    with engine.connect() as c:
        rows = c.execute(text("SELECT user_id, reply_rate, sample_size, trend "
                              "FROM playbook_scores WHERE pattern_key = 'pk-shared'")).all()
    by_owner = {r.user_id: r for r in rows}
    assert set(by_owner) == {alice, bob, None}
    assert (by_owner[alice].reply_rate, by_owner[alice].sample_size,
            by_owner[alice].trend) == (0.30, 20, "rising")
    assert (by_owner[bob].reply_rate, by_owner[bob].sample_size) == (0.90, 10)
    assert by_owner[None].sample_size == 40     # the pooled row was not touched
    engine.dispose()


def test_deleting_an_account_removes_only_its_rows(scratch_url):
    _alembic(scratch_url, "upgrade", AFTER)
    engine = create_engine(scratch_url)
    with engine.begin() as c:
        alice, bob = _user(c), _user(c)
        _owned_row(c, alice, "pk-shared", "A")
        _owned_row(c, bob, "pk-shared", "A")
        _pooled_row(c, "pk-shared", "A")
    with engine.begin() as c:
        c.execute(text("DELETE FROM users WHERE id = :id"), {"id": alice})
        owners = sorted(str(r[0]) for r in c.execute(
            text("SELECT user_id FROM playbook_scores")).all())
    assert owners == sorted([str(bob), "None"])
    engine.dispose()


def test_downgrade_restores_the_pre_0093_table(scratch_url):
    _alembic(scratch_url, "upgrade", AFTER)
    engine = create_engine(scratch_url)
    with engine.begin() as c:
        alice, bob = _user(c), _user(c)
        _owned_row(c, alice, "pk-shared", "A")
        _owned_row(c, bob, "pk-shared", "A")
        _pooled_row(c, "pk-pooled", "A")

    _alembic(scratch_url, "downgrade", BEFORE)
    insp = inspect(engine)
    assert "user_id" not in {col["name"] for col in insp.get_columns("playbook_scores")}
    uniques = {u["name"]: u["column_names"] for u in insp.get_unique_constraints("playbook_scores")}
    assert uniques == {"pattern_variant": ["pattern_key", "variant"]}
    with engine.connect() as c:
        assert c.execute(text("SELECT pattern_key FROM playbook_scores")).scalars().all() == [
            "pk-pooled"]

    _alembic(scratch_url, "upgrade", AFTER)   # and forward again
    engine.dispose()
