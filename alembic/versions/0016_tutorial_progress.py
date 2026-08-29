"""Per-user tutorial progress for the Learn LeadPilot section.

Feature 2. ONE new table and nothing else -- no column is added to any existing
table, so this migration cannot affect a single existing query.

WHY THERE IS NO `tutorials` TABLE
---------------------------------
The video catalogue lives in app/services/tutorials.py, in code. It is
editorial content, not user data: it is the same in every environment, it
changes when someone records a video, and replacing a placeholder id should be
a reviewed one-line diff rather than hand-written SQL against production. See
that module's docstring for the full reasoning and the cost.

This table therefore references the catalogue by `tutorial_slug` with NO
foreign key -- there is nothing to point at. The API validates every slug
against the catalogue before writing, so an unknown slug is a 404 and never a
silently-stored orphan row.

The trade-off to know about: renaming a slug in the catalogue orphans the
progress rows that point at it. Titles are safe to change; slugs are not.

UNIQUE (user_id, tutorial_slug)
-------------------------------
One row per user per video. A video player emits progress updates constantly,
and without this constraint two near-simultaneous updates insert two rows --
after which "has this user finished this video?" has two different answers
depending on which row you read.

NO BACKFILL
-----------
Unlike 0015, there is nothing to backfill: an absent row means "not started",
which is the correct state for every existing user. The API treats a missing
row as zero progress rather than requiring one to exist.

DOWNGRADE
---------
Drops the table, which DISCARDS every user's watch progress and therefore
every earned badge (badges are derived from progress, not stored). There is
nowhere else to put that data. It does not affect anything outside this
feature.

Revision ID: 0016_tutorial_progress
Revises: 0015_email_verification
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_tutorial_progress"
down_revision = "0015_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tutorial_progress",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tutorial_slug", sa.String(length=100), nullable=False),
        # Resume point. Latest value wins -- scrubbing back means resuming back.
        sa.Column("position_seconds", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        # Furthest point reached, 0-100. Monotonic -- only an explicit reset
        # lowers it, so a rewatch can never undo a completion.
        sa.Column("percent", sa.Float(), nullable=False, server_default="0"),
        # Quoted '0': PostgreSQL casts the string literal to boolean false.
        # An unquoted 0 is an integer and PostgreSQL rejects it on a boolean.
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_watched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_tutorial_progress_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutorial_progress"),
        sa.UniqueConstraint("user_id", "tutorial_slug",
                            name="uq_tutorial_progress_user_id_tutorial_slug"),
    )
    op.create_index(
        "ix_tutorial_progress_user_id", "tutorial_progress", ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_tutorial_progress_tutorial_slug", "tutorial_progress",
        ["tutorial_slug"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tutorial_progress_tutorial_slug",
                  table_name="tutorial_progress")
    op.drop_index("ix_tutorial_progress_user_id",
                  table_name="tutorial_progress")
    op.drop_table("tutorial_progress")
