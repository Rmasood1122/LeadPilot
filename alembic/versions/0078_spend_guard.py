"""F07 Spend Guard + Cost Forecast: monthly caps, alerts, forecasts.

CREATES
  spend_caps       an account's own monthly spending ceiling + alert preference
                   (one row per account: unique index on user_id)
  spend_alerts     one row per fired 50/80/100% alert; UNIQUE (user_id,
                   period, threshold) is the "once per threshold per month"
                   guarantee
  spend_forecasts  the cost forecast taken before each strategy / lead-sourcing
                   / Quickstart run, allowed or refused

No personal data. Every table is owned by user_id (ON DELETE CASCADE);
spend_forecasts.strategy_id is CASCADE like every strategy-owned row and
batch_id is SET NULL.

Create-only: nothing existing is altered. F07's data-credit meter writes into
F01's enrichment_attempts using its existing columns (step = "spend_guard").

DOWNGRADE drops the three tables: caps, alert history and forecast history are
lost. Nothing else is touched.

Revision ID: 0078_spend_guard
Revises: 0077_reply_copilot
"""

import sqlalchemy as sa
from alembic import op

revision = "0078_spend_guard"
down_revision = "0077_reply_copilot"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "spend_caps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("monthly_cap_micros", sa.BigInteger(), nullable=True),
        sa.Column("email_alerts", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_spend_caps_user_id", "spend_caps", ["user_id"], unique=True)

    op.create_table(
        "spend_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("cap_micros", sa.BigInteger(), nullable=False),
        sa.Column("spent_micros", sa.BigInteger(), nullable=False),
        sa.Column("email_status", sa.String(20), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "period", "threshold",
                            name="uq_spend_alert_user_period_threshold"),
    )
    op.create_index("ix_spend_alerts_user_id", "spend_alerts", ["user_id"])

    op.create_table(
        "spend_forecasts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("strategy_id", sa.Uuid(),
                  sa.ForeignKey("strategies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("batch_id", sa.Uuid(),
                  sa.ForeignKey("lead_batches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_leads", sa.Integer(), nullable=True),
        sa.Column("ai_purposes", sa.JSON(), nullable=False),
        sa.Column("ai_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("ai_output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("ai_micros", sa.BigInteger(), nullable=False),
        sa.Column("data_units_json", sa.JSON(), nullable=False),
        sa.Column("data_micros", sa.BigInteger(), nullable=False),
        sa.Column("total_micros", sa.BigInteger(), nullable=False),
        sa.Column("month_spent_micros", sa.BigInteger(), nullable=False),
        sa.Column("cap_micros", sa.BigInteger(), nullable=True),
        sa.Column("detail_json", sa.JSON(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_spend_forecasts_user_created", "spend_forecasts",
                    ["user_id", "created_at"])
    op.create_index("ix_spend_forecasts_strategy_id", "spend_forecasts", ["strategy_id"])
    op.create_index("ix_spend_forecasts_batch_id", "spend_forecasts", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_spend_forecasts_batch_id", table_name="spend_forecasts")
    op.drop_index("ix_spend_forecasts_strategy_id", table_name="spend_forecasts")
    op.drop_index("ix_spend_forecasts_user_created", table_name="spend_forecasts")
    op.drop_table("spend_forecasts")
    op.drop_index("ix_spend_alerts_user_id", table_name="spend_alerts")
    op.drop_table("spend_alerts")
    op.drop_index("ix_spend_caps_user_id", table_name="spend_caps")
    op.drop_table("spend_caps")
