"""F-DB-03 -- the dispatcher's due-message scan needs an index.

`leadpilot.outreach.dispatch` runs every beat tick:
    WHERE status = 'scheduled' AND scheduled_at <= now ORDER BY scheduled_at
messages had indexes on lead_id / origin / sequence_id only, so every tick was a
sequential scan of the whole table, and the table only grows.

These tests are offline (SQLite). The real-Postgres proof (CONCURRENTLY inside
autocommit_block, round trip) is in the PR evidence, not in the hard gate.
"""

from __future__ import annotations

import importlib.util
import os

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m

INDEX = "ix_messages_status_scheduled_at"
MIGRATION = "0065_messages_dispatch_index.py"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        MIGRATION[:-3], os.path.join(ROOT, "alembic", "versions", MIGRATION))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_model_declares_the_index():
    declared = {i.name: [c.name for c in i.columns]
                for i in m.Message.__table__.indexes}
    assert declared.get(INDEX) == ["status", "scheduled_at"]


def test_the_migration_chains_after_the_current_head():
    module = _load()
    assert module.revision == "0065_messages_dispatch_index"
    assert module.down_revision == "0064_meeting_practice"


def test_upgrade_then_downgrade_round_trips_on_sqlite():
    module = _load()
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    sa.Table("messages", meta, sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("status", sa.String(20)),
             sa.Column("scheduled_at", sa.DateTime))
    meta.create_all(engine)
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
        names = {i["name"]: i["column_names"]
                 for i in sa.inspect(conn).get_indexes("messages")}
        assert names.get(INDEX) == ["status", "scheduled_at"]
        with Operations.context(ctx):
            module.downgrade()
        assert INDEX not in {i["name"] for i in sa.inspect(conn).get_indexes("messages")}


def test_upgrade_is_idempotent_on_sqlite():
    module = _load()
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    sa.Table("messages", meta, sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("status", sa.String(20)),
             sa.Column("scheduled_at", sa.DateTime))
    meta.create_all(engine)
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
            module.upgrade()
