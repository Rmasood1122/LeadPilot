"""Feature Group 8 — workspaces, roles, manager approval, white label.

CREATES
  workspaces             one per owner; white-label branding + custom domain
  workspace_members      (workspace, user, role) -- owner | manager | sdr | viewer
  workspace_invitations  hashed, expiring email invitations

ALTERS (all nullable -- existing sequences read as "never needed approval")
  sequences  approval_requested_by_user_id, approval_requested_at,
             approved_by_user_id, approved_at, approval_note, approval_payload_json

SequenceStatus gains "pending_approval"; the column is VARCHAR(32).

No data migration: a user's workspace is created the first time they touch
anything workspace-related (app/services/workspaces.py::personal_workspace),
so existing accounts keep working unchanged and never see an empty team.

Revision ID: 0030_workspaces
Revises: 0029_crm_ecosystem
"""

import sqlalchemy as sa
from alembic import op

revision = "0030_workspaces"
down_revision = "0029_crm_ecosystem"
branch_labels = None
depends_on = None

_SEQUENCE_COLUMNS = [
    ("approval_requested_at", sa.DateTime(timezone=True)),
    ("approved_at", sa.DateTime(timezone=True)),
    ("approval_note", sa.Text()),
    ("approval_payload_json", sa.JSON()),
]


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("white_label_enabled", sa.Boolean(), server_default=sa.false(),
                  nullable=False),
        sa.Column("brand_name", sa.String(length=100), nullable=True),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("primary_color", sa.String(length=7), nullable=True),
        sa.Column("support_email", sa.String(length=320), nullable=True),
        sa.Column("custom_domain", sa.String(length=253), nullable=True),
        sa.Column("domain_verification_token", sa.String(length=64), nullable=True),
        sa.Column("domain_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workspaces"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_workspaces_owner_user_id_users"),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=True)
    op.create_index("ix_workspaces_owner_user_id", "workspaces", ["owner_user_id"], unique=True)
    op.create_index("ix_workspaces_custom_domain", "workspaces", ["custom_domain"], unique=True)

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workspace_members"),
        sa.UniqueConstraint("workspace_id", "user_id", name="workspace_member"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE",
                                name="fk_workspace_members_workspace_id_workspaces"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_workspace_members_user_id_users"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_workspace_members_invited_by_user_id_users"),
    )
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])

    op.create_table(
        "workspace_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workspace_invitations"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE",
                                name="fk_workspace_invitations_workspace_id_workspaces"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_workspace_invitations_invited_by_user_id_users"),
    )
    op.create_index("ix_workspace_invitations_workspace_id", "workspace_invitations",
                    ["workspace_id"])
    op.create_index("ix_workspace_invitations_email", "workspace_invitations", ["email"])
    op.create_index("ix_workspace_invitations_token_hash", "workspace_invitations",
                    ["token_hash"], unique=True)

    # Foreign-key columns on an existing table: batch mode, so SQLite (the
    # test database) can do it too -- same approach as 0026.
    with op.batch_alter_table("sequences") as batch:
        batch.add_column(sa.Column("approval_requested_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("approved_by_user_id", sa.Uuid(), nullable=True))
        for name, type_ in _SEQUENCE_COLUMNS:
            batch.add_column(sa.Column(name, type_, nullable=True))
        batch.create_foreign_key("fk_sequences_approval_requested_by_user_id_users", "users",
                                 ["approval_requested_by_user_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_sequences_approved_by_user_id_users", "users",
                                 ["approved_by_user_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("sequences") as batch:
        batch.drop_constraint("fk_sequences_approved_by_user_id_users", type_="foreignkey")
        batch.drop_constraint("fk_sequences_approval_requested_by_user_id_users",
                              type_="foreignkey")
        for name, _ in reversed(_SEQUENCE_COLUMNS):
            batch.drop_column(name)
        batch.drop_column("approved_by_user_id")
        batch.drop_column("approval_requested_by_user_id")
    op.drop_table("workspace_invitations")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
