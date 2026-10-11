"""F01 waterfall enrichment: the per-attempt cost ledger.

CREATES
  enrichment_attempts   one row per email finder / verifier attempt made by
                        the waterfall, including cache hits (cost 0)

No personal data: the email DOMAIN only, never the address or the name.
user_id is ON DELETE CASCADE (the account's ledger goes with the account);
lead_id / batch_id are SET NULL (deleting a lead does not erase what was spent
on it); strategy_id is CASCADE like every other strategy-owned row.

Create-only: nothing existing is altered. The verdict and the per-lead
override live in leads.enrichment_json (no column change).

DOWNGRADE drops the table, which loses the ledger. Nothing else is touched.

Revision ID: 0073_waterfall_enrichment
Revises: 0072_guardrails_studio
"""

import sqlalchemy as sa
from alembic import op

revision = "0073_waterfall_enrichment"
down_revision = "0072_guardrails_studio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrichment_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("strategy_id", sa.Uuid(),
                  sa.ForeignKey("strategies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("lead_id", sa.Uuid(),
                  sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("batch_id", sa.Uuid(),
                  sa.ForeignKey("lead_batches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("cost_units", sa.Integer(), nullable=False),
        sa.Column("claimed_status", sa.String(40), nullable=True),
        sa.Column("email_domain", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_enrichment_attempts_user_id", "enrichment_attempts", ["user_id"])
    op.create_index("ix_enrichment_attempts_strategy_id", "enrichment_attempts",
                    ["strategy_id"])
    op.create_index("ix_enrichment_attempts_lead_id", "enrichment_attempts", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_enrichment_attempts_lead_id", table_name="enrichment_attempts")
    op.drop_index("ix_enrichment_attempts_strategy_id", table_name="enrichment_attempts")
    op.drop_index("ix_enrichment_attempts_user_id", table_name="enrichment_attempts")
    op.drop_table("enrichment_attempts")
