"""Feature Group 9 — trust & deliverability.

CREATES
  deliverability_checks  health / blacklist checks per sending domain (history)
  compliance_audit_log   region, regime, checks and decision for every send

No existing table changes. The new campaign state "paused_blacklist" and the
reply class "automated_response" live in existing VARCHAR columns.

Revision ID: 0031_trust_deliverability
Revises: 0030_workspaces
"""

import sqlalchemy as sa
from alembic import op

revision = "0031_trust_deliverability"
down_revision = "0030_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deliverability_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=True),
        sa.Column("listed_on", sa.JSON(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_deliverability_checks"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_deliverability_checks_user_id_users"),
    )
    op.create_index("ix_deliverability_checks_user_kind_checked", "deliverability_checks",
                    ["user_id", "kind", "checked_at"])

    op.create_table(
        "compliance_audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("region", sa.String(length=10), nullable=True),
        sa.Column("regime", sa.String(length=40), nullable=True),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("checks_json", sa.JSON(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_compliance_audit_log"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_compliance_audit_log_user_id_users"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL",
                                name="fk_compliance_audit_log_lead_id_leads"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL",
                                name="fk_compliance_audit_log_message_id_messages"),
    )
    op.create_index("ix_compliance_audit_log_lead_id", "compliance_audit_log", ["lead_id"])
    op.create_index("ix_compliance_audit_log_user_ts", "compliance_audit_log", ["user_id", "ts"])


def downgrade() -> None:
    op.drop_table("compliance_audit_log")
    op.drop_table("deliverability_checks")
