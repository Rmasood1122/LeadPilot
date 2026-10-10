"""F10 Champion Tracker: recorded departures (the send block + the metric).

CREATES
  champion_moves   one row per person confirmed to have left the company a
                   lead was sourced at; UNIQUE(old_lead_id)

Holds an address HASH (old_email_sha256), never the address. user_id is ON
DELETE CASCADE (the account's records go with the account); old_lead_id /
new_lead_id are SET NULL (a deleted lead does not lift the block on its
address); dismissed_by_user_id is SET NULL.

Create-only: nothing existing is altered. Per-lead role-check state lives in
leads.enrichment_json.role_check (no column change).

DOWNGRADE drops the table, which loses the recorded departures -- and with
them the send-time block on those old addresses. Nothing else is touched.

Revision ID: 0080_champion_tracker
Revises: 0079_pilot_mode
"""

import sqlalchemy as sa
from alembic import op

revision = "0080_champion_tracker"
down_revision = "0079_pilot_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "champion_moves",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("old_lead_id", sa.Uuid(),
                  sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("new_lead_id", sa.Uuid(),
                  sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("old_email_sha256", sa.String(64), nullable=True),
        sa.Column("champion_kind", sa.String(20), nullable=True),
        sa.Column("from_company", sa.String(200), nullable=True),
        sa.Column("from_title", sa.String(200), nullable=True),
        sa.Column("to_company", sa.String(200), nullable=True),
        sa.Column("to_title", sa.String(200), nullable=True),
        sa.Column("to_domain", sa.String(255), nullable=True),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("detail", sa.String(300), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_by_user_id", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dismiss_reason", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("old_lead_id", name="uq_champion_move_old_lead"),
    )
    op.create_index("ix_champion_moves_user_id", "champion_moves", ["user_id"])
    op.create_index("ix_champion_moves_new_lead_id", "champion_moves", ["new_lead_id"])
    op.create_index("ix_champion_moves_old_email_sha256", "champion_moves",
                    ["old_email_sha256"])


def downgrade() -> None:
    op.drop_index("ix_champion_moves_old_email_sha256", table_name="champion_moves")
    op.drop_index("ix_champion_moves_new_lead_id", table_name="champion_moves")
    op.drop_index("ix_champion_moves_user_id", table_name="champion_moves")
    op.drop_table("champion_moves")
