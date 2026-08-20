"""Combined-build repairs: ICP dimension columns, system-level outcomes,
promotion idempotency.

Revision ID: 0012_build_repairs
Revises: 0011_m8c5
Create Date: 2026-08-16

Live smoke-testing the nightly learning loop against a real PostgreSQL 16
instance surfaced three schema gaps in the delivered M8-C4/C5 code paths.
Fixed here as a NEW migration (never editing applied ones):

  1. strategies.icp_industry + icp_company_size_bucket — the C4 send-time
     optimizer groups reply rates by (channel, industry, size, weekday, hour)
     but the columns were never created. Nullable: populated by the Phase 2
     ICP step going forward; NULL rows aggregate under a generic bucket.

  2. outcomes.lead_id → nullable — outcomes is also the audit log for
     system-level events (ab_promoted, circuit_opened) which have a
     strategy but no lead. The M1 NOT NULL made every such insert fail.
     Lead-scoped events still always carry lead_id (application invariant).

  3. Partial unique index on outcomes(strategy_id) WHERE event='ab_promoted'
     — gives auto_promote_winners' ON CONFLICT DO NOTHING an actual
     constraint to conflict against, making promotion idempotent at the
     database level rather than only via the pre-check count.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_build_repairs"
down_revision = "0011_m8c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. ICP dimensions consumed by the C4 send-time optimizer
    op.add_column("strategies", sa.Column("icp_industry", sa.String(120), nullable=True))
    op.add_column("strategies", sa.Column("icp_company_size_bucket", sa.String(40), nullable=True))
    op.create_index(op.f("ix_strategies_icp_industry"), "strategies", ["icp_industry"])

    # 2. Allow system-level (lead-less) outcome events
    op.alter_column("outcomes", "lead_id", existing_type=sa.Uuid(), nullable=True)

    # 3. DB-level idempotency for A/B auto-promotion
    op.execute(
        "CREATE UNIQUE INDEX uq_outcomes_ab_promoted "
        "ON outcomes (strategy_id) WHERE event = 'ab_promoted'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_outcomes_ab_promoted")
    # NOTE: rows with NULL lead_id must be removed before this can succeed.
    op.execute("DELETE FROM outcomes WHERE lead_id IS NULL")
    op.alter_column("outcomes", "lead_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index(op.f("ix_strategies_icp_industry"), table_name="strategies")
    op.drop_column("strategies", "icp_company_size_bucket")
    op.drop_column("strategies", "icp_industry")
