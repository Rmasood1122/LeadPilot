"""Annual billing + F04 stop-attribution setting (docs/features/annual-billing.md).

CREATES
  billing_renewal_notices  one row per auto-renewal notice to an account
                           owner (acknowledgment | trial_end | renewal);
                           UNIQUE (subscription_id, kind, period_key) is the
                           idempotency key the sweep claims before it sends

ADDS (nullable or with a server default)
  billing_subscriptions.trial_started_at     when the current trial began
  billing_subscriptions.trial_used           the account has had a trial
                                             (BACKFILLED true where
                                             trial_ends_at is set -- the old
                                             "had a trial" test)
  billing_subscriptions.renewal_consent_at, consent_disclosure_version,
    consent_price_cents, consent_interval, consent_checkout_session_id
                                             affirmative auto-renewal consent,
                                             recorded when checkout completes
  billing_subscriptions.price_unit_amount_cents, price_interval,
    price_currency                           what Stripe actually bills
  billing_subscriptions.support_note         something a person must resolve
  reply_copilot_settings.answer_earlier_replies  F04 per-account setting,
                           server default TRUE = the behaviour before it existed

billing_subscriptions.billing_model stays String(20); the new value "annual"
fits. Types work on SQLite (tests) and PostgreSQL.

DOWNGRADE drops the table and the added columns: the notice log, consent
records, stored Stripe prices, support notes and trial starts are lost, and
every F04 account falls back to the default (answer earlier replies). Rows with billing_model = 'annual' are NOT
touched -- code from before this revision does not know that model and would
treat the account as free, so do not downgrade while an annual subscription
exists.

Revision ID: 0082_annual_billing
Revises: 0081_daily_send_approval
"""

import sqlalchemy as sa
from alembic import op

revision = "0082_annual_billing"
down_revision = "0081_daily_send_approval"
branch_labels = None
depends_on = None


_SUBSCRIPTION_COLUMNS = (
    ("renewal_consent_at", sa.DateTime(timezone=True)),
    ("consent_disclosure_version", sa.String(length=40)),
    ("consent_price_cents", sa.Integer()),
    ("consent_interval", sa.String(length=10)),
    ("consent_checkout_session_id", sa.String(length=128)),
    ("price_unit_amount_cents", sa.Integer()),
    ("price_interval", sa.String(length=10)),
    ("price_currency", sa.String(length=3)),
    ("support_note", sa.String(length=500)),
)


def upgrade() -> None:
    op.add_column("billing_subscriptions",
                  sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_subscriptions",
                  sa.Column("trial_used", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    op.execute("UPDATE billing_subscriptions SET trial_used = "
               + ("true" if op.get_bind().dialect.name == "postgresql" else "1")
               + " WHERE trial_ends_at IS NOT NULL")
    for name, column_type in _SUBSCRIPTION_COLUMNS:
        op.add_column("billing_subscriptions", sa.Column(name, column_type, nullable=True))
    op.add_column("reply_copilot_settings",
                  sa.Column("answer_earlier_replies", sa.Boolean(), nullable=False,
                            server_default=sa.true()))
    op.create_table(
        "billing_renewal_notices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("period_key", sa.String(length=120), nullable=False),
        sa.Column("charge_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("days_before", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'sending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_billing_renewal_notices"),
        sa.UniqueConstraint("subscription_id", "kind", "period_key",
                            name="uq_billing_renewal_notice"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_billing_renewal_notices_user_id_users"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["billing_subscriptions.id"], ondelete="CASCADE",
            name="fk_billing_renewal_notices_subscription_id"),  # <= 63 chars (PG)
    )
    op.create_index("ix_billing_renewal_notices_user_id", "billing_renewal_notices",
                    ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_renewal_notices_user_id", table_name="billing_renewal_notices")
    op.drop_table("billing_renewal_notices")
    op.drop_column("reply_copilot_settings", "answer_earlier_replies")
    for name, _ in reversed(_SUBSCRIPTION_COLUMNS):
        op.drop_column("billing_subscriptions", name)
    op.drop_column("billing_subscriptions", "trial_used")
    op.drop_column("billing_subscriptions", "trial_started_at")
