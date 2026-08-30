"""Move the tutorial catalogue from code into the database, and seed it.

Task 3. Feature 2 deliberately kept the catalogue in
app/services/tutorials.py, so that replacing a placeholder YouTube id was a
reviewed one-line diff rather than hand-written SQL. That trade-off was
accepted at the time and then reversed on purpose: the cost of "adding a video
needs a deploy" turned out to be the one that mattered.

WHAT CHANGES
  * `tutorial_catalogue` holds the nine tutorials.
  * They are seeded with is_published = FALSE.
  * app/services/tutorials.py keeps the same nine entries as SEED_CATALOGUE.
    That constant is the source for THIS migration and nothing reads it at
    runtime -- it stays so a fresh database is seeded identically and so the
    editorial text remains reviewable in git.

WHY is_published DEFAULTS FALSE
Every seeded row has youtube_id = NULL. Published, they would render as nine
permanent "coming soon" cards, which reads as a broken feature rather than an
empty one. Unpublished, /learn is honestly empty until somebody adds a video
and presses Publish. This DOES mean the Learn tab shows nothing immediately
after this migration -- that is the intended, agreed behaviour.

NO FOREIGN KEY FROM tutorial_progress
tutorial_progress.tutorial_slug still references the catalogue by string with
no FK, and that is deliberate rather than an oversight:

  * adding an FK retroactively fails outright on any progress row whose
    tutorial has since been removed, turning this migration into something
    that can abort against real data;
  * progress SHOULD outlive a deleted tutorial. Deleting a tutorial by
    accident and re-creating it with the same slug restores every user's
    progress, which is the forgiving behaviour. An ON DELETE CASCADE would
    have destroyed it silently.

Renaming a slug still orphans progress. Moving the catalogue into a table did
not change that, and the admin API refuses slug edits for exactly that reason.

DOWNGRADE
Drops the table. Progress rows are untouched -- they are keyed by slug, so
re-running this migration restores the association. What IS lost is every
edit made through the admin UI: youtube_ids, titles, publish state. Those
exist nowhere else once the catalogue lives in the database. Take a dump.

Revision ID: 0018_tutorial_catalogue
Revises: 0017_ai_support_chat
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0018_tutorial_catalogue"
down_revision = "0017_ai_support_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    catalogue = op.create_table(
        "tutorial_catalogue",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("youtube_id", sa.String(length=32), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False,
                  server_default="0"),
        # Quoted '0': PostgreSQL casts the string literal to boolean false.
        sa.Column("is_published", sa.Boolean(), nullable=False,
                  server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tutorial_catalogue"),
        sa.UniqueConstraint("slug", name="uq_tutorial_catalogue_slug"),
    )
    op.create_index("ix_tutorial_catalogue_slug", "tutorial_catalogue",
                    ["slug"], unique=True)
    op.create_index("ix_tutorial_catalogue_level", "tutorial_catalogue",
                    ["level"])
    op.create_index("ix_tutorial_catalogue_is_published", "tutorial_catalogue",
                    ["is_published"])

    # Seed. Imported rather than duplicated so the editorial text has exactly
    # one home; a copy here would drift from the module the docs point at.
    from app.services.tutorials import SEED_CATALOGUE

    op.bulk_insert(catalogue, [
        {
            "id": uuid.uuid4(),
            "slug": entry.slug,
            "title": entry.title,
            "description": entry.description,
            "level": entry.level,
            "youtube_id": entry.youtube_id,
            "duration_seconds": entry.duration_seconds,
            "sort_order": entry.order,
            "is_published": False,
        }
        for entry in SEED_CATALOGUE
    ])


def downgrade() -> None:
    op.drop_index("ix_tutorial_catalogue_is_published",
                  table_name="tutorial_catalogue")
    op.drop_index("ix_tutorial_catalogue_level", table_name="tutorial_catalogue")
    op.drop_index("ix_tutorial_catalogue_slug", table_name="tutorial_catalogue")
    op.drop_table("tutorial_catalogue")
