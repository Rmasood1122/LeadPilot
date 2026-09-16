"""Migration 0045 (Feature A5) must add exactly the leads columns the model
declares (column-strip technique, tests/test_pipeline_features_migration.py)."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0045_conversion_probability.py"
ADDED = ["conversion_probability", "conversion_probability_at", "engagement_state",
         "kill_signal", "conversion_factors_json"]
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
    return {c["name"]: (str(c["type"]), bool(c["nullable"])) for c in inspector.get_columns("leads")}


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


def test_the_revision_follows_0044():
    module = _load(MIGRATION)
    assert module.revision == "0045_conversion_probability"
    assert module.down_revision == "0044_channel_suggestions"


def test_columns_match_the_model(from_models, from_migration):
    assert _columns(from_migration) == _columns(from_models)


def test_no_existing_lead_changes_behaviour(from_migration):
    """All nullable: engagement_state NULL reads as active."""
    columns = _columns(from_migration)
    assert all(columns[name][1] for name in ADDED)
    names = {i["name"] for i in from_migration.get_indexes("leads")}
    assert "ix_leads_engagement_state" in names


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
