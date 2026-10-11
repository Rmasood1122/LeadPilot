"""Migration 0083: billing rows' owner FK goes CASCADE -> RESTRICT (decision E1,
docs/features/gdpr-erasure.md), so deleting a users row can no longer take the
billing records that must be kept with it. Applied on top of the tables
migration 0040 creates; checked against the model; downgrade round-trips."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base
from tests.test_billing_migration import LATER_COLUMNS

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = ("billing_subscriptions", "billable_meetings")
_PREREQ = ["users", "products", "workspaces", "client_workspaces", "strategies",
           "lead_batches", "linkedin_accounts", "leads"]


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(_ROOT, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, *steps):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            for step in steps:
                step()


def _user_fk(inspector, table):
    (fk,) = [f for f in inspector.get_foreign_keys(table) if f["referred_table"] == "users"]
    return fk["name"], (fk.get("options") or {}).get("ondelete")


@pytest.fixture()
def engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])
    _run(engine, _load("0040_billing.py").upgrade)
    yield engine
    engine.dispose()


def test_the_revision_follows_0080():
    module = _load("0083_billing_retention.py")
    assert module.revision == "0083_billing_retention"
    assert module.down_revision == "0082_annual_billing"


def test_before_it_billing_cascaded_with_the_user(engine):
    inspector = sa.inspect(engine)
    for table in TABLES:
        assert _user_fk(inspector, table)[1] == "CASCADE"


def test_upgrade_makes_it_restrict_with_the_same_name(engine):
    _run(engine, _load("0083_billing_retention.py").upgrade)
    inspector = sa.inspect(engine)
    for table in TABLES:
        name, ondelete = _user_fk(inspector, table)
        assert name == f"fk_{table}_user_id_users"
        assert ondelete == "RESTRICT"


def test_the_model_matches_the_migration(engine, tmp_path):
    _run(engine, _load("0083_billing_retention.py").upgrade)
    model_engine = sa.create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(model_engine)
    try:
        for table in TABLES:
            assert _user_fk(sa.inspect(engine), table) == _user_fk(sa.inspect(model_engine), table)
            columns = {c["name"] for c in sa.inspect(engine).get_columns(table)}
            # Columns a LATER migration adds (0082_annual_billing) are not in
            # this fixture's 0040 schema; the same list test_billing_migration
            # uses, so a new column must be declared in one place.
            later = set(LATER_COLUMNS.get(table, {}))
            model_columns = {c["name"] for c in sa.inspect(model_engine).get_columns(table)}
            assert columns == model_columns - later
    finally:
        model_engine.dispose()


def test_downgrade_round_trips(engine):
    module = _load("0083_billing_retention.py")
    _run(engine, module.upgrade, module.downgrade)
    inspector = sa.inspect(engine)
    for table in TABLES:
        assert _user_fk(inspector, table)[1] == "CASCADE"


def test_rows_survive_the_upgrade(engine):
    import uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    uid, sid = uuid.uuid4().hex, uuid.uuid4().hex
    now = datetime(2026, 10, 11, tzinfo=timezone.utc).isoformat()
    with engine.begin() as c:
        c.execute(sa.text("INSERT INTO users (id, email, plan, theme_json, is_admin, "
                          "is_suspended, email_verified, identity_required, phone_verified, "
                          "created_at, updated_at) VALUES (:id, 'a@b.example', 'free', '{}', "
                          "0, 0, 1, 0, 0, :now, :now)"), {"id": uid, "now": now})
        c.execute(sa.text("INSERT INTO billing_subscriptions (id, user_id, billing_model, tier, "
                          "status, cancel_at_period_end, is_stub, created_at, updated_at) "
                          "VALUES (:id, :u, 'monthly', 'growth', 'active', 0, 0, :now, :now)"),
                  {"id": sid, "u": uid, "now": now})
    _run(engine, _load("0083_billing_retention.py").upgrade)
    with engine.connect() as c:
        assert c.execute(sa.text("SELECT count(*) FROM billing_subscriptions")).scalar() == 1
