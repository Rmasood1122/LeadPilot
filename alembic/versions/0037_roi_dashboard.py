"""Feature 5 — client ROI dashboard.

CREATES
  roi_snapshots  one row per (strategy, day): the six metrics as they stood
                 that day, written by the 01:00 UTC sweep

ALTERS
  leads  estimated_deal_value

LeadStatus GAINS "proposal_sent". No DDL: every enum in this schema is stored
as VARCHAR (native_enum=False -- see app/db/models.py's module docstring), so
adding a value is a data-free change. "meeting_booked" and "closed_won", which
the same feature specification also lists, have existed since M3 and Feature
Group 7 respectively; only "proposal_sent" is new.

estimated_deal_value is Numeric(12,2) and NULLABLE. Money is never a float --
a pipeline summed in binary floating point is a pipeline that disagrees with
itself by cents at scale. NULL means "nobody has put a number on this lead",
which is a different fact from a deal worth nothing, and the ROI sums skip it
rather than reading it as zero.

The UNIQUE (strategy_id, snapshot_date) is what makes the daily sweep
idempotent: re-running it updates the day's row instead of appending a second,
so a retried or double-scheduled job cannot double-count a day.

Revision ID: 0037_roi_dashboard
Revises: 0036_displacement_alerts
"""

import sqlalchemy as sa
from alembic import op

revision = "0037_roi_dashboard"
down_revision = "0036_displacement_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads",
                  sa.Column("estimated_deal_value", sa.Numeric(12, 2), nullable=True))

    op.create_table(
        "roi_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("meetings_booked", sa.Integer(), server_default=sa.text("0"),
                  nullable=False),
        sa.Column("pipeline_value", sa.Numeric(12, 2), server_default=sa.text("0"),
                  nullable=False),
        sa.Column("messages_sent", sa.Integer(), server_default=sa.text("0"),
                  nullable=False),
        sa.Column("reply_rate", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("time_saved_hours", sa.Float(), server_default=sa.text("0"),
                  nullable=False),
        sa.Column("revenue_attributed", sa.Numeric(12, 2), server_default=sa.text("0"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roi_snapshots"),
        sa.UniqueConstraint("strategy_id", "snapshot_date", name="roi_strategy_day"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE",
                                name="fk_roi_snapshots_strategy_id_strategies"),
    )
    op.create_index("ix_roi_snapshots_strategy_id", "roi_snapshots", ["strategy_id"])


def downgrade() -> None:
    op.drop_index("ix_roi_snapshots_strategy_id", table_name="roi_snapshots")
    op.drop_table("roi_snapshots")
    with op.batch_alter_table("leads") as batch:
        batch.drop_column("estimated_deal_value")
