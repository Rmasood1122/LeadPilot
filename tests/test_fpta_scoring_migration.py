"""Migration 0054 (Part 1, Feature 2) must add exactly the leads columns the model
declares -- same column-strip technique as tests/test_reply_intent_migration.py."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0054_fpta_scoring.py"
ADDED = ["fpta_fit", "fpta_problem", "fpta_timing", "fpta_access", "fpta_overall",
         "fpta_reasons_json", "fpta_method", "fpta_scored_at"]
# `workspaces` and `client_workspaces` are prerequisites because
# `strategies` gained a foreign key to the latter in migration 0063
# (Part 1 Feature 11). Without them the pre-migration `strategies`
# table references a table that does not exist, which SQLite refuses.
_PREREQ = ["users", "products", "workspaces", "client_workspaces", "strategies", "lead_batches", "linkedin_accounts", "leads"]


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
    leads = meta.tables["leads"]
    for index in list(leads.indexes):
        if any(col.name in ADDED for col in index.columns):
            leads.indexes.remove(index)
    for name in ADDED:
        leads._columns.remove(leads.c[name])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


def _columns(inspector):
    return {c["name"]: (str(c["type"]), bool(c["nullable"]))
            for c in inspector.get_columns("leads")}


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


def test_the_revision_follows_0053():
    module = _load(MIGRATION)
    assert module.revision == "0054_fpta_scoring"
    assert module.down_revision == "0053_reply_intent"


def test_columns_match_the_model(from_models, from_migration):
    assert _columns(from_migration) == _columns(from_models)


def test_every_new_column_is_nullable(from_migration):
    """A prospect sourced before this revision is 'not scored', which sorts
    last rather than reading as a zero."""
    columns = _columns(from_migration)
    assert all(columns[name][1] for name in ADDED)


def test_the_overall_index_exists(from_migration):
    names = {i["name"] for i in from_migration.get_indexes("leads")}
    assert "ix_leads_fpta_overall" in names


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    present = {c["name"] for c in sa.inspect(engine).get_columns("leads")}
    assert not set(ADDED) & present
    engine.dispose()
