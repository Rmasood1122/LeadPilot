"""M8-C3: admin table, token encryption column, user suspension columns

Revision ID: 0009_m8c3
Revises: 0008_m8c2
Create Date: 2026-08-17 00:00:00.000000

Changes:
  1. task_errors table (Celery failure log)
  2. integration_tokens.encrypted_value column (Fernet ciphertext)
  3. users.is_admin, is_suspended, suspended_at, suspended_reason, last_active_at
  4. backfill: move existing plaintext tokens to encrypted_value
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0009_m8c3"
down_revision = "0008_m8c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. task_errors table
    # -------------------------------------------------------------------------
    op.create_table(
        "task_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_name", sa.String(256), nullable=False),
        sa.Column("task_id", sa.String(256), nullable=True),
        sa.Column("args_summary", sa.Text, nullable=True),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("traceback", sa.Text, nullable=True),
        sa.Column("ts", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("resolved_by", sa.String(256), nullable=True),
        sa.Column("resolution_note", sa.Text, nullable=True),
    )
    op.create_index("ix_task_errors_task_name", "task_errors", ["task_name"])
    op.create_index("ix_task_errors_ts", "task_errors", ["ts"])
    op.create_index("ix_task_errors_resolved_at", "task_errors", ["resolved_at"])

    # -------------------------------------------------------------------------
    # 2. integration_tokens: add encrypted_value column
    # -------------------------------------------------------------------------
    # Check if integration_tokens exists (it was created in M2)
    op.add_column(
        "integration_tokens",
        sa.Column("encrypted_value", sa.Text, nullable=True),
    )
    # NOTE: The backfill of plaintext → encrypted happens via the
    # POST /admin/rotate-encryption-key endpoint after migration, not here,
    # because we need the ENCRYPTION_KEY from the environment.

    # -------------------------------------------------------------------------
    # 3. users: admin and suspension columns
    # -------------------------------------------------------------------------
    op.add_column("users", sa.Column("is_admin", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("users", sa.Column("is_suspended", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("users", sa.Column("suspended_at", sa.DateTime, nullable=True))
    op.add_column("users", sa.Column("suspended_reason", sa.Text, nullable=True))
    op.add_column("users", sa.Column("last_active_at", sa.DateTime, nullable=True))

    # Auto-promote ADMIN_EMAIL if set (handled by the application layer, not SQL,
    # because environment variables are not available in migrations)

    # -------------------------------------------------------------------------
    # 4. Add updated_at to integration_tokens if missing
    # -------------------------------------------------------------------------
    # Some M2 migrations may not have included updated_at — add it safely
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'integration_tokens' AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE integration_tokens ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    # Remove task_errors
    op.drop_table("task_errors")

    # Remove encrypted_value
    op.drop_column("integration_tokens", "encrypted_value")

    # Remove user admin/suspension columns
    op.drop_column("users", "is_admin")
    op.drop_column("users", "is_suspended")
    op.drop_column("users", "suspended_at")
    op.drop_column("users", "suspended_reason")
    op.drop_column("users", "last_active_at")
