"""Persistent sign-in sessions and the security audit log.

CREATES
  auth_sessions          one row per refresh token (the JWT's jti). Rotation,
                         logout and refresh-token reuse detection read and
                         write it. See app/services/auth_sessions.py.
  security_audit_events  who did what to an account, and when -- strategy
                         deletions, denied password confirmations, sign-outs,
                         refresh-token reuse. No foreign keys, so a record
                         outlives the row it describes.

No backfill: refresh tokens issued before this revision carry no jti and are
exchanged for a tracked session on first use (AUTH_ACCEPT_LEGACY_REFRESH_TOKENS).

Revision ID: 0052_auth_sessions
Revises: 0051_compliance_rules
"""

import sqlalchemy as sa
from alembic import op

revision = "0052_auth_sessions"
down_revision = "0051_compliance_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("persistent", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=40), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_auth_sessions_user_id_users"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_family_id", "auth_sessions", ["family_id"])

    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_security_audit_events"),
    )
    op.create_index("ix_security_audit_events_user_created", "security_audit_events",
                    ["user_id", "created_at"])
    op.create_index("ix_security_audit_events_target", "security_audit_events",
                    ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_security_audit_events_target", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_user_created", table_name="security_audit_events")
    op.drop_table("security_audit_events")
    op.drop_index("ix_auth_sessions_family_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
