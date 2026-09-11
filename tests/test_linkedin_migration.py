"""Migration 0026 must produce exactly the schema the models declare.

Creates linkedin_accounts + linkedin_suppressions, and adds columns (two of
them foreign keys, in batch mode) to leads, sequence_steps and messages. The
prerequisites are built from a metadata COPY without those columns -- see
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

NEW_TABLES = ["linkedin_accounts", "linkedin_suppressions"]
ADDED = {
    "leads": ["linkedin_provider_id", "linkedin_is_premium", "linkedin_connection_status",
              "linkedin_invited_at", "linkedin_connected_at", "linkedin_account_id",
              "linkedin_chat_id"],
    "sequence_steps": ["linkedin_action"],
    "messages": ["linkedin_action", "linkedin_account_id"],
}
_PREREQ = ["users", "products", "strategies", "lead_batches", "leads",
           "whatsapp_templates", "sequences", "sequence_steps", "messages"]


def _load(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(root, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_prereqs(engine):
    """Copy EVERY table (so every foreign key in the copy resolves), trim the
    columns 0026 adds -- with their FK constraints and FK objects -- and
    create only the prerequisite subset. 0026's own tables must not exist
    before it runs."""
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    for table_name, cols in ADDED.items():
        table = meta.tables[table_name]
        for index in list(table.indexes):
            if any(c.name in cols for c in index.columns):
                table.indexes.discard(index)
        for constraint in list(table.constraints):
            if isinstance(constraint, sa.ForeignKeyConstraint) and any(
                    c in cols for c in constraint.column_keys):
                table.constraints.discard(constraint)
        for fk in list(table.foreign_keys):
            if fk.parent.name in cols:
                table.foreign_keys.discard(fk)
        for name in cols:
            table._columns.remove(table.c[name])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: {"columns": list(i["column_names"]), "unique": bool(i["unique"])}
                    for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 tuple(f["referred_columns"])) for f in inspector.get_foreign_keys(table)},
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
            _load("0026_linkedin_channel.py").upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_prerequisites_lack_the_columns(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'pre.db'}")
    _build_prereqs(engine)
    assert "linkedin_account_id" not in {
        c["name"] for c in sa.inspect(engine).get_columns("leads")}
    engine.dispose()


@pytest.mark.parametrize("table", NEW_TABLES)
def test_new_tables_match(table, from_models, from_migration):
    assert _describe(from_migration, table) == _describe(from_models, table)


@pytest.mark.parametrize("table", sorted(ADDED))
def test_altered_columns_and_fks_match(table, from_models, from_migration):
    a, b = _describe(from_migration, table), _describe(from_models, table)
    assert a["columns"] == b["columns"]
    assert a["fks"] == b["fks"]


def test_leads_provider_index(from_models, from_migration):
    assert (_describe(from_migration, "leads")["indexes"]["ix_leads_linkedin_provider_id"]
            == _describe(from_models, "leads")["indexes"]["ix_leads_linkedin_provider_id"])


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load("0026_linkedin_channel.py")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    assert not set(NEW_TABLES) & set(inspector.get_table_names())
    assert "linkedin_account_id" not in {c["name"] for c in inspector.get_columns("leads")}
    engine.dispose()
