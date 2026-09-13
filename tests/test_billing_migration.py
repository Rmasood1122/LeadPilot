"""Migration 0040 (Section E billing) must produce exactly the schema the
models declare. It only creates tables, so the prerequisites come straight from
the metadata copy -- same technique as tests/test_trust_migration.py.

Beyond "columns match", pinned: the UNIQUE (user_id, dedupe_key) that makes
"charge once per prospect" a schema guarantee, and the one-subscription-per-
account uniqueness.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0040_billing.py"
NEW_TABLES = ["billing_subscriptions", "billable_meetings"]
_PREREQ = ["users", "products", "strategies", "lead_batches", "linkedin_accounts", "leads"]


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
        "indexes": {i["name"]: {"columns": list(i["column_names"]), "unique": bool(i["unique"])}
                    for i in inspector.get_indexes(table)},
        "uniques": {tuple(sorted(u["column_names"]))
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
def migrated(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _build_prereqs(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()
    yield engine
    engine.dispose()


def test_the_revision_follows_0039():
    module = _load(MIGRATION)
    assert module.revision == "0040_billing"
    assert module.down_revision == "0039_identity_verification"


@pytest.mark.parametrize("table", NEW_TABLES)
def test_tables_match_the_models(from_models, migrated, table):
    migrated_shape = _describe(sa.inspect(migrated), table)
    model_shape = _describe(from_models, table)
    assert migrated_shape["columns"] == model_shape["columns"]
    assert migrated_shape["fks"] == model_shape["fks"]
    assert migrated_shape["indexes"] == model_shape["indexes"]
    # SQLite reports a unique=True column as a unique INDEX on one side and a
    # constraint on the other; compare the union of both as column sets.
    def _unique_sets(shape):
        return shape["uniques"] | {tuple(sorted(i["columns"]))
                                   for i in shape["indexes"].values() if i["unique"]}
    assert _unique_sets(migrated_shape) == _unique_sets(model_shape)


def test_a_prospect_can_be_billed_only_once(migrated):
    user_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    with migrated.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO users (id, email, plan, theme_json, is_admin, is_suspended, "
            "email_verified, identity_required, phone_verified, created_at, updated_at) "
            "VALUES (:id, 'a@x.com', 'free', '{}', 0, 0, 1, 0, 0, :now, :now)"),
            {"id": user_id, "now": now})
    insert = sa.text(
        "INSERT INTO billable_meetings (id, user_id, dedupe_key, source, amount_cents, "
        "currency, status, occurred_at, charge_after, is_stub, created_at, updated_at) "
        "VALUES (:id, :user, 'lead-1', 'calendly', 17900, 'usd', 'pending', :now, :now, 0, "
        ":now, :now)")
    with migrated.begin() as connection:
        connection.execute(insert, {"id": uuid.uuid4().hex, "user": user_id, "now": now})
    with pytest.raises(sa.exc.IntegrityError):
        with migrated.begin() as connection:
            connection.execute(insert, {"id": uuid.uuid4().hex, "user": user_id, "now": now})


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    assert not set(NEW_TABLES) & set(sa.inspect(engine).get_table_names())
    engine.dispose()
