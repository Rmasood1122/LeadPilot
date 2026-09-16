"""Migration 0055 (Part 1, Feature 3) must add exactly the sequence_enrollments
columns the model declares -- same column-strip technique as
tests/test_fpta_scoring_migration.py."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0055_sequence_completion.py"
ADDED = ["planned_steps", "steps_sent", "completed_at", "stopped_at", "stop_category"]
#: steps_sent is the one NOT NULL column: it has a server default of 0, which
#: is a safe backfill (an old enrollment reports 0 sent, which the metric reads
#: as "unknown", never as a failure).
NULLABLE = [name for name in ADDED if name != "steps_sent"]
_PREREQ = ["users", "products", "strategies", "lead_batches", "linkedin_accounts", "leads",
           "sequences", "sequence_enrollments"]


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
    table = meta.tables["sequence_enrollments"]
    for index in list(table.indexes):
        if any(col.name in ADDED for col in index.columns):
            table.indexes.remove(index)
    for name in ADDED:
        table._columns.remove(table.c[name])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


def _columns(inspector):
    return {c["name"]: (str(c["type"]), bool(c["nullable"]))
            for c in inspector.get_columns("sequence_enrollments")}


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


def test_the_revision_follows_0054():
    module = _load(MIGRATION)
    assert module.revision == "0055_sequence_completion"
    assert module.down_revision == "0054_fpta_scoring"


def test_columns_match_the_model(from_models, from_migration):
    assert _columns(from_migration) == _columns(from_models)


def test_the_history_carrying_columns_are_nullable(from_migration):
    """An enrollment from before this revision has no planned_steps snapshot,
    which the metric reads as 'unknown' rather than as a failed completion."""
    columns = _columns(from_migration)
    assert all(columns[name][1] for name in NULLABLE)


def test_steps_sent_backfills_to_zero_rather_than_null(from_migration):
    """The one NOT NULL addition: a counter with no value is 0, and 0 sent of
    a NULL plan is still 'unknown', so nothing is miscounted."""
    columns = _columns(from_migration)
    assert columns["steps_sent"][1] is False


def test_the_stop_category_index_exists(from_migration):
    names = {i["name"] for i in from_migration.get_indexes("sequence_enrollments")}
    assert "ix_sequence_enrollments_stop_category" in names


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    present = {c["name"] for c in sa.inspect(engine).get_columns("sequence_enrollments")}
    assert not set(ADDED) & present
    engine.dispose()
