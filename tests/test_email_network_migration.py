"""Migration 0090 (email network): four new tables matching the model, chained
after 0089, names within PostgreSQL's 63-character limit, no JSONB, and a
downgrade that drops exactly those tables. The chain still has ONE head."""

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
MIGRATION = "0090_email_network.py"
TABLES = ("email_network_imports", "email_contacts", "email_contact_matches",
          "email_network_messages")


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


def _engine_before(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'en.db'}")
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables
                                             if t.name not in TABLES])
    return engine


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: list(i["column_names"]) for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 f["options"].get("ondelete")) for f in inspector.get_foreign_keys(table)},
    }


def test_the_revision_follows_0089_and_the_chain_has_one_head():
    module = _load()
    assert module.revision == "0090_email_network"
    assert module.down_revision == "0089_voice_twin"
    config = Config(os.path.join(ROOT, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1


def test_the_activation_script_targets_the_head():
    from scripts import activate_with_keys as act

    config = Config(os.path.join(ROOT, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    assert [act.TARGET_REVISION] == ScriptDirectory.from_config(config).get_heads()


def test_upgrade_matches_the_model(tmp_path):
    engine = _engine_before(tmp_path)
    _run(engine, _load().upgrade)
    reference = sa.create_engine(f"sqlite:///{tmp_path / 'model.db'}")
    Base.metadata.create_all(reference)
    got, want = sa.inspect(engine), sa.inspect(reference)
    for table in TABLES:
        assert _describe(got, table) == _describe(want, table), table
    engine.dispose()
    reference.dispose()


def test_constraint_names_fit_postgres_and_no_jsonb():
    source = open(os.path.join(ROOT, "alembic", "versions", MIGRATION), encoding="utf-8").read()
    names = re.findall(r'name="([^"]+)"', source)
    names += [f"ix_email_network_messages_{c}" for c in
              ("user_id", "contact_id", "product_id", "strategy_id", "lead_id", "message_id")]
    assert names and all(len(n) <= 63 for n in names), max(names, key=len)
    for table in TABLES:
        for constraint in Base.metadata.tables[table].constraints:
            assert constraint.name is None or len(constraint.name) <= 63
        for index in Base.metadata.tables[table].indexes:
            assert len(index.name) <= 63
    assert "postgresql." not in source and "JSONB" not in source


def test_downgrade_drops_exactly_the_new_tables(tmp_path):
    engine = _engine_before(tmp_path)
    before = set(sa.inspect(engine).get_table_names())
    module = _load()
    _run(engine, module.upgrade)
    assert set(TABLES) <= set(sa.inspect(engine).get_table_names())
    _run(engine, module.downgrade)
    assert set(sa.inspect(engine).get_table_names()) == before
    engine.dispose()
