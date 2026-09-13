"""Anonymised benchmarks (Feature 6).

CREATES
  benchmark_buckets  one row per published (industry, channel, metric):
                     account count, rounded p25/p50/p75, window, computed_at.
                     Buckets below the minimum-accounts threshold are never
                     written. No user, strategy or lead ids.

Revision ID: 0050_benchmarks
Revises: 0049_meeting_recording
"""

import sqlalchemy as sa
from alembic import op

revision = "0050_benchmarks"
down_revision = "0049_meeting_recording"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_buckets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("industry", sa.String(length=120), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("metric", sa.String(length=20), nullable=False),
        sa.Column("account_count", sa.Integer(), nullable=False),
        sa.Column("p25", sa.Float(), nullable=False),
        sa.Column("p50", sa.Float(), nullable=False),
        sa.Column("p75", sa.Float(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_benchmark_buckets"),
        sa.UniqueConstraint("industry", "channel", "metric", name="benchmark_bucket"),
    )


def downgrade() -> None:
    op.drop_table("benchmark_buckets")
