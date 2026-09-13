"""Migration 0039 must produce exactly the schema the models declare.

Same copy-based technique as tests/test_pipeline_features_migration.py: the
full chain cannot run on SQLite, so the model metadata is copied, the columns
and tables 0039 ADDS are removed from the copy (with the indexes that reference
those columns), the prerequisites are created, and 0039 runs against that.

The property worth pinning beyond "columns match": identity_required and
phone_verified must be NOT NULL with a false server default, because that is
what keeps every pre-existing account out of the new gates without a backfill.
"""

from __future__ import annotations

import importlib.util
import os
import uuid

import sqlalchemy as sa
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0039_identity_verification.py"
ADDED_USER_COLUMNS = [
    "identity_required", "personal_country", "account_type", "company_name",
    "company_country", "identity_submitted_at", "signup_ip", "geo_detected_country",
    "geo_check_status", "geo_review_status", "geo_reviewed_by", "geo_reviewed_at",
    "geo_review_note", "phone_number", "phone_verified", "phone_verified_at",
]
NEW_TABLES = ["phone_verification_codes", "account_security_events"]


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
    users = meta.tables["users"]
    for index in list(users.indexes):
        if any(col.name in ADDED_USER_COLUMNS for col in index.columns):
            users.indexes.remove(index)
    for name in ADDED_USER_COLUMNS:
        users._columns.remove(users.c[name])
    for name in NEW_TABLES:
        meta.remove(meta.tables[name])
    meta.create_all(engine, tables=[meta.tables["users"]])


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: {"columns": list(i["column_names"]),
                                "unique": bool(i["unique"])}
                    for i in inspector.get_indexes(table)},
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
def migrated_engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _build_prereqs(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()
    yield engine
    engine.dispose()


def test_the_revision_follows_0038():
    module = _load(MIGRATION)
    assert module.revision == "0039_identity_verification"
    assert module.down_revision == "0038_website_builder"


@pytest.mark.parametrize("table", NEW_TABLES)
def test_new_tables_match_the_models(from_models, migrated_engine, table):
    assert _describe(sa.inspect(migrated_engine), table) == _describe(from_models, table)


def test_user_columns_and_indexes_match_the_models(from_models, migrated_engine):
    migrated = _describe(sa.inspect(migrated_engine), "users")
    modelled = _describe(from_models, "users")
    assert migrated["columns"] == modelled["columns"]
    for name in ("ix_users_geo_review_status", "ix_users_phone_number"):
        assert migrated["indexes"][name] == modelled["indexes"][name]


def test_existing_accounts_are_never_forced_through_the_new_gates(migrated_engine):
    """A row inserted the way a pre-0039 row exists -- without naming the new
    columns -- must read identity_required=false and phone_verified=false."""
    with migrated_engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO users (id, email, plan, theme_json, is_admin, is_suspended, "
            "email_verified, created_at, updated_at) VALUES (:id, 'old@x.com', 'free', "
            "'{}', 0, 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
            {"id": uuid.uuid4().hex})
        row = connection.execute(sa.text(
            "SELECT identity_required, phone_verified FROM users")).one()
    assert (bool(row[0]), bool(row[1])) == (False, False)


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    assert not set(NEW_TABLES) & set(inspector.get_table_names())
    present = {c["name"] for c in inspector.get_columns("users")}
    assert not set(ADDED_USER_COLUMNS) & present
    engine.dispose()
