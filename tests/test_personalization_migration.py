"""Migration 0025 adds exactly the columns the models declare.

0025 only ALTERs (leads, users, messages), so each prerequisite is built from a
metadata COPY without the added columns -- see the note in
tests/test_ai_intelligence_migration.py for why the shared metadata is never
mutated.
"""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

ADDED = {
    "leads": ["linkedin_url", "linkedin_posts_json", "linkedin_posts_fetched_at",
              "company_news_json", "company_news_fetched_at", "loom_video_json"],
    "users": ["style_profile_json", "style_samples_json", "style_profile_updated_at"],
    "messages": ["personalization_json"],
}
# linkedin_accounts: see the note in tests/test_ai_intelligence_migration.py
# (batch-mode downgrade reflects every table leads/messages reference).
_PREREQ = ["users", "products", "strategies", "lead_batches", "linkedin_accounts", "leads",
           "whatsapp_templates", "sequences", "messages"]


def _load(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(root, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_prereqs(engine):
    # EVERY table is copied so every foreign key in the copy resolves (leads
    # and messages reference linkedin_accounts since 0026); only _PREREQ is
    # created.
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    for table_name, cols in ADDED.items():
        table = meta.tables[table_name]
        for name in cols:
            table._columns.remove(table.c[name])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


def _columns(inspector, table):
    return {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
            for c in inspector.get_columns(table)}


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
            _load("0025_personalization.py").upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_prerequisites_lack_the_columns(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'pre.db'}")
    _build_prereqs(engine)
    assert "linkedin_url" not in {c["name"] for c in sa.inspect(engine).get_columns("leads")}
    engine.dispose()


@pytest.mark.parametrize("table", sorted(ADDED))
def test_columns_match(table, from_models, from_migration):
    assert _columns(from_migration, table) == _columns(from_models, table)


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load("0025_personalization.py")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    for table, cols in ADDED.items():
        present = {c["name"] for c in inspector.get_columns(table)}
        assert not set(cols) & present, table
    engine.dispose()
