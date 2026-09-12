"""Migration 0038 must produce exactly the schema the models declare.

Same copy-based technique as tests/test_pipeline_features_migration.py: the
full chain cannot run on SQLite (0008_m8c2 uses op.create_foreign_key, which
SQLite has no ALTER for), so the model metadata is copied, the two tables this
migration ADDS are removed from the copy, only the prerequisites are created,
and then 0038 runs against that.

What this pins is the failure that only shows up in production: a column added
to app/db/models.py and forgotten in the migration, or declared at a different
width. `meta_title` at VARCHAR(70) and `meta_description` at VARCHAR(165) are
load-bearing, not cosmetic -- they are where Google truncates a SERP entry, and
a column that silently allows more lets a page ship with an ellipsis where its
call to action should be.
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

MIGRATION = "0038_website_builder.py"
NEW_TABLES = ["site_pages", "site_assets"]

# workspaces is the only FK target 0038 needs, and it needs users beneath it.
_PREREQ = ["users", "workspaces"]

# Types as SQLITE renders them: sa.Uuid() is CHAR(32) there and UUID on
# PostgreSQL, and DateTime(timezone=True) is DATETIME. The dialect-independent
# guard is test_new_tables_match_the_models, which diffs the migration against
# the models; this table pins the widths that carry meaning on their own.
_UUID = "CHAR(32)"

EXPECTED_SITE_PAGES = {
    "id": _UUID, "workspace_id": _UUID, "page_type": "VARCHAR(30)",
    "slug": "VARCHAR(200)", "title": "VARCHAR(200)", "meta_title": "VARCHAR(70)",
    "meta_description": "VARCHAR(165)", "target_keyword": "VARCHAR(200)",
    "brief": "TEXT", "secondary_keywords": "JSON", "html_content": "TEXT",
    "word_count": "INTEGER", "reading_time_mins": "INTEGER",
    "schema_markup_json": "JSON", "internal_links_json": "JSON",
    "status": "VARCHAR(20)", "published_at": "DATETIME",
    "last_generated_at": "DATETIME", "generation_version": "INTEGER",
    "seo_score": "INTEGER", "seo_issues_json": "JSON", "created_at": "DATETIME",
}
EXPECTED_SITE_ASSETS = {
    "id": _UUID, "page_id": _UUID, "asset_type": "VARCHAR(20)",
    "filename": "VARCHAR(300)", "content": "TEXT", "created_at": "DATETIME",
}
NULLABLE_SITE_PAGES = {"workspace_id", "word_count", "reading_time_mins",
                       "schema_markup_json", "published_at", "last_generated_at",
                       "seo_score"}


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
    for name in NEW_TABLES:
        meta.remove(meta.tables[name])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: {"columns": list(i["column_names"]),
                                "unique": bool(i["unique"])}
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
            _load(MIGRATION).upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_the_revision_follows_0037():
    """A branched chain is an `alembic upgrade head` that fails on the deploy,
    not in CI."""
    module = _load(MIGRATION)
    assert module.revision == "0038_website_builder"
    assert module.down_revision == "0037_roi_dashboard"


@pytest.mark.parametrize("table", NEW_TABLES)
def test_new_tables_match_the_models(from_models, from_migration, table):
    assert _describe(from_migration, table) == _describe(from_models, table)


def test_site_pages_columns_and_widths(from_migration):
    """The widths are the SEO contract -- 70 and 165 are SERP truncation."""
    columns = _describe(from_migration, "site_pages")["columns"]
    assert set(columns) == set(EXPECTED_SITE_PAGES)
    for name, expected_type in EXPECTED_SITE_PAGES.items():
        assert columns[name]["type"] == expected_type, name
        assert columns[name]["nullable"] is (name in NULLABLE_SITE_PAGES), name


def test_site_assets_columns(from_migration):
    columns = _describe(from_migration, "site_assets")["columns"]
    assert set(columns) == set(EXPECTED_SITE_ASSETS)
    for name, expected_type in EXPECTED_SITE_ASSETS.items():
        assert columns[name]["type"] == expected_type, name


def test_slug_is_unique(from_migration):
    """Slug IS the public URL. Two rows claiming one path has no defined
    answer for what gets served, and the export writes one file per slug."""
    uniques = {tuple(sorted(u["column_names"]))
               for u in from_migration.get_unique_constraints("site_pages")}
    assert ("slug",) in uniques


def test_the_two_lookup_indexes_exist(from_migration):
    indexes = {i["name"]: list(i["column_names"])
               for i in from_migration.get_indexes("site_pages")}
    assert indexes.get("ix_site_pages_status_type") == ["status", "page_type"]
    assert indexes.get("ix_site_pages_target_keyword") == ["target_keyword"]


def test_site_assets_cascades_from_its_page(from_migration):
    fks = from_migration.get_foreign_keys("site_assets")
    assert any(fk["referred_table"] == "site_pages"
               and fk["constrained_columns"] == ["page_id"] for fk in fks)


def test_check_constraints_reject_bad_values(tmp_path):
    """page_type decides the schema.org markup and status decides whether a
    page is served publicly -- both are CHECK-constrained on purpose."""
    import uuid

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'ck.db'}")
    _build_prereqs(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()

    insert = sa.text(
        "INSERT INTO site_pages (id, page_type, slug, title, meta_title, "
        "meta_description, target_keyword, brief, secondary_keywords, "
        "html_content, internal_links_json, status, generation_version, "
        "seo_issues_json, created_at) VALUES (:id, :page_type, :slug, 't', "
        "'mt', 'md', 'kw', '', '[]', '', '[]', :status, 1, '[]', CURRENT_TIMESTAMP)")

    with engine.begin() as connection:
        connection.execute(sa.text("PRAGMA foreign_keys=ON"))
        # A legal row lands.
        connection.execute(insert, {"id": str(uuid.uuid4()), "page_type": "blog",
                                    "slug": "ok", "status": "draft"})

    for bad in ({"page_type": "newsletter", "status": "draft", "slug": "b1"},
                {"page_type": "blog", "status": "live", "slug": "b2"}):
        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as connection:
                connection.execute(insert, {"id": str(uuid.uuid4()), **bad})
    engine.dispose()


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    for table in NEW_TABLES:
        assert table not in inspector.get_table_names()
    engine.dispose()
