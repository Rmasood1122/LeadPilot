"""Migration 0049 (Feature 3) must add exactly the meetings columns and indexes
the model declares. Same technique as tests/test_reengagement_migration.py."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0049_meeting_recording.py"
ADDED = ["recording_bot_id", "transcript_status", "transcript_deadline_at", "summary_source"]


def _load(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(root, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_prereqs(engine):
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    meetings = meta.tables["meetings"]
    for index in list(meetings.indexes):
        if any(c.name in ADDED for c in index.columns):
            meetings.indexes.discard(index)
    for name in ADDED:
        meetings._columns.remove(meetings.c[name])
    needed, changed = {"meetings"}, True
    while changed:
        changed = False
        for name in list(needed):
            for fk in meta.tables[name].foreign_keys:
                if fk.column.table.name not in needed:
                    needed.add(fk.column.table.name)
                    changed = True
    meta.create_all(engine, tables=[t for t in meta.sorted_tables if t.name in needed])


def _describe(inspector):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns("meetings")},
        "indexes": {i["name"]: {"columns": list(i["column_names"]), "unique": bool(i["unique"])}
                    for i in inspector.get_indexes("meetings")},
    }


@pytest.fixture()
def from_models(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    yield sa.inspect(engine)
    engine.dispose()


@pytest.fixture()
def from_migration(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _build_prereqs(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_the_revision_follows_0048():
    module = _load(MIGRATION)
    assert module.revision == "0049_meeting_recording"
    assert module.down_revision == "0048_reengagement"


def test_meetings_matches_the_model(from_models, from_migration):
    assert _describe(from_migration) == _describe(from_models)


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    columns = {c["name"] for c in sa.inspect(engine).get_columns("meetings")}
    assert not columns & set(ADDED)
    engine.dispose()
