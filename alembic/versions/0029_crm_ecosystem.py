"""Feature Group 4 — CRM & ecosystem.

CREATES
  external_crm_connections  a user's HubSpot / Salesforce connection (non-secret)
  external_crm_links        LeadPilot lead/deal <-> CRM record, unique both ways
  api_keys                  hashed personal API keys (Zapier / Make)

"external_" keeps these apart from M9's native CRM tables (crm_*), which
tests/test_crm_migration.py pins to migration 0019 by prefix.

ALTERS
  webhook_targets     source (NOT NULL, default 'api'), disabled_reason
  webhook_deliveries  last_attempt_at -- written by the M8 delivery code
                      since M8-C5, never created until now

Revision ID: 0029_crm_ecosystem
Revises: 0028_revenue_analytics
"""

import sqlalchemy as sa
from alembic import op

revision = "0029_crm_ecosystem"
down_revision = "0028_revenue_analytics"
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
        "external_crm_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("account_id", sa.String(length=100), nullable=True),
        sa.Column("account_name", sa.String(length=200), nullable=True),
        sa.Column("instance_url", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="connected", nullable=False),
        sa.Column("last_push_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_pull_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_external_crm_connections"),
        sa.UniqueConstraint("user_id", "provider", name="crm_connection_user_provider"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_external_crm_connections_user_id_users"),
    )
    op.create_index("ix_external_crm_connections_user_id", "external_crm_connections",
                    ["user_id"])
    op.create_index("ix_external_crm_connections_provider_account",
                    "external_crm_connections", ["provider", "account_id"])

    op.create_table(
        "external_crm_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("local_type", sa.String(length=10), nullable=False),
        sa.Column("local_id", sa.Uuid(), nullable=False),
        sa.Column("remote_type", sa.String(length=20), nullable=False),
        sa.Column("remote_id", sa.String(length=64), nullable=False),
        sa.Column("last_pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_pulled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remote_updated_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_external_crm_links"),
        sa.UniqueConstraint("user_id", "provider", "local_type", "local_id",
                            name="crm_link_local"),
        sa.UniqueConstraint("user_id", "provider", "remote_type", "remote_id",
                            name="crm_link_remote"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_external_crm_links_user_id_users"),
    )
    op.create_index("ix_external_crm_links_user_id", "external_crm_links", ["user_id"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_api_keys_user_id_users"),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    op.add_column("webhook_targets", sa.Column("source", sa.String(length=20),
                                               server_default="api", nullable=False))
    op.add_column("webhook_targets", sa.Column("disabled_reason", sa.String(length=200),
                                               nullable=True))
    op.add_column("webhook_deliveries", sa.Column("last_attempt_at",
                                                  sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("webhook_deliveries") as batch:
        batch.drop_column("last_attempt_at")
    with op.batch_alter_table("webhook_targets") as batch:
        batch.drop_column("disabled_reason")
        batch.drop_column("source")
    op.drop_table("api_keys")
    op.drop_table("external_crm_links")
    op.drop_table("external_crm_connections")
