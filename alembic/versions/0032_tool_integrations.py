"""Tool integrations — AegisAudit, PostIQ, SIGNALFORGE settings.

CREATES
  tool_integration_settings  per-tool key/value config; user_id NULL is a
                             workspace-level (admin) row, otherwise per-user

No existing table changes.

Uniqueness: UNIQUE (user_id, tool_name, config_key) covers per-user rows, but
PostgreSQL treats NULLs as distinct, so it cannot stop two workspace-level
rows for the same key. The partial unique index on (tool_name, config_key)
WHERE user_id IS NULL closes that gap.

Revision ID: 0032_tool_integrations
Revises: 0031_trust_deliverability
"""

import sqlalchemy as sa
from alembic import op

revision = "0032_tool_integrations"
down_revision = "0031_trust_deliverability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_integration_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("config_key", sa.String(length=128), nullable=False),
        sa.Column("config_value", sa.Text(), nullable=True),
        sa.Column("is_encrypted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_tool_integration_settings_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_tool_integration_settings"),
        sa.UniqueConstraint("user_id", "tool_name", "config_key", name="uq_tool_integration"),
    )
    op.create_index("ix_tool_integration_settings_user_id", "tool_integration_settings",
                    ["user_id"])
    op.create_index(
        "uq_tool_integration_workspace", "tool_integration_settings",
        ["tool_name", "config_key"], unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
        sqlite_where=sa.text("user_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_tool_integration_workspace", table_name="tool_integration_settings")
    op.drop_index("ix_tool_integration_settings_user_id", table_name="tool_integration_settings")
    op.drop_table("tool_integration_settings")
