"""Feature Group 1 — AI intelligence layer.

ADDS
  strategies                 market_signals_json, market_signals_fetched_at,
                             consensus_status, last_mutation_at
  leads                      ai_booking_likelihood (indexed), ai_score_reason,
                             ai_score_factors, ai_scored_at
  strategy_model_outputs     both models' raw answers per consensus step
  strategy_uncertain_zones   sections where Claude and GPT-4o disagreed
  strategy_versions          original snapshot + proposed/applied mutations

Every added column is NULLABLE with no default, so the ALTERs are metadata-only
on PostgreSQL (no table rewrite) and existing rows read as "never scored",
"never fetched", "consensus never ran" -- which is the truth for them.

WHY leads.ai_booking_likelihood IS INDEXED
The leads list sorts by it by default (highest likelihood first). Without the
index that is a sort over every lead of the strategy on every page load.

DOWNGRADE drops the three tables and the eight columns. Scores, signals,
zones and every mutation proposal are destroyed.

Revision ID: 0024_ai_intelligence
Revises: 0023_meeting_prep
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_ai_intelligence"
down_revision = "0023_meeting_prep"
branch_labels = None
depends_on = None

_PIPELINE = sa.Enum("strategy", "gtm", name="pipelinekind", native_enum=False, length=32)


def upgrade() -> None:
    # ---- strategies ----------------------------------------------------------
    op.add_column("strategies", sa.Column("market_signals_json", sa.JSON(), nullable=True))
    op.add_column("strategies", sa.Column("market_signals_fetched_at",
                                          sa.DateTime(timezone=True), nullable=True))
    op.add_column("strategies", sa.Column("consensus_status", sa.String(length=20),
                                          nullable=True))
    op.add_column("strategies", sa.Column("last_mutation_at",
                                          sa.DateTime(timezone=True), nullable=True))

    # ---- leads -----------------------------------------------------------------
    op.add_column("leads", sa.Column("ai_booking_likelihood", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("ai_score_reason", sa.String(length=500), nullable=True))
    op.add_column("leads", sa.Column("ai_score_factors", sa.JSON(), nullable=True))
    op.add_column("leads", sa.Column("ai_scored_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_leads_ai_booking_likelihood", "leads", ["ai_booking_likelihood"])

    # ---- strategy_model_outputs ------------------------------------------------
    op.create_table(
        "strategy_model_outputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline", _PIPELINE, nullable=False),
        sa.Column("phase", sa.Integer(), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_strategy_model_outputs"),
        sa.UniqueConstraint("strategy_id", "pipeline", "step_no", "provider",
                            name="strategy_model_output_step_provider"),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="CASCADE",
            name="fk_strategy_model_outputs_strategy_id_strategies"),
    )
    op.create_index("ix_strategy_model_outputs_strategy_id",
                    "strategy_model_outputs", ["strategy_id"])

    # ---- strategy_uncertain_zones ---------------------------------------------
    op.create_table(
        "strategy_uncertain_zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline", _PIPELINE, nullable=False),
        sa.Column("phase", sa.Integer(), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("section_title", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=False),
        sa.Column("claude_position", sa.Text(), nullable=False),
        sa.Column("gpt_position", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_strategy_uncertain_zones"),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="CASCADE",
            name="fk_strategy_uncertain_zones_strategy_id_strategies"),
    )
    op.create_index("ix_strategy_uncertain_zones_strategy_id",
                    "strategy_uncertain_zones", ["strategy_id"])
    op.create_index("ix_strategy_uncertain_zones_step", "strategy_uncertain_zones",
                    ["strategy_id", "pipeline", "step_no"])

    # ---- strategy_versions -----------------------------------------------------
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column("document", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("changes_json", sa.JSON(), nullable=True),
        sa.Column("outcome_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("trigger", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="proposed",
                  nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_strategy_versions"),
        sa.UniqueConstraint("strategy_id", "version_no", name="strategy_version_no"),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="CASCADE",
            name="fk_strategy_versions_strategy_id_strategies"),
        sa.ForeignKeyConstraint(
            ["parent_version_id"], ["strategy_versions.id"], ondelete="SET NULL",
            name="fk_strategy_versions_parent_version_id_strategy_versions"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL",
            name="fk_strategy_versions_created_by_user_id_users"),
    )
    op.create_index("ix_strategy_versions_strategy_id", "strategy_versions",
                    ["strategy_id"])


def downgrade() -> None:
    op.drop_table("strategy_versions")
    op.drop_table("strategy_uncertain_zones")
    op.drop_table("strategy_model_outputs")
    op.drop_index("ix_leads_ai_booking_likelihood", table_name="leads")
    with op.batch_alter_table("leads") as batch:
        for name in ("ai_scored_at", "ai_score_factors", "ai_score_reason",
                     "ai_booking_likelihood"):
            batch.drop_column(name)
    with op.batch_alter_table("strategies") as batch:
        for name in ("last_mutation_at", "consensus_status",
                     "market_signals_fetched_at", "market_signals_json"):
            batch.drop_column(name)
