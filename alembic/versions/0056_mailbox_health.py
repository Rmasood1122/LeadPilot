"""Per-mailbox deliverability health (Part 1, Feature 4).

CREATES
  mailbox_health   one row per (user, mailbox). The mailbox is identified by
                   `mailbox_ref`, which is EXACTLY the value the send path
                   writes to messages.sender_ref -- a Gmail account id, a
                   "linkedin:<id>", a "whatsapp:<phone id>". That is what makes
                   volume and complaints countable per mailbox rather than per
                   user, and it is why the column is a string and not a foreign
                   key: not every sending identity is a row in one table.

WHY A NEW TABLE BESIDE deliverability_checks. `deliverability_checks` (FG9) is
an append-only LOG of domain checks, and the domain is the wrong grain for
this feature: two mailboxes on the same domain can have very different
reputations, and only one of them should be throttled. This table is CURRENT
STATE, one row per mailbox, upserted on each refresh -- the thing the send
gate reads on every send. The domain log stays exactly as it was.

Revision ID: 0056_mailbox_health
Revises: 0055_sequence_completion
"""

import sqlalchemy as sa
from alembic import op

revision = "0056_mailbox_health"
down_revision = "0055_sequence_completion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mailbox_health",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("mailbox_ref", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("address", sa.String(length=320), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False,
                  server_default=sa.text("'healthy'")),
        sa.Column("throttle_cap", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column("reasons_json", sa.JSON(), nullable=True),
        sa.Column("spf_ok", sa.Boolean(), nullable=True),
        sa.Column("dkim_ok", sa.Boolean(), nullable=True),
        sa.Column("dmarc_ok", sa.Boolean(), nullable=True),
        sa.Column("dmarc_policy", sa.String(length=20), nullable=True),
        sa.Column("complaint_rate", sa.Float(), nullable=True),
        sa.Column("bounce_rate", sa.Float(), nullable=True),
        sa.Column("sends_today", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sends_7d", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("daily_cap", sa.Integer(), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_mailbox_health"),
        sa.UniqueConstraint("user_id", "mailbox_ref", name="mailbox_health_ref"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_mailbox_health_user_id_users"),
        sa.ForeignKeyConstraint(["resumed_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_mailbox_health_resumed_by_user_id_users"),
    )
    op.create_index("ix_mailbox_health_user_id", "mailbox_health", ["user_id"])
    op.create_index("ix_mailbox_health_mailbox_ref", "mailbox_health", ["mailbox_ref"])
    op.create_index("ix_mailbox_health_state", "mailbox_health", ["state"])


def downgrade() -> None:
    op.drop_index("ix_mailbox_health_state", table_name="mailbox_health")
    op.drop_index("ix_mailbox_health_mailbox_ref", table_name="mailbox_health")
    op.drop_index("ix_mailbox_health_user_id", table_name="mailbox_health")
    op.drop_table("mailbox_health")
