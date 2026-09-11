"""Feature Group 3 — analytics & revenue intelligence.

CREATES
  campaign_costs         costs the user records per campaign (or account-wide)
  api_usage              metered Claude/OpenAI spend, attributed per campaign
  reply_sentiment_weeks  weekly reply-classification roll-up per campaign

ALTERS
  messages    opened_at, open_count        (email open tracking)
  strategies  smart_send_time, send_windows_json, send_windows_computed_at

open_count and smart_send_time are NOT NULL with a server default, so the
ALTER succeeds on a table that already has rows and every existing campaign
keeps today's scheduling (smart send time off).

Revision ID: 0028_revenue_analytics
Revises: 0027_phone_calling
"""

import sqlalchemy as sa
from alembic import op

revision = "0028_revenue_analytics"
down_revision = "0027_phone_calling"
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "campaign_costs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("hours", sa.Float(), nullable=True),
        sa.Column("incurred_on", sa.Date(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_campaign_costs"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_campaign_costs_user_id_users"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE",
                                name="fk_campaign_costs_strategy_id_strategies"),
    )
    op.create_index("ix_campaign_costs_user_id", "campaign_costs", ["user_id"])
    op.create_index("ix_campaign_costs_strategy_id", "campaign_costs", ["strategy_id"])
    op.create_index("ix_campaign_costs_user_incurred", "campaign_costs",
                    ["user_id", "incurred_on"])

    op.create_table(
        "api_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_micros", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_api_usage"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_api_usage_user_id_users"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL",
                                name="fk_api_usage_strategy_id_strategies"),
    )
    op.create_index("ix_api_usage_strategy_ts", "api_usage", ["strategy_id", "ts"])
    op.create_index("ix_api_usage_user_ts", "api_usage", ["user_id", "ts"])

    op.create_table(
        "reply_sentiment_weeks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("interested", sa.Integer(), nullable=False),
        sa.Column("question", sa.Integer(), nullable=False),
        sa.Column("objection", sa.Integer(), nullable=False),
        sa.Column("not_interested", sa.Integer(), nullable=False),
        sa.Column("unsubscribe", sa.Integer(), nullable=False),
        sa.Column("objection_rate", sa.Float(), nullable=True),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_reply_sentiment_weeks"),
        sa.UniqueConstraint("strategy_id", "week_start", name="sentiment_strategy_week"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE",
                                name="fk_reply_sentiment_weeks_strategy_id_strategies"),
    )
    op.create_index("ix_reply_sentiment_weeks_strategy_id", "reply_sentiment_weeks",
                    ["strategy_id"])

    op.add_column("messages", sa.Column("opened_at", sa.DateTime(timezone=True),
                                        nullable=True))
    op.add_column("messages", sa.Column("open_count", sa.Integer(),
                                        server_default=sa.text("0"), nullable=False))
    op.add_column("strategies", sa.Column("smart_send_time", sa.Boolean(),
                                          server_default=sa.false(), nullable=False))
    op.add_column("strategies", sa.Column("send_windows_json", sa.JSON(), nullable=True))
    op.add_column("strategies", sa.Column("send_windows_computed_at",
                                          sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("strategies") as batch:
        batch.drop_column("send_windows_computed_at")
        batch.drop_column("send_windows_json")
        batch.drop_column("smart_send_time")
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("open_count")
        batch.drop_column("opened_at")
    op.drop_table("reply_sentiment_weeks")
    op.drop_table("api_usage")
    op.drop_table("campaign_costs")
