"""Daily send approval: one row per account per local day.

CREATES
  daily_send_approvals   UNIQUE(user_id, local_date). Whether a person
                         approved today's AUTOMATIC sending, for which
                         channels, the LinkedIn risk acknowledgement and the
                         warning version shown, and the once-per-day
                         notification claim (notified_at).

user_id is ON DELETE CASCADE (the account's rows go with the account);
decided_by_user_id is SET NULL. No prospect data. The durable audit of every
decision is in compliance_audit_log, which this migration does not touch.

Create-only: nothing existing is altered.

DOWNGRADE drops the table: the per-day approval state is lost (so automatic
sends would need the code that reads it removed too); the audit rows in
compliance_audit_log remain.

Revision ID: 0081_daily_send_approval
Revises: 0080_champion_tracker
"""

import sqlalchemy as sa
from alembic import op

revision = "0081_daily_send_approval"
down_revision = "0080_champion_tracker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_send_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("channels_json", sa.JSON(), nullable=True),
        sa.Column("linkedin_risk_acknowledged", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("linkedin_warning_version", sa.String(40), nullable=True),
        sa.Column("queued_counts_json", sa.JSON(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "local_date",
                            name="uq_daily_send_approval_user_date"),
    )
    op.create_index("ix_daily_send_approvals_user_id", "daily_send_approvals", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_daily_send_approvals_user_id", table_name="daily_send_approvals")
    op.drop_table("daily_send_approvals")
