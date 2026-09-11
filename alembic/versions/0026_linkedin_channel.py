"""Feature Group 5 — the LinkedIn outreach channel.

CREATES
  linkedin_accounts      a user's Unipile-connected LinkedIn accounts
  linkedin_suppressions  LinkedIn profiles that must never be contacted again

ALTERS (all nullable -- existing rows read as "no LinkedIn activity")
  leads           linkedin_provider_id (indexed), linkedin_is_premium,
                  linkedin_connection_status, linkedin_invited_at,
                  linkedin_connected_at, linkedin_account_id (FK),
                  linkedin_chat_id
  sequence_steps  linkedin_action
  messages        linkedin_action, linkedin_account_id (FK)

The FK columns are added in BATCH mode: SQLite cannot add a named foreign key
to an existing table in place. On PostgreSQL batch mode is a plain ALTER.

WHY A SEPARATE SUPPRESSION TABLE: see the LinkedInSuppression model docstring
(rewriting suppression_list's CHECK in a SQLite batch is how constraints get
silently dropped).

DOWNGRADE drops both tables and every added column. LinkedIn connection
state is lost; the suppression entries are lost -- export them first.

Revision ID: 0026_linkedin_channel
Revises: 0025_personalization
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_linkedin_channel"
down_revision = "0025_personalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linkedin_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("unipile_account_id", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("profile_url", sa.String(length=500), nullable=True),
        sa.Column("has_premium", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("inmail_credits", sa.Integer(), nullable=True),
        sa.Column("inmail_sent_total", sa.Integer(), server_default=sa.text("0"),
                  nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ok", nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_linkedin_accounts"),
        sa.UniqueConstraint("unipile_account_id", name="linkedin_account_unipile_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_linkedin_accounts_user_id_users"),
    )
    op.create_index("ix_linkedin_accounts_user_id", "linkedin_accounts", ["user_id"])

    op.create_table(
        "linkedin_suppressions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_linkedin_suppressions"),
        sa.UniqueConstraint("profile", name="linkedin_suppression_profile"),
    )

    with op.batch_alter_table("leads") as batch:
        batch.add_column(sa.Column("linkedin_provider_id", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("linkedin_is_premium", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("linkedin_connection_status", sa.String(length=20),
                                   nullable=True))
        batch.add_column(sa.Column("linkedin_invited_at", sa.DateTime(timezone=True),
                                   nullable=True))
        batch.add_column(sa.Column("linkedin_connected_at", sa.DateTime(timezone=True),
                                   nullable=True))
        batch.add_column(sa.Column("linkedin_account_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("linkedin_chat_id", sa.String(length=120), nullable=True))
        batch.create_foreign_key("fk_leads_linkedin_account_id_linkedin_accounts",
                                 "linkedin_accounts", ["linkedin_account_id"], ["id"],
                                 ondelete="SET NULL")
        batch.create_index("ix_leads_linkedin_provider_id", ["linkedin_provider_id"])

    with op.batch_alter_table("sequence_steps") as batch:
        batch.add_column(sa.Column("linkedin_action", sa.String(length=20), nullable=True))

    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("linkedin_action", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("linkedin_account_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_messages_linkedin_account_id_linkedin_accounts",
                                 "linkedin_accounts", ["linkedin_account_id"], ["id"],
                                 ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_constraint("fk_messages_linkedin_account_id_linkedin_accounts",
                              type_="foreignkey")
        batch.drop_column("linkedin_account_id")
        batch.drop_column("linkedin_action")
    with op.batch_alter_table("sequence_steps") as batch:
        batch.drop_column("linkedin_action")
    with op.batch_alter_table("leads") as batch:
        batch.drop_index("ix_leads_linkedin_provider_id")
        batch.drop_constraint("fk_leads_linkedin_account_id_linkedin_accounts",
                              type_="foreignkey")
        for name in ("linkedin_chat_id", "linkedin_account_id", "linkedin_connected_at",
                     "linkedin_invited_at", "linkedin_connection_status",
                     "linkedin_is_premium", "linkedin_provider_id"):
            batch.drop_column(name)
    op.drop_table("linkedin_suppressions")
    op.drop_table("linkedin_accounts")
