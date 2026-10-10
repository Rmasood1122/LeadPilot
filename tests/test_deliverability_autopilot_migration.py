"""Migration 0075 (F03 Deliverability Autopilot): one nullable column on
mailbox_health, added without touching existing rows, and removed on downgrade."""

from __future__ import annotations

import importlib.util
import os

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(ROOT, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, *steps):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            for step in steps:
                step()


def _engine_at_0056(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'f03.db'}")
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    meta.create_all(engine, tables=[meta.tables["users"]])
    _run(engine, _load("0056_mailbox_health.py").upgrade)
    return engine


def test_the_revision_follows_0074():
    module = _load("0075_deliverability_autopilot.py")
    assert module.revision == "0075_deliverability_autopilot"
    assert module.down_revision == "0074_signal_radar"


def test_upgrade_adds_the_nullable_column_the_model_declares(tmp_path):
    engine = _engine_at_0056(tmp_path)
    _run(engine, _load("0075_deliverability_autopilot.py").upgrade)
    columns = {c["name"]: c for c in sa.inspect(engine).get_columns("mailbox_health")}
    assert "complaint_source" in columns
    assert columns["complaint_source"]["nullable"] is True
    model = m.MailboxHealth.__table__.c.complaint_source
    assert model.nullable is True and model.type.length == 16
    assert str(columns["complaint_source"]["type"]) == "VARCHAR(16)"
    engine.dispose()


def test_existing_rows_keep_null_which_reads_as_proxy(tmp_path):
    engine = _engine_at_0056(tmp_path)
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO mailbox_health (id, user_id, mailbox_ref, channel, state, "
            "sends_today, sends_7d, created_at, updated_at) VALUES "
            "('r1', 'u1', 'mb1', 'email', 'healthy', 0, 0, CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP)"))
    _run(engine, _load("0075_deliverability_autopilot.py").upgrade)
    with engine.begin() as connection:
        value = connection.execute(sa.text(
            "SELECT complaint_source FROM mailbox_health WHERE id = 'r1'")).scalar_one()
    assert value is None
    engine.dispose()


def test_downgrade_round_trips(tmp_path):
    engine = _engine_at_0056(tmp_path)
    module = _load("0075_deliverability_autopilot.py")
    _run(engine, module.upgrade, module.downgrade)
    columns = {c["name"] for c in sa.inspect(engine).get_columns("mailbox_health")}
    assert "complaint_source" not in columns
    assert "complaint_rate" in columns
    engine.dispose()
