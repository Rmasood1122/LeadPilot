"""F06 Quickstart: review-only first drafts while the full pipeline runs.

CREATES
  quickstart_runs    one row per Quickstart request (website URL + one-line
                     offer), its derived ICP, the lead batch it sourced, and
                     the stage timestamps that measure time-to-first-draft.
  quickstart_drafts  one review-only first-touch draft per (run, lead).

NOTHING HERE CAN SEND. Drafts are deliberately NOT `messages` rows: the
dispatcher and the send chokepoint read only `messages`, so a draft has no
route to a prospect. See docs/features/f06-quickstart.md.

Create-only; types work on SQLite (tests) and PostgreSQL (JSON, not JSONB).
DOWNGRADE drops both tables: the Quickstart runs and drafts are lost (they are
review artefacts the verified strategy supersedes). The products, strategies,
lead batches and leads a run created are ordinary rows in their own tables and
are not touched.

Revision ID: 0076_quickstart
Revises: 0075_deliverability_autopilot
"""

import sqlalchemy as sa
from alembic import op

revision = "0076_quickstart"
down_revision = "0075_deliverability_autopilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quickstart_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("lead_batch_id", sa.Uuid(), nullable=True),
        sa.Column("website_url", sa.String(length=2048), nullable=False),
        sa.Column("offer", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'queued'")),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("icp_criteria_json", sa.JSON(), nullable=True),
        sa.Column("website_meta_json", sa.JSON(), nullable=True),
        sa.Column("website_text", sa.Text(), nullable=True),
        sa.Column("lead_target", sa.Integer(), nullable=False),
        sa.Column("budget_micros", sa.BigInteger(), nullable=True),
        sa.Column("detail_json", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("icp_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sourcing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_draft_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_quickstart_runs"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_quickstart_runs_user_id_users"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE",
                                name="fk_quickstart_runs_product_id_products"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE",
                                name="fk_quickstart_runs_strategy_id_strategies"),
        sa.ForeignKeyConstraint(["lead_batch_id"], ["lead_batches.id"], ondelete="SET NULL",
                                name="fk_quickstart_runs_lead_batch_id_lead_batches"),
    )
    op.create_index("ix_quickstart_runs_user_id", "quickstart_runs", ["user_id"])
    op.create_index("ix_quickstart_runs_strategy_id", "quickstart_runs", ["strategy_id"])
    op.create_index("ix_quickstart_runs_status", "quickstart_runs", ["status"])

    op.create_table(
        "quickstart_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'draft'")),
        sa.Column("claims_changed", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_quickstart_drafts"),
        sa.UniqueConstraint("run_id", "lead_id", name="uq_quickstart_draft_run_lead"),
        sa.ForeignKeyConstraint(["run_id"], ["quickstart_runs.id"], ondelete="CASCADE",
                                name="fk_quickstart_drafts_run_id_quickstart_runs"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_quickstart_drafts_user_id_users"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_quickstart_drafts_lead_id_leads"),
    )
    op.create_index("ix_quickstart_drafts_run_id", "quickstart_drafts", ["run_id"])
    op.create_index("ix_quickstart_drafts_user_id", "quickstart_drafts", ["user_id"])
    op.create_index("ix_quickstart_drafts_lead_id", "quickstart_drafts", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_quickstart_drafts_lead_id", table_name="quickstart_drafts")
    op.drop_index("ix_quickstart_drafts_user_id", table_name="quickstart_drafts")
    op.drop_index("ix_quickstart_drafts_run_id", table_name="quickstart_drafts")
    op.drop_table("quickstart_drafts")
    op.drop_index("ix_quickstart_runs_status", table_name="quickstart_runs")
    op.drop_index("ix_quickstart_runs_strategy_id", table_name="quickstart_runs")
    op.drop_index("ix_quickstart_runs_user_id", table_name="quickstart_runs")
    op.drop_table("quickstart_runs")
