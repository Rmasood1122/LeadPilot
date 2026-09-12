"""Feature 4 — competitor displacement alerts.

CREATES
  displacement_alerts  one alert per lead whose recent LinkedIn post named a
                       competitor tool or described pipeline/people pain,
                       carrying the matched keywords, the post excerpt and a
                       ready-to-send DM

No existing table changes.

THE INDEX IS NOT OPTIONAL. Both hot paths -- the 14-day deduplication check
that runs once per lead on every twelve-hourly scan, and the alerts list --
are "the most recent alerts for this lead". Without (lead_id, created_at DESC)
the dedup check is a sequential scan per lead per sweep.

alert_status is a plain VARCHAR rather than a native enum, matching every other
status column in this schema (see app/db/models.py's module docstring): adding
a fifth state later is then a data-free change.

Revision ID: 0036_displacement_alerts
Revises: 0035_voice_profile
"""

import sqlalchemy as sa
from alembic import op

revision = "0036_displacement_alerts"
down_revision = "0035_voice_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "displacement_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("matched_keywords", sa.JSON(), nullable=True),
        sa.Column("post_excerpt", sa.Text(), nullable=False),
        sa.Column("post_url", sa.String(length=500), nullable=True),
        sa.Column("suggested_dm", sa.Text(), nullable=True),
        sa.Column("alert_status", sa.String(length=20), server_default="pending",
                  nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_displacement_alerts"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_displacement_alerts_lead_id_leads"),
    )
    op.create_index("ix_displacement_alerts_lead_id", "displacement_alerts", ["lead_id"])
    op.create_index("ix_displacement_alerts_lead_created", "displacement_alerts",
                    ["lead_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_displacement_alerts_lead_created",
                  table_name="displacement_alerts")
    op.drop_index("ix_displacement_alerts_lead_id", table_name="displacement_alerts")
    op.drop_table("displacement_alerts")
