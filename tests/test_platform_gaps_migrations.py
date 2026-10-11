"""Migrations 0081 (password_reset_tokens) and 0082 (PD-2 webhook foreign
keys), on SQLite. Same technique as tests/test_champion_tracker_migration.py:
build the prerequisite tables, run the migration's upgrade() through an
Alembic Operations context, and compare with what the model declares.

0082 is also exercised against PostgreSQL in
tests/integration/test_migration_0085_webhook_fks.py (the production engine,
where the constraints were actually missing).
"""

from __future__ import annotations

import importlib.util
import os
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(ROOT, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _meta():
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    return meta


def _run(engine, fn):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            fn()


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: (list(i["column_names"]), bool(i["unique"]))
                    for i in inspector.get_indexes(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 f["options"].get("ondelete"))
                for f in inspector.get_foreign_keys(table)},
    }


# --------------------------------------------------------------------------
# 0081 password_reset_tokens
# --------------------------------------------------------------------------


def _users_at_0080(engine):
    """users as it is before 0081: today's model minus password_changed_at."""
    meta = _meta()
    meta.create_all(engine, tables=[meta.tables["users"]])
    with engine.begin() as c:
        c.execute(sa.text("ALTER TABLE users DROP COLUMN password_changed_at"))


class TestPasswordResetMigration:
    MIGRATION = "0084_password_reset.py"
    TABLE = "password_reset_tokens"

    def test_adds_users_password_changed_at_like_the_model(self, tmp_path):
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'u.db'}")
        _users_at_0080(engine)
        assert "password_changed_at" not in {
            c["name"] for c in sa.inspect(engine).get_columns("users")}
        _run(engine, _load(self.MIGRATION).upgrade)
        col = {c["name"]: c for c in sa.inspect(engine).get_columns("users")}[
            "password_changed_at"]
        assert col["nullable"] and str(col["type"]) == "DATETIME"
        engine.dispose()

    def test_postgres_lock_wait_is_bounded(self):
        source = open(os.path.join(ROOT, "alembic", "versions", self.MIGRATION),
                      encoding="utf-8").read()
        code = source.split('"""', 2)[2]
        assert "SET LOCAL lock_timeout = '15s'" in code
        assert code.count("_bounded_lock_wait()") == 3  # defined + both directions

    def test_revision_chain(self):
        module = _load(self.MIGRATION)
        assert module.revision == "0084_password_reset"
        assert module.down_revision == "0083_billing_retention"

    def test_table_matches_the_model(self, tmp_path):
        models = sa.create_engine(f"sqlite:///{tmp_path / 'models.db'}")
        Base.metadata.create_all(models)
        migrated = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
        _users_at_0080(migrated)
        _run(migrated, _load(self.MIGRATION).upgrade)
        assert _describe(sa.inspect(migrated), self.TABLE) == _describe(
            sa.inspect(models), self.TABLE)
        models.dispose()
        migrated.dispose()

    def test_token_hash_is_unique_and_tokens_go_with_the_account(self, tmp_path):
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
        _users_at_0080(engine)
        _run(engine, _load(self.MIGRATION).upgrade)
        insp = sa.inspect(engine)
        unique = {i["name"]: i["unique"] for i in insp.get_indexes(self.TABLE)}
        assert unique["ix_password_reset_tokens_token_hash"]
        fk = insp.get_foreign_keys(self.TABLE)[0]
        assert fk["referred_table"] == "users" and fk["options"]["ondelete"] == "CASCADE"
        assert "token" not in {c["name"] for c in insp.get_columns(self.TABLE)}
        engine.dispose()

    def test_downgrade_round_trips(self, tmp_path):
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
        _users_at_0080(engine)
        module = _load(self.MIGRATION)
        _run(engine, lambda: (module.upgrade(), module.downgrade()))
        assert self.TABLE not in sa.inspect(engine).get_table_names()
        assert "password_changed_at" not in {
            c["name"] for c in sa.inspect(engine).get_columns("users")}
        engine.dispose()


# --------------------------------------------------------------------------
# 0082 webhook foreign keys (PD-2)
# --------------------------------------------------------------------------

# The 0011 shape: same columns as today's model, but NO foreign keys.
_LEGACY_DDL = (
    """CREATE TABLE webhook_targets (
        id CHAR(32) PRIMARY KEY, user_id CHAR(32) NOT NULL, url TEXT NOT NULL,
        secret_encrypted TEXT, event_types JSON NOT NULL DEFAULT '[]',
        active BOOLEAN NOT NULL DEFAULT 1, source VARCHAR(20) NOT NULL DEFAULT 'api',
        disabled_reason VARCHAR(200), description TEXT,
        created_at DATETIME, updated_at DATETIME)""",
    """CREATE TABLE webhook_deliveries (
        id CHAR(32) PRIMARY KEY, target_id CHAR(32) NOT NULL,
        event_type VARCHAR(64) NOT NULL, payload_json JSON NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        last_attempt_at DATETIME, next_attempt_at DATETIME, last_status_code INTEGER,
        last_error TEXT, delivered_at DATETIME, created_at DATETIME)""",
)


def _legacy_engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    meta = _meta()
    meta.create_all(engine, tables=[meta.tables["users"]])
    with engine.begin() as c:
        for ddl in _LEGACY_DDL:
            c.execute(sa.text(ddl))
    return engine


def _seed(engine):
    """A live user with a target and a delivery; a target whose user is gone
    (with a delivery); a delivery whose target is gone."""
    ids = {k: uuid.uuid4().hex for k in
           ("user", "t_live", "d_live", "t_orphan", "d_of_orphan", "d_orphan", "ghost_user")}
    with engine.begin() as c:
        c.execute(sa.text("INSERT INTO users (id, email, plan, theme_json, is_admin, "
                          "is_suspended, email_verified, identity_required, phone_verified) "
                          "VALUES (:id, 'live@x.io', 'FREE', '{}', 0, 0, 1, 0, 0)"),
                  {"id": ids["user"]})
        for tid, uid in ((ids["t_live"], ids["user"]), (ids["t_orphan"], ids["ghost_user"])):
            c.execute(sa.text("INSERT INTO webhook_targets (id, user_id, url) "
                              "VALUES (:id, :uid, 'https://hooks.example.com/x')"),
                      {"id": tid, "uid": uid})
        for did, tid in ((ids["d_live"], ids["t_live"]), (ids["d_of_orphan"], ids["t_orphan"]),
                         (ids["d_orphan"], uuid.uuid4().hex)):
            c.execute(sa.text("INSERT INTO webhook_deliveries (id, target_id, event_type, "
                              "payload_json) VALUES (:id, :tid, 'meeting_booked', '{}')"),
                      {"id": did, "tid": tid})
    return ids


def _fks(engine, table):
    return {(tuple(f["constrained_columns"]), f["referred_table"], f["options"].get("ondelete"))
            for f in sa.inspect(engine).get_foreign_keys(table)}


class TestWebhookForeignKeysMigration:
    MIGRATION = "0085_webhook_foreign_keys.py"

    def test_revision_chain(self):
        module = _load(self.MIGRATION)
        assert module.revision == "0085_webhook_foreign_keys"
        assert module.down_revision == "0084_password_reset"

    def test_constraint_names_follow_the_naming_convention(self):
        """The names the model metadata produces, so a later migration can
        drop them by name on either engine."""
        expected = {fk.constraint.name for t in ("webhook_targets", "webhook_deliveries")
                    for fk in Base.metadata.tables[t].foreign_keys}
        assert {name for *_rest, name in _load(self.MIGRATION)._FKS} == expected

    def test_legacy_schema_has_no_fks_before(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        assert _fks(engine, "webhook_targets") == set()
        assert _fks(engine, "webhook_deliveries") == set()
        engine.dispose()

    def test_upgrade_adds_both_cascading_fks(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        _run(engine, _load(self.MIGRATION).upgrade)
        assert _fks(engine, "webhook_targets") == {(("user_id",), "users", "CASCADE")}
        assert _fks(engine, "webhook_deliveries") == {
            (("target_id",), "webhook_targets", "CASCADE")}
        engine.dispose()

    def test_upgrade_deletes_only_the_orphans(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        ids = _seed(engine)
        _run(engine, _load(self.MIGRATION).upgrade)
        with engine.connect() as c:
            targets = {r[0] for r in c.execute(sa.text("SELECT id FROM webhook_targets"))}
            deliveries = {r[0] for r in c.execute(sa.text("SELECT id FROM webhook_deliveries"))}
        assert targets == {ids["t_live"]}
        assert deliveries == {ids["d_live"]}
        engine.dispose()

    def test_after_upgrade_removing_a_user_cascades(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        ids = _seed(engine)
        _run(engine, _load(self.MIGRATION).upgrade)
        with engine.begin() as c:
            c.execute(sa.text("PRAGMA foreign_keys=ON"))
            c.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": ids["user"]})
            left = (c.execute(sa.text("SELECT count(*) FROM webhook_targets")).scalar(),
                    c.execute(sa.text("SELECT count(*) FROM webhook_deliveries")).scalar())
        assert left == (0, 0)
        engine.dispose()

    def test_existing_fks_are_left_alone(self, tmp_path):
        """A database built from the model already has both: no-op."""
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'model.db'}")
        Base.metadata.create_all(engine)
        before = (_fks(engine, "webhook_targets"), _fks(engine, "webhook_deliveries"))
        _run(engine, _load(self.MIGRATION).upgrade)
        assert (_fks(engine, "webhook_targets"), _fks(engine, "webhook_deliveries")) == before
        engine.dispose()

    def test_downgrade_drops_the_fks_and_keeps_the_rows(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        ids = _seed(engine)
        module = _load(self.MIGRATION)
        _run(engine, module.upgrade)
        _run(engine, module.downgrade)
        assert _fks(engine, "webhook_targets") == set()
        assert _fks(engine, "webhook_deliveries") == set()
        with engine.connect() as c:
            assert c.execute(sa.text("SELECT id FROM webhook_targets")).scalars().all() == [
                ids["t_live"]]
        engine.dispose()


def test_activation_script_targets_the_new_head():
    from scripts import activate_with_keys as act

    assert act.TARGET_REVISION == "0085_webhook_foreign_keys"


@pytest.mark.parametrize("name", ["0084_password_reset.py", "0085_webhook_foreign_keys.py"])
def test_no_postgres_only_types(name):
    source = open(os.path.join(ROOT, "alembic", "versions", name), encoding="utf-8").read()
    assert "postgresql." not in source and "JSONB" not in source
