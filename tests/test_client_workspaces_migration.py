"""Migration 0063 (Part 1, Feature 11) must create exactly the tables the models
declare, and add exactly the strategies column."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0063_client_workspaces.py"
TABLE = "client_workspaces"
SECOND = "client_sending_domains"
_PREREQ = ["users", "workspaces", "products", "strategies"]


def _load(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(root, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_prereqs(engine):
    """The pre-migration schema: no client tables, and `strategies` without its
    client_workspace_id column or the foreign key that references it."""
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    strategies = meta.tables["strategies"]
    for index in list(strategies.indexes):
        if any(col.name == "client_workspace_id" for col in index.columns):
            strategies.indexes.remove(index)
    for fk in list(strategies.foreign_keys):
        if fk.parent.name == "client_workspace_id":
            strategies.foreign_keys.discard(fk)
    for constraint in list(strategies.constraints):
        if any(col.name == "client_workspace_id"
               for col in getattr(constraint, "columns", [])):
            strategies.constraints.discard(constraint)
    strategies._columns.remove(strategies.c["client_workspace_id"])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


def _describe(inspector, table=TABLE):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: list(i["column_names"])
                    for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"])
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


def test_the_revision_follows_0062():
    module = _load(MIGRATION)
    assert module.revision == "0063_client_workspaces"
    assert module.down_revision == "0062_data_provenance"


def test_table_matches_the_model(from_models, from_migration):
    assert _describe(from_migration) == _describe(from_models)


def test_the_domain_pool_table_matches_the_model(from_models, from_migration):
    assert _describe(from_migration, SECOND) == _describe(from_models, SECOND)


def test_a_campaign_can_be_filed_under_a_client(from_migration):
    columns = {c["name"]: c for c in from_migration.get_columns("strategies")}
    assert "client_workspace_id" in columns
    # Nullable: every existing campaign is the agency's own work, not a client
    # that does not exist.
    assert columns["client_workspace_id"]["nullable"] is True


def test_deleting_a_client_does_not_delete_its_campaigns(from_migration):
    """SET NULL: losing a client must not erase the outreach done for them."""
    rules = {tuple(f["constrained_columns"]): f["options"].get("ondelete")
             for f in from_migration.get_foreign_keys("strategies")}
    assert rules[("client_workspace_id",)] == "SET NULL"


def test_one_domain_per_client_is_enforced_by_the_schema(from_migration):
    uniques = {u["name"]: sorted(u["column_names"])
               for u in from_migration.get_unique_constraints(SECOND)}
    assert uniques["client_sending_domain_once"] == ["client_workspace_id", "domain"]


def test_one_slug_per_agency(from_migration):
    uniques = {u["name"]: sorted(u["column_names"])
               for u in from_migration.get_unique_constraints(TABLE)}
    assert uniques["client_workspace_slug"] == ["slug", "workspace_id"]


def test_a_new_client_starts_active(from_migration):
    columns = {c["name"]: c for c in from_migration.get_columns(TABLE)}
    assert "active" in str(columns["status"]["default"])


def test_money_is_integer_cents(from_migration):
    """A float column cannot represent 0.10 exactly, and these are summed per
    client into an invoice."""
    columns = {c["name"]: str(c["type"]).upper()
               for c in from_migration.get_columns(TABLE)}
    assert "INT" in columns["monthly_fee_cents"]
    assert "INT" in columns["per_meeting_fee_cents"]


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    assert TABLE not in inspector.get_table_names()
    assert SECOND not in inspector.get_table_names()
    assert "client_workspace_id" not in {c["name"]
                                         for c in inspector.get_columns("strategies")}
    engine.dispose()
