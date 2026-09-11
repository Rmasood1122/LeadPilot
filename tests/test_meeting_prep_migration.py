"""Migration 0023 must produce exactly the schema the models declare.

Same reasoning and technique as tests/test_engagement_migrations.py: the suite
builds its database with create_all(), production by running migrations, so
the two descriptions of the schema are only ever compared here.

integration_tokens IS THE INTERESTING CASE. 0023 relaxes its user_id to
NULL-able (the system credential scope). The prerequisite table is therefore
built with the column NOT NULL -- as 0008/0009 left it -- so the test would
fail if upgrade() forgot the ALTER, instead of comparing a table to itself.
"""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401  (registers tables)
from app.db.base import Base

NEW_TABLES = ["system_settings", "deals", "meeting_prep_briefs", "meeting_outcomes"]

_PREREQ_TABLES = [
    "users", "products", "strategies", "lead_batches", "leads",
    "calendar_booking_pages", "calendar_bookings", "meetings",
    "integration_tokens",
]


def _load(name: str):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "alembic", "versions", name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _describe(inspector, table: str) -> dict:
    return {
        "columns": {
            c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
            for c in inspector.get_columns(table)
        },
        "indexes": {
            i["name"]: {"columns": list(i["column_names"]), "unique": bool(i["unique"])}
            for i in inspector.get_indexes(table)
        },
        "uniques": {
            u["name"]: sorted(u["column_names"])
            for u in inspector.get_unique_constraints(table)
        },
        "fks": {
            (tuple(f["constrained_columns"]), f["referred_table"],
             tuple(f["referred_columns"]))
            for f in inspector.get_foreign_keys(table)
        },
    }


def _build_prereqs(engine) -> None:
    """Prerequisites as they stood BEFORE 0023 (integration_tokens.user_id
    NOT NULL). The metadata is module-level shared state, so it is restored
    whatever happens."""
    column = Base.metadata.tables["integration_tokens"].c.user_id
    column.nullable = False
    try:
        Base.metadata.create_all(
            engine, tables=[Base.metadata.tables[t] for t in _PREREQ_TABLES]
        )
    finally:
        column.nullable = True


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
            _load("0023_meeting_prep.py").upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_prerequisite_really_starts_not_null(tmp_path):
    """Guards the fixture: if this stopped holding, the ALTER test below
    would pass vacuously."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'pre.db'}")
    _build_prereqs(engine)
    cols = {c["name"]: c for c in sa.inspect(engine).get_columns("integration_tokens")}
    assert cols["user_id"]["nullable"] is False
    engine.dispose()


def test_every_table_is_created(from_migration):
    missing = set(NEW_TABLES) - set(from_migration.get_table_names())
    assert not missing, f"0023 did not create: {sorted(missing)}"


@pytest.mark.parametrize("table", NEW_TABLES)
def test_columns_match(table, from_models, from_migration):
    assert (_describe(from_migration, table)["columns"]
            == _describe(from_models, table)["columns"])


@pytest.mark.parametrize("table", NEW_TABLES)
def test_indexes_match(table, from_models, from_migration):
    assert (_describe(from_migration, table)["indexes"]
            == _describe(from_models, table)["indexes"])


@pytest.mark.parametrize("table", NEW_TABLES)
def test_unique_constraints_match(table, from_models, from_migration):
    """meeting_prep_brief_source_ref is what stops a Calendly retry from
    producing a second brief and a second set of reminders."""
    assert (_describe(from_migration, table)["uniques"]
            == _describe(from_models, table)["uniques"])


@pytest.mark.parametrize("table", NEW_TABLES)
def test_foreign_keys_match(table, from_models, from_migration):
    assert (_describe(from_migration, table)["fks"]
            == _describe(from_models, table)["fks"])


def test_integration_tokens_user_id_becomes_nullable(from_migration, from_models):
    after = {c["name"]: c for c in from_migration.get_columns("integration_tokens")}
    assert after["user_id"]["nullable"] is True
    assert (_describe(from_migration, "integration_tokens")["columns"]
            == _describe(from_models, "integration_tokens")["columns"])


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'roundtrip.db'}")
    _build_prereqs(engine)
    module = _load("0023_meeting_prep.py")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    assert not set(NEW_TABLES) & set(inspector.get_table_names())
    cols = {c["name"]: c for c in inspector.get_columns("integration_tokens")}
    assert cols["user_id"]["nullable"] is False
    engine.dispose()
