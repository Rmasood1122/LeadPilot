"""Local business mode + consent-based customer win-back.

Spec: docs/features/local-business-mode.md.

ADDS (all nullable or server-defaulted; no existing row changes meaning):
  products.business_type       VARCHAR(30) NULL  -- NULL = not a local business
  products.healthcare_locked_at TIMESTAMPTZ NULL  -- set when first healthcare,
                                                    never cleared (win-back lock)
  strategies.service_area_json JSON NULL         -- {city, postal_code, country,
                                                    radius, unit, timezone}
  strategies.local_offer       VARCHAR(500) NULL
  sequences.audience           VARCHAR(20) NOT NULL DEFAULT 'prospects'
                               -- every existing sequence is a prospects
                                  (B2B) sequence, which is what it always was

CREATES
  customer_imports   one row per import of a business's own customer list:
                     user_id (FK users, CASCADE), strategy_id (FK strategies,
                     SET NULL), business_type, attestation (+ its version),
                     counts, and the
                     refused lines as {line, reason} only (no personal data).

Constraint/index names follow app/db/base.py NAMING_CONVENTION and are all
well under PostgreSQL's 63-character identifier limit (the longest is
fk_customer_imports_strategy_id_strategies, 42 characters).

DOWNGRADE drops the table and the five columns. Business types, service
areas, offers and sequence audiences are lost -- a customer (win-back)
sequence would become an ordinary prospects sequence -- so switch
customer_winback_enabled off and stop customer sequences BEFORE downgrading.
Imported customer leads and their consent_events rows are not touched.

Revision ID: 0088_local_business
Revises: 0087_autopilot_launch
"""

import sqlalchemy as sa
from alembic import op

revision = "0088_local_business"
down_revision = "0087_autopilot_launch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("business_type", sa.String(30), nullable=True))
    op.add_column("products", sa.Column("healthcare_locked_at", sa.DateTime(timezone=True),
                                        nullable=True))
    op.add_column("strategies", sa.Column("service_area_json", sa.JSON(), nullable=True))
    op.add_column("strategies", sa.Column("local_offer", sa.String(500), nullable=True))
    op.add_column("sequences", sa.Column("audience", sa.String(20), nullable=False,
                                         server_default=sa.text("'prospects'")))
    op.create_table(
        "customer_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("business_type", sa.String(30), nullable=False),
        sa.Column("attestation", sa.Text(), nullable=False),
        sa.Column("attestation_version", sa.String(10), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("rejected_count", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("rejected_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_customer_imports_user_id_users"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL",
                                name="fk_customer_imports_strategy_id_strategies"),
        sa.PrimaryKeyConstraint("id", name="pk_customer_imports"),
    )
    op.create_index("ix_customer_imports_user_id", "customer_imports", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_customer_imports_user_id", table_name="customer_imports")
    op.drop_table("customer_imports")
    op.drop_column("sequences", "audience")
    op.drop_column("strategies", "local_offer")
    op.drop_column("strategies", "service_area_json")
    op.drop_column("products", "healthcare_locked_at")
    op.drop_column("products", "business_type")
