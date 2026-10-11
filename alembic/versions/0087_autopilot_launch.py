"""Autopilot launch + best time to send (docs/features/autopilot-launch.md).

CREATES
  autopilot_launches   UNIQUE(strategy_id). The per-strategy Autopilot opt-in,
                       the lawful-basis confirmation it requires (who, when,
                       text version, exact text), and the launch state (batch,
                       per-channel sequences, per-channel status, notification
                       memory, the conditional-UPDATE claim).

ALTERS
  strategies   send_time_plan_json      (JSON, NULL) per-channel send windows
               send_time_override_json  (JSON, NULL) the person's own window
  messages     ix_messages_status_sent_at (status, sent_at) for the periodic
               best-time learning refresh

strategy_id is ON DELETE CASCADE (the row goes with its strategy);
confirmed_by_user_id and batch_id are SET NULL. No prospect data. The durable
audit of every opt-in / opt-out is in compliance_audit_log, untouched here.

Both new strategies columns are nullable with no default, so the ALTER succeeds
on a table that already has rows and every existing strategy keeps today's
behaviour (no plan = channel priors; no override).

DOWNGRADE drops the table and the two columns: opt-in rows, launch state and
send-time plans are lost; the audit rows in compliance_audit_log remain.

Revision ID: 0087_autopilot_launch
Revises: 0086_inbound_reply_threading
"""

import sqlalchemy as sa
from alembic import op

revision = "0087_autopilot_launch"
down_revision = "0086_inbound_reply_threading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autopilot_launches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("state", sa.String(length=30), server_default="off", nullable=False),
        sa.Column("state_reason", sa.Text(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text_version", sa.String(length=60), nullable=True),
        sa.Column("confirmed_text", sa.Text(), nullable=True),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("sequences_json", sa.JSON(), nullable=True),
        sa.Column("channels_json", sa.JSON(), nullable=True),
        sa.Column("notified_json", sa.JSON(), nullable=True),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("launched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("batch_ids_json", sa.JSON(), nullable=True),
        sa.Column("eligible_json", sa.JSON(), nullable=True),
        sa.Column("unreachable_json", sa.JSON(), nullable=True),
        sa.Column("icp_json", sa.JSON(), nullable=True),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chain_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chain_attempts", sa.Integer(), server_default=sa.text("0"),
                  nullable=False),
        sa.Column("whatsapp_template_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_autopilot_launches"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE",
                                name="fk_autopilot_launches_strategy_id_strategies"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_autopilot_launches_confirmed_by_user_id_users"),
        sa.ForeignKeyConstraint(["batch_id"], ["lead_batches.id"], ondelete="SET NULL",
                                name="fk_autopilot_launches_batch_id_lead_batches"),
        sa.ForeignKeyConstraint(["whatsapp_template_id"], ["whatsapp_templates.id"],
                                ondelete="SET NULL",
                                name="fk_autopilot_launches_whatsapp_template_id_whatsapp_templates"),
        sa.UniqueConstraint("strategy_id", name="uq_autopilot_launches_strategy_id"),
    )
    # The best-time learning refresh (send_time.refresh_learning) scans recent
    # SENT messages by (status, sent_at).
    op.create_index("ix_messages_status_sent_at", "messages", ["status", "sent_at"])
    op.add_column("strategies", sa.Column("send_time_plan_json", sa.JSON(), nullable=True))
    op.add_column("strategies", sa.Column("send_time_override_json", sa.JSON(),
                                          nullable=True))


def downgrade() -> None:
    op.drop_index("ix_messages_status_sent_at", table_name="messages")
    with op.batch_alter_table("strategies") as batch:
        batch.drop_column("send_time_override_json")
        batch.drop_column("send_time_plan_json")
    op.drop_table("autopilot_launches")
