"""Migration 0070 creates exactly the table the model declares (create-only;
same technique as tests/test_consent_migration.py)."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0070_linkedin_network_messages.py"
TABLES = ["linkedin_network_messages"]
_PREREQ = ["users", "products", "linkedin_connections"]


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


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: list(i["column_names"]) for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 f["options"].get("ondelete"))
                for f in inspector.get_foreign_keys(table)},
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


def test_the_revision_follows_0069():
    module = _load(MIGRATION)
    assert module.revision == "0070_linkedin_network_messages"
    assert module.down_revision == "0069_user_full_name"


@pytest.mark.parametrize("table", TABLES)
def test_table_matches_the_model(from_models, from_migration, table):
    assert _describe(from_migration, table) == _describe(from_models, table)


def test_every_row_goes_when_the_account_goes(from_migration):
    """Erasure of an account must erase its network: user_id is CASCADE on all."""
    for table in TABLES:
        rules = {tuple(f["constrained_columns"]): f["options"].get("ondelete")
                 for f in from_migration.get_foreign_keys(table)}
        assert rules[("user_id",)] == "CASCADE"


def test_one_message_per_connection(from_migration):
    uniques = {tuple(sorted(u["column_names"]))
               for u in from_migration.get_unique_constraints("linkedin_network_messages")}
    assert ("connection_id", "user_id") in uniques


def test_connection_fk_cascades(from_migration):
    rules = {f["constrained_columns"][0]: f["options"].get("ondelete")
             for f in from_migration.get_foreign_keys("linkedin_network_messages")}
    assert rules["connection_id"] == "CASCADE"


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    assert not set(TABLES) & set(sa.inspect(engine).get_table_names())
    engine.dispose()
