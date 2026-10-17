"""Migration 0091 (connector OAuth): two new tables and two auth_sessions
columns matching the model, chained after 0090, names within PostgreSQL's
63-character limit, no JSONB, a downgrade that removes exactly what it added,
and still ONE head (which the activation script targets)."""

from __future__ import annotations

import importlib.util
import os
import re

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.db import models as m  # noqa: F401
from app.db.base import Base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = "0091_oauth_connector.py"
TABLES = ("oauth_clients", "oauth_authorization_codes")
SESSION_COLUMNS = ("oauth_client_id", "scope")
SESSION_INDEX = "ix_auth_sessions_oauth_client_id"


def _load(name=MIGRATION):
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(ROOT, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, *steps):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            for step in steps:
                step()


def _strip_session_columns():
    from alembic import op

    op.drop_index(SESSION_INDEX, table_name="auth_sessions")
    with op.batch_alter_table("auth_sessions") as batch:
        for column in SESSION_COLUMNS:
            batch.drop_column(column)


def _engine_before(tmp_path):
    """The schema at 0090: every model table but the two new ones, and
    auth_sessions without the two new columns."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'oauth.db'}")
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables
                                             if t.name not in TABLES])
    _run(engine, _strip_session_columns)
    return engine


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: (list(i["column_names"]), bool(i["unique"]))
                    for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 f["options"].get("ondelete")) for f in inspector.get_foreign_keys(table)},
    }


def _config():
    config = Config(os.path.join(ROOT, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    return config


def test_the_revision_follows_0090_and_the_chain_has_one_head():
    module = _load()
    assert module.revision == "0091_oauth_connector"
    assert module.down_revision == "0090_email_network"
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_the_activation_script_targets_the_head():
    from scripts import activate_with_keys as act

    assert [act.TARGET_REVISION] == ScriptDirectory.from_config(_config()).get_heads()


def test_upgrade_matches_the_model(tmp_path):
    engine = _engine_before(tmp_path)
    assert not set(SESSION_COLUMNS) & {c["name"] for c in
                                       sa.inspect(engine).get_columns("auth_sessions")}
    _run(engine, _load().upgrade)
    reference = sa.create_engine(f"sqlite:///{tmp_path / 'model.db'}")
    Base.metadata.create_all(reference)
    got, want = sa.inspect(engine), sa.inspect(reference)
    for table in (*TABLES, "auth_sessions"):
        assert _describe(got, table) == _describe(want, table), table
    engine.dispose()
    reference.dispose()


def test_constraint_names_fit_postgres_and_no_jsonb():
    source = open(os.path.join(ROOT, "alembic", "versions", MIGRATION), encoding="utf-8").read()
    names = re.findall(r'"((?:ix|uq|pk|fk)_[a-z0-9_]+)"', source)
    assert names and all(len(n) <= 63 for n in names), max(names, key=len)
    for table in TABLES:
        for constraint in Base.metadata.tables[table].constraints:
            assert constraint.name is None or len(constraint.name) <= 63
        for index in Base.metadata.tables[table].indexes:
            assert len(index.name) <= 63
    assert "postgresql." not in source and "JSONB" not in source


def test_downgrade_removes_exactly_what_upgrade_added(tmp_path):
    engine = _engine_before(tmp_path)
    before_tables = set(sa.inspect(engine).get_table_names())
    before_sessions = _describe(sa.inspect(engine), "auth_sessions")
    module = _load()
    _run(engine, module.upgrade)
    _run(engine, module.downgrade)
    inspector = sa.inspect(engine)
    assert set(inspector.get_table_names()) == before_tables
    assert _describe(inspector, "auth_sessions") == before_sessions
    engine.dispose()


def test_the_codes_table_belongs_to_the_account_and_clients_do_not():
    from app.services import account_erasure, account_export

    assert account_export.OWNERSHIP["oauth_authorization_codes"] == ["user_id"]
    assert "oauth_clients" in account_export.EXCLUDED
    assert "oauth_authorization_codes" in account_erasure.DELETED
    codes = Base.metadata.tables["oauth_authorization_codes"]
    assert {fk.column.table.name for fk in codes.foreign_keys} == {"users"}
