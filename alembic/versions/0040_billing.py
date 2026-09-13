"""Billing: monthly subscriptions and pay-per-meeting usage (Section E).

CREATES
  billing_subscriptions  one row per account: which way it pays, mirrored
                         from Stripe
  billable_meetings      one row per prospect a pay-per-meeting account owes
                         for; UNIQUE (user_id, dedupe_key) is "charge once per
                         prospect", enforced by the schema

users.plan GAINS "growth", "scale" and "pay_per_meeting". No DDL: plan is
VARCHAR-backed like every enum here (native_enum=False), so new values are a
data-free change.

Revision ID: 0040_billing
Revises: 0039_identity_verification
"""

import sqlalchemy as sa
from alembic import op

revision = "0040_billing"
down_revision = "0039_identity_verification"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "billing_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("billing_model", sa.String(length=20), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="incomplete",
                  nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=64), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(length=128), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_stub", sa.Boolean(), server_default="0", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_billing_subscriptions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_billing_subscriptions_user_id_users"),
        sa.UniqueConstraint("stripe_subscription_id",
                            name="uq_billing_subscriptions_stripe_subscription_id"),
    )
    op.create_index("ix_billing_subscriptions_user_id", "billing_subscriptions",
                    ["user_id"], unique=True)
    op.create_index("ix_billing_subscriptions_stripe_customer_id", "billing_subscriptions",
                    ["stripe_customer_id"])

    op.create_table(
        "billable_meetings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("outcome_id", sa.Uuid(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="usd", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("charge_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("charged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_invoice_id", sa.String(length=64), nullable=True),
        sa.Column("stripe_invoice_item_id", sa.String(length=64), nullable=True),
        sa.Column("is_stub", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("resolution_note", sa.String(length=500), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_billable_meetings"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_billable_meetings_user_id_users"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL",
                                name="fk_billable_meetings_lead_id_leads"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL",
                                name="fk_billable_meetings_strategy_id_strategies"),
        sa.UniqueConstraint("user_id", "dedupe_key", name="billable_meeting_once"),
    )
    op.create_index("ix_billable_meetings_user_id", "billable_meetings", ["user_id"])
    op.create_index("ix_billable_meetings_status_charge_after", "billable_meetings",
                    ["status", "charge_after"])


def downgrade() -> None:
    op.drop_index("ix_billable_meetings_status_charge_after", table_name="billable_meetings")
    op.drop_index("ix_billable_meetings_user_id", table_name="billable_meetings")
    op.drop_table("billable_meetings")
    op.drop_index("ix_billing_subscriptions_stripe_customer_id",
                  table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_user_id", table_name="billing_subscriptions")
    op.drop_table("billing_subscriptions")
