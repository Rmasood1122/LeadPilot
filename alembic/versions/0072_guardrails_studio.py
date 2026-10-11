"""F05 Guardrails Studio: per-account exclusion lists + per-product library.

CREATES
  guardrail_exclusions  domains / companies / contacts one ACCOUNT must never
                        pitch (manual, CSV, CRM sync). Normalised value, UNIQUE
                        per (user_id, kind, value) -- the send-time lookup
                        index. Soft-deleted (removed_at) so the read-only audit
                        query can tell whether an exclusion was active at the
                        moment of a send.
  guardrail_library     approved claims about us + forbidden phrases, per
                        product (product_id NULL = every product).

Create-only; touches no existing table. Both tables are owned by users.id
(CASCADE), so deleting an account deletes its lists.

DOWNGRADE drops both tables. That is LOSSY: the exclusion lists and the
library are gone. Export them first (GET /guardrails/exclusions, or the GDPR
account export, which includes both tables).

Revision ID: 0072_guardrails_studio
Revises: 0071_webhook_schema_sync
"""

import sqlalchemy as sa

from alembic import op

revision = "0072_guardrails_studio"
down_revision = "0071_webhook_schema_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guardrail_exclusions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("value", sa.String(length=320), nullable=False),
        sa.Column("display_value", sa.String(length=320), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("external_ref", sa.String(length=100), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("active_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_guardrail_exclusions"),
        sa.UniqueConstraint("user_id", "kind", "value", name="uq_guardrail_exclusion"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_guardrail_exclusions_user_id_users"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_guardrail_exclusions_created_by_user_id_users"),
    )
    op.create_index("ix_guardrail_exclusions_user_id", "guardrail_exclusions", ["user_id"])

    op.create_table(
        "guardrail_library",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_guardrail_library"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_guardrail_library_user_id_users"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE",
                                name="fk_guardrail_library_product_id_products"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_guardrail_library_created_by_user_id_users"),
    )
    op.create_index("ix_guardrail_library_user_id", "guardrail_library", ["user_id"])
    op.create_index("ix_guardrail_library_product_id", "guardrail_library", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_guardrail_library_product_id", table_name="guardrail_library")
    op.drop_index("ix_guardrail_library_user_id", table_name="guardrail_library")
    op.drop_table("guardrail_library")
    op.drop_index("ix_guardrail_exclusions_user_id", table_name="guardrail_exclusions")
    op.drop_table("guardrail_exclusions")
