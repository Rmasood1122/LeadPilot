"""F02 Signal Radar ("why now").

CREATES
  lead_signals   one dated event per lead (funding, hiring, launch, news, the
                 lead's own post) with its source link, observed/expiry dates
                 and a source confidence -- derived only from data the system
                 already stores (no new vendor). See
                 docs/features/f02-signal-radar.md.

WHY lead_id IS CASCADE (and not SET NULL like consent_events). A signal is
derived personal data about the prospect (a post excerpt, a headline about
their company). It has no reason to outlive the lead: when the lead row goes,
so do its signals. The GDPR delete route, which tombstones rather than deletes
the lead, deletes these rows explicitly.

DOWNGRADE drops the table. That is lossy by design and safe: every row is
re-derivable from leads.company_news_json / linkedin_posts_json /
enrichment_json and strategies.market_signals_json, which this revision does
not touch -- the next send or POST /leads/{id}/signals/refresh rebuilds them.

Revision ID: 0074_signal_radar
Revises: 0073_waterfall_enrichment
"""

import sqlalchemy as sa
from alembic import op

revision = "0074_signal_radar"
down_revision = "0073_waterfall_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("signal_type", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_lead_signals"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_lead_signals_user_id_users"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_lead_signals_lead_id_leads"),
        # Also the index for the only per-lead read ("WHERE lead_id = ?").
        sa.UniqueConstraint("lead_id", "dedupe_key", name="uq_lead_signals_lead_dedupe"),
    )
    op.create_index("ix_lead_signals_user_id", "lead_signals", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_lead_signals_user_id", table_name="lead_signals")
    op.drop_table("lead_signals")
