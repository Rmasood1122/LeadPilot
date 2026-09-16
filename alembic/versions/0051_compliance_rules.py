"""Configurable compliance rules (Feature 8).

CREATES
  compliance_rules  per-scope (global | workspace), per-region, per-channel
                    overrides of the send-time compliance baseline: send
                    window hours, weekend skipping, daily cap, consent
                    requirement, bounce-pause threshold. Every rule field is
                    nullable (= inherit). An EMPTY table means the hardcoded
                    baseline, i.e. exactly today's behaviour.

Revision ID: 0051_compliance_rules
Revises: 0050_benchmarks
"""

import sqlalchemy as sa
from alembic import op

revision = "0051_compliance_rules"
down_revision = "0050_benchmarks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compliance_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("region", sa.String(length=10), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("send_start_hour", sa.Integer(), nullable=True),
        sa.Column("send_end_hour", sa.Integer(), nullable=True),
        sa.Column("skip_weekends", sa.Boolean(), nullable=True),
        sa.Column("daily_cap", sa.Integer(), nullable=True),
        sa.Column("consent_required", sa.Boolean(), nullable=True),
        sa.Column("bounce_pause_threshold", sa.Float(), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_compliance_rules"),
        sa.UniqueConstraint("scope", "region", "channel", name="compliance_rule_scope"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE",
                                name="fk_compliance_rules_workspace_id_workspaces"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_compliance_rules_updated_by_user_id_users"),
    )
    op.create_index("ix_compliance_rules_workspace_id", "compliance_rules", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_compliance_rules_workspace_id", table_name="compliance_rules")
    op.drop_table("compliance_rules")
