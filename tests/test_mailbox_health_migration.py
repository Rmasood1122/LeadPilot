"""Migration 0056 (Part 1, Feature 4) must create exactly the table the model
declares (create-only; tests/test_compliance_rules_migration.py technique)."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0056_mailbox_health.py"
TABLE = "mailbox_health"
_PREREQ = ["users"]


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
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


# Columns later migrations add to this table. 0056 is create-only, so comparing
# its table with today's model would report each of them as a column 0056
# forgot. Naming them keeps the test meaningful -- it still fails if 0056
# itself changes -- and makes the dependency visible (same technique as
# tests/test_meeting_prep_migration.py).
#
#   0075_deliverability_autopilot (F03): complaint_source.
_ADDED_LATER = {"complaint_source"}


def _without_later_columns(described: dict) -> dict:
    """The model's description of the table as it stood after 0056."""
    return {
        **described,
        "columns": {name: value for name, value in described["columns"].items()
                    if name not in _ADDED_LATER},
        "indexes": {name: cols for name, cols in described["indexes"].items()
                    if not set(cols) & _ADDED_LATER},
    }


def _describe(inspector):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(TABLE)},
        "indexes": {i["name"]: list(i["column_names"]) for i in inspector.get_indexes(TABLE)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(TABLE)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"])
                for f in inspector.get_foreign_keys(TABLE)},
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


def test_the_revision_follows_0055():
    module = _load(MIGRATION)
    assert module.revision == "0056_mailbox_health"
    assert module.down_revision == "0055_sequence_completion"


def test_one_row_per_mailbox_is_enforced_by_the_schema(from_migration):
    """Two rows for one mailbox would mean the send gate could read either."""
    uniques = {u["name"]: sorted(u["column_names"])
               for u in from_migration.get_unique_constraints(TABLE)}
    assert uniques["mailbox_health_ref"] == ["mailbox_ref", "user_id"]


def test_state_defaults_to_healthy_so_a_new_row_never_blocks_sending(from_migration):
    columns = {c["name"]: c for c in from_migration.get_columns(TABLE)}
    assert "healthy" in str(columns["state"]["default"])


def test_table_matches_the_model(from_models, from_migration):
    assert _describe(from_migration) == _without_later_columns(_describe(from_models))


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    assert TABLE not in sa.inspect(engine).get_table_names()
    engine.dispose()
