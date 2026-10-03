"""Founder / agency mode: per-client workspaces (Part 1, Feature 11).

CREATES
  client_workspaces        one CLIENT an agency runs outreach for, under one
                           agency account
  client_sending_domains   which sending domains belong to which client

ALTERS
  strategies  client_workspace_id

WHY NOT REUSE `workspaces`. That table is a TEAM around one owner --
`owner_user_id` is UNIQUE, and its own docstring says "the workspace's data is
its owner's data". An agency's SDRs are shared across every client; the clients
are separate books of business. Conflating the two would mean either giving
every client its own login (and re-inviting the same three SDRs to each) or
breaking the unique constraint that thirteen modules' ownership resolution
rests on. A client is a different object, so it gets a different table, hanging
off the team workspace rather than replacing it.

WHY strategies AND NOT products. In this schema one strategy owns one outreach
campaign (Strategy.campaign_state), and a campaign is the unit an agency
actually runs FOR a client. A product can legitimately be sold to several
clients' markets.

NULLABLE, on purpose: every existing strategy is unassigned, which reads as
"the agency's own work" rather than being force-fitted into a client that does
not exist. An account that never creates a client workspace behaves exactly as
it does today.

Revision ID: 0063_client_workspaces
Revises: 0062_data_provenance
"""

import sqlalchemy as sa
from alembic import op

revision = "0063_client_workspaces"
down_revision = "0062_data_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'active'")),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("billing_email", sa.String(length=320), nullable=True),
        sa.Column("billing_reference", sa.String(length=100), nullable=True),
        sa.Column("monthly_fee_cents", sa.BigInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("per_meeting_fee_cents", sa.BigInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("currency", sa.String(length=3), nullable=False,
                  server_default="USD"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_client_workspaces"),
        sa.UniqueConstraint("workspace_id", "slug", name="client_workspace_slug"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE",
                                name="fk_client_workspaces_workspace_id_workspaces"),
    )
    op.create_index("ix_client_workspaces_workspace_id", "client_workspaces",
                    ["workspace_id"])

    op.create_table(
        "client_sending_domains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_workspace_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_client_sending_domains"),
        sa.UniqueConstraint("client_workspace_id", "domain",
                            name="client_sending_domain_once"),
        sa.ForeignKeyConstraint(["client_workspace_id"], ["client_workspaces.id"],
                                ondelete="CASCADE",
                                name="fk_client_sending_domains_client_workspace_id_client_workspaces"),
    )
    op.create_index("ix_client_sending_domains_client_workspace_id",
                    "client_sending_domains", ["client_workspace_id"])
    op.create_index("ix_client_sending_domains_domain", "client_sending_domains",
                    ["domain"])

    op.add_column("strategies", sa.Column("client_workspace_id", sa.Uuid(), nullable=True))
    op.create_index("ix_strategies_client_workspace_id", "strategies",
                    ["client_workspace_id"])
    with op.batch_alter_table("strategies") as batch:
        batch.create_foreign_key("fk_strategies_client_workspace_id_client_workspaces",
                                 "client_workspaces", ["client_workspace_id"], ["id"],
                                 ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("strategies") as batch:
        batch.drop_constraint("fk_strategies_client_workspace_id_client_workspaces",
                              type_="foreignkey")
    op.drop_index("ix_strategies_client_workspace_id", table_name="strategies")
    with op.batch_alter_table("strategies") as batch:
        batch.drop_column("client_workspace_id")
    op.drop_index("ix_client_sending_domains_domain", table_name="client_sending_domains")
    op.drop_index("ix_client_sending_domains_client_workspace_id",
                  table_name="client_sending_domains")
    op.drop_table("client_sending_domains")
    op.drop_index("ix_client_workspaces_workspace_id", table_name="client_workspaces")
    op.drop_table("client_workspaces")
