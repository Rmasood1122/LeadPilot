"""Migration 0019_m9_crm must produce exactly the schema the models declare.

WHY THIS TEST EXISTS
The test suite builds its database with `Base.metadata.create_all()`, never by
running migrations (tests/conftest.py, SQLite in-memory). Production builds it
by running migrations and never touches create_all. So the two descriptions of
the schema are exercised by completely disjoint code paths, and a column added
to a model but forgotten in the migration passes every test in this repository
while being absent from the deployed database -- the failure only appears at
runtime, in production, as a "no such column" on a query nobody changed.

This test runs 0019's upgrade() against a real (SQLite) database and diffs the
result against what the models declare, column by column, index by index.

It cannot run the whole chain: migration 0008_m8c2 uses ALTER-to-add-a-foreign-
key, which SQLite has no support for outside batch mode. So the tables 0019
depends on (users, leads, strategies) are created from metadata, and then only
0019 is executed on top -- which is precisely the comparison that matters here.
"""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db.base import Base
from app.db import models as m

# The tables 0019 creates. Kept as a literal rather than derived from the
# metadata so that adding a table to the models without adding it to the
# migration fails HERE, loudly, instead of silently shrinking the comparison.
CRM_TABLES = [
    "crm_tags",
    "crm_notes",
    "crm_activities",
    "crm_lead_tags",
    "crm_saved_views",
    "crm_custom_fields",
    "crm_custom_field_values",
    "crm_lead_meta",
]

# Tables 0019's foreign keys point at.
_PREREQ_TABLES = ["users", "products", "strategies", "lead_batches", "leads"]


def _load_migration():
    """Import the revision file by path -- alembic/versions is not a package."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "alembic", "versions", "0019_m9_crm.py")
    spec = importlib.util.spec_from_file_location("m9_crm_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _describe(inspector, table: str) -> dict:
    """The comparable shape of one table: columns, indexes, uniques, FKs.

    Column *types* are compared as their SQLite-rendered string, because that
    is what both sides actually become on this dialect; comparing SQLAlchemy
    type objects would report VARCHAR(32) != String(32) and be useless.
    """
    columns = {
        c["name"]: {
            "type": str(c["type"]),
            "nullable": bool(c["nullable"]),
        }
        for c in inspector.get_columns(table)
    }
    indexes = {
        i["name"]: {
            "columns": list(i["column_names"]),
            "unique": bool(i["unique"]),
        }
        for i in inspector.get_indexes(table)
    }
    uniques = {
        u["name"]: sorted(u["column_names"])
        for u in inspector.get_unique_constraints(table)
    }
    fks = {
        (
            tuple(f["constrained_columns"]),
            f["referred_table"],
            tuple(f["referred_columns"]),
        )
        for f in inspector.get_foreign_keys(table)
    }
    return {"columns": columns, "indexes": indexes, "uniques": uniques,
            "fks": fks}


@pytest.fixture()
def from_models(tmp_path):
    """Schema as `Base.metadata.create_all()` builds it -- what tests run on."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    yield sa.inspect(engine)
    engine.dispose()


@pytest.fixture()
def from_migration(tmp_path):
    """Schema as migration 0019 builds it -- what production runs on."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    # Prerequisites only: 0019's foreign keys need these to exist.
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[t] for t in _PREREQ_TABLES]
    )
    migration = _load_migration()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
    yield sa.inspect(engine)
    engine.dispose()


class TestMigrationMatchesModels:
    def test_migration_creates_every_crm_table(self, from_migration):
        created = set(from_migration.get_table_names())
        assert set(CRM_TABLES) <= created, (
            f"migration 0019 did not create: {sorted(set(CRM_TABLES) - created)}"
        )

    def test_models_declare_every_crm_table(self):
        """The other direction: a table in the migration but not the models."""
        declared = {t for t in Base.metadata.tables if t.startswith("crm_")}
        assert declared == set(CRM_TABLES)

    @pytest.mark.parametrize("table", CRM_TABLES)
    def test_columns_match(self, table, from_models, from_migration):
        model_cols = _describe(from_models, table)["columns"]
        migration_cols = _describe(from_migration, table)["columns"]
        assert migration_cols == model_cols

    @pytest.mark.parametrize("table", CRM_TABLES)
    def test_indexes_match(self, table, from_models, from_migration):
        """A missing index is invisible until the table has real volume, and
        then it is a slow-query incident rather than an error."""
        assert (_describe(from_migration, table)["indexes"]
                == _describe(from_models, table)["indexes"])

    @pytest.mark.parametrize("table", CRM_TABLES)
    def test_unique_constraints_match(self, table, from_models, from_migration):
        """These carry real behaviour: crm_lead_tag_unique is what lets the
        bulk-tag endpoint be idempotent without a read-before-write."""
        assert (_describe(from_migration, table)["uniques"]
                == _describe(from_models, table)["uniques"])

    @pytest.mark.parametrize("table", CRM_TABLES)
    def test_foreign_keys_match(self, table, from_models, from_migration):
        assert (_describe(from_migration, table)["fks"]
                == _describe(from_models, table)["fks"])


class TestMigrationIsReversible:
    def test_downgrade_drops_every_crm_table(self, tmp_path):
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'roundtrip.db'}")
        Base.metadata.create_all(
            engine, tables=[Base.metadata.tables[t] for t in _PREREQ_TABLES]
        )
        migration = _load_migration()
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.downgrade()
        remaining = set(sa.inspect(engine).get_table_names())
        engine.dispose()
        assert not (remaining & set(CRM_TABLES)), (
            f"downgrade left tables behind: {sorted(remaining & set(CRM_TABLES))}"
        )


class TestRevisionChain:
    def test_extends_the_current_head(self):
        """0019 must sit on top of 0018, not fork a second head. Two heads
        make `alembic upgrade head` ambiguous and fail the deploy."""
        migration = _load_migration()
        assert migration.revision == "0019_m9_crm"
        assert migration.down_revision == "0018_tutorial_catalogue"

    def test_the_revision_chain_stays_linear(self):
        """No revision may be claimed as a parent twice, and there must be
        exactly one head.

        This started life as "0019 is a leaf, nothing may point at it", which
        was true right up until 0020_followup_delay was written on top of it --
        as every migration after a head is. Pinning the identity of the current
        head made the test fail on the one action it should permit (extending
        the chain) while still passing on the action it exists to forbid
        (rewriting it), so it now asserts the property directly.

        Two files claiming the same down_revision is a fork: `alembic upgrade
        head` becomes ambiguous and the deploy fails. Two heads is the same
        failure seen from the other end.
        """
        from collections import Counter

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Alembic's own loader, not a regex over the files: revision ids are
        # declared in several spellings across this directory (bare assignment,
        # annotated assignment, single quotes), and a regex that misses one
        # would silently shrink the comparison to the files it happened to
        # parse -- which is exactly the failure mode this test exists to catch.
        script = ScriptDirectory.from_config(
            Config(os.path.join(root, "alembic.ini"))
        )

        parents: list[str] = []
        for revision in script.walk_revisions():
            for down in (revision.down_revision or ()) if isinstance(
                revision.down_revision, tuple
            ) else ([revision.down_revision] if revision.down_revision else []):
                parents.append(down)

        forked = [rev for rev, count in Counter(parents).items() if count > 1]
        assert not forked, (
            f"these revisions are claimed as a parent by more than one "
            f"migration, which forks the chain: {sorted(forked)}"
        )
        heads = script.get_heads()
        assert len(heads) == 1, (
            f"the chain has {len(heads)} heads ({sorted(heads)}); "
            f"`alembic upgrade head` is ambiguous with more than one"
        )

    def test_0019_is_still_in_the_chain(self):
        """The half of the old test that is still meaningful: 0019 has been
        applied to real databases, so its position must not be rewritten."""
        migration = _load_migration()
        assert migration.down_revision == "0018_tutorial_catalogue"


class TestCrmActivityStaysSeparateFromOutcomes:
    """Rule 2 of the M9 brief, pinned as a test rather than a comment.

    `outcomes` is the M8 learning loop's immutable event log; the nightly
    aggregation and the A/B sweep compute rates from its row counts. If CRM
    activity is ever folded into it, those denominators change silently.
    """

    def test_crm_activity_is_its_own_table(self):
        assert m.CrmActivity.__tablename__ == "crm_activities"
        assert m.Outcome.__tablename__ == "outcomes"

    def test_migration_does_not_touch_the_outcomes_table(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "alembic", "versions", "0019_m9_crm.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ('op.add_column("outcomes"', 'op.drop_column("outcomes"',
                          'op.alter_column("outcomes"'):
            assert forbidden not in source

    def test_migration_does_not_alter_leads_or_strategies(self):
        """The no-touch guarantee from the plan, enforced. Adding a column to
        `leads` here would put CRM-only state in the row that the sourcing
        chain, the sequence engine and the SDK all load."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "alembic", "versions", "0019_m9_crm.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for table in ("leads", "strategies", "users", "messages", "outcomes"):
            for verb in ("add_column", "drop_column", "alter_column"):
                assert f'op.{verb}("{table}"' not in source
