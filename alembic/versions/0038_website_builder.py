"""Website builder — AI-generated SEO marketing pages.

CREATES
  site_pages   one generated marketing page: its SEO metadata, the rendered
               HTML, the schema markup, and its measured SEO score
  site_assets  per-page image/css/js payloads, cascade-deleted with the page

No existing table changes.

CHECK CONSTRAINTS, DELIBERATELY. Every other enum in this schema is a bare
VARCHAR (see app/db/models.py's module docstring) precisely so that adding a
value later is a data-free change. These three columns carry real CHECKs
instead, because `page_type` decides which schema.org markup a page gets and
`status` decides whether a page is served to the public internet: a typo in
either is a page that either ranks wrongly or leaks. Adding a page type later
therefore costs one ALTER, which is the trade being made on purpose.

UUID PRIMARY KEYS are client-generated (uuid4 from the model), matching every
other table here rather than the `gen_random_uuid()` the feature spec named.
That is what lets the whole schema be built on SQLite for the migration tests;
pgcrypto's gen_random_uuid() has no SQLite equivalent.

`brief` is carried on the row although the feature spec's column list omits
it. Regeneration (POST /site/pages/{id}/regenerate) has to feed the generator
the same content brief the page was created from; without it a regenerate
silently produces unrelated copy at the same URL.

`slug` is UNIQUE because it IS the public URL path. Two rows claiming
"blog/agency-pipeline" have no defined answer for what gets served there, and
the export writes one file per slug, so the second would silently overwrite
the first.

Revision ID: 0038_website_builder
Revises: 0037_roi_dashboard
"""

import sqlalchemy as sa
from alembic import op

revision = "0038_website_builder"
down_revision = "0037_roi_dashboard"
branch_labels = None
depends_on = None

PAGE_TYPES = ("landing", "blog", "case_study", "comparison", "location")
PAGE_STATUSES = ("draft", "published", "archived")
ASSET_TYPES = ("image", "css", "js")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "site_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("page_type", sa.String(length=30), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("meta_title", sa.String(length=70), nullable=False),
        sa.Column("meta_description", sa.String(length=165), nullable=False),
        sa.Column("target_keyword", sa.String(length=200), nullable=False),
        # NOT in the feature spec's column list, added because ENDPOINT 4
        # (regenerate) is unimplementable without it: the content brief is
        # the single largest input to generation, and a page regenerated
        # without it would come back as different copy on the same URL.
        sa.Column("brief", sa.Text(), server_default="", nullable=False),
        sa.Column("secondary_keywords", sa.JSON(), server_default=sa.text("'[]'"),
                  nullable=False),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("reading_time_mins", sa.Integer(), nullable=True),
        sa.Column("schema_markup_json", sa.JSON(), nullable=True),
        sa.Column("internal_links_json", sa.JSON(), server_default=sa.text("'[]'"),
                  nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft",
                  nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generation_version", sa.Integer(), server_default=sa.text("1"),
                  nullable=False),
        sa.Column("seo_score", sa.Integer(), nullable=True),
        sa.Column("seo_issues_json", sa.JSON(), server_default=sa.text("'[]'"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_site_pages"),
        sa.UniqueConstraint("slug", name="uq_site_pages_slug"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE",
                                name="fk_site_pages_workspace_id_workspaces"),
        sa.CheckConstraint(_in_list("page_type", PAGE_TYPES),
                           name="ck_site_pages_page_type"),
        sa.CheckConstraint(_in_list("status", PAGE_STATUSES),
                           name="ck_site_pages_status"),
    )
    op.create_index("ix_site_pages_workspace_id", "site_pages", ["workspace_id"])
    op.create_index("ix_site_pages_status_type", "site_pages", ["status", "page_type"])
    op.create_index("ix_site_pages_target_keyword", "site_pages", ["target_keyword"])

    op.create_table(
        "site_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_site_assets"),
        sa.ForeignKeyConstraint(["page_id"], ["site_pages.id"], ondelete="CASCADE",
                                name="fk_site_assets_page_id_site_pages"),
        sa.CheckConstraint(_in_list("asset_type", ASSET_TYPES),
                           name="ck_site_assets_asset_type"),
    )
    op.create_index("ix_site_assets_page_id", "site_assets", ["page_id"])


def downgrade() -> None:
    op.drop_index("ix_site_assets_page_id", table_name="site_assets")
    op.drop_table("site_assets")
    op.drop_index("ix_site_pages_target_keyword", table_name="site_pages")
    op.drop_index("ix_site_pages_status_type", table_name="site_pages")
    op.drop_index("ix_site_pages_workspace_id", table_name="site_pages")
    op.drop_table("site_pages")
