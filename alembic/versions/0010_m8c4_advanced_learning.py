"""M8-C4: advanced learning schema additions

Revision ID: 0010_m8c4
Revises: 0009_m8c3
Create Date: 2026-08-17 01:00:00.000000

Changes:
  1. playbook_scores: decay_half_life_days, effective_sample_size, oldest_outcome_ts, trend
  2. subject_line_patterns table (NEW)
  3. messages.personalization_score column
  4. strategies.personalization_correlation column
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_m8c4"
down_revision = "0009_m8c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. playbook_scores: decay columns
    op.add_column("playbook_scores", sa.Column(
        "decay_half_life_days", sa.Integer, nullable=True,
        comment="Half-life in days used for exponential decay weighting"
    ))
    op.add_column("playbook_scores", sa.Column(
        "effective_sample_size", sa.Float, nullable=True,
        comment="Sum of decay weights (Σ e^(-λ*t)) — not raw count"
    ))
    op.add_column("playbook_scores", sa.Column(
        "oldest_outcome_ts", sa.DateTime, nullable=True,
        comment="Oldest outcome timestamp contributing to this score"
    ))
    op.add_column("playbook_scores", sa.Column(
        "trend", sa.String(16), nullable=True,
        comment="rising | falling | stable | new"
    ))

    # 2. subject_line_patterns table
    op.create_table(
        "subject_line_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("pattern_type", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("avg_reply_rate", sa.Float, nullable=True),
        sa.Column("avg_meeting_rate", sa.Float, nullable=True),
        sa.Column("sample_size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_reliable", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("example", sa.Text, nullable=True),
        sa.Column("last_updated", sa.DateTime, nullable=True),
        sa.UniqueConstraint("pattern_type", "channel", name="uq_subject_pattern_type_channel"),
    )
    op.create_index("ix_subject_patterns_channel", "subject_line_patterns", ["channel"])

    # 3. messages.personalization_score
    op.add_column("messages", sa.Column(
        "personalization_score", sa.Float, nullable=True,
        comment="0.0–1.0; proportion of available enrichment fields used in the rendered body"
    ))

    # 4. strategies.personalization_correlation
    op.add_column("strategies", sa.Column(
        "personalization_correlation", sa.Float, nullable=True,
        comment="Pearson r between personalization_score and reply rate for this strategy"
    ))


def downgrade() -> None:
    op.drop_column("playbook_scores", "decay_half_life_days")
    op.drop_column("playbook_scores", "effective_sample_size")
    op.drop_column("playbook_scores", "oldest_outcome_ts")
    op.drop_column("playbook_scores", "trend")
    op.drop_table("subject_line_patterns")
    op.drop_column("messages", "personalization_score")
    op.drop_column("strategies", "personalization_correlation")
