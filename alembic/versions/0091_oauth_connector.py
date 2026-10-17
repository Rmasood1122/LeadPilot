"""OAuth 2.1 authorization server for the Claude / ChatGPT connector.

Spec: docs/features/mcp-connector.md. Decision: docs/program/DECISIONS.md
CONN-AS (reuse auth_sessions for connector refresh tokens).

CREATES
  oauth_clients               one RFC 7591 dynamic client registration:
                              client_id (unique), name, redirect URIs (JSON,
                              each allowlisted), scope. No owner column --
                              registration is anonymous.
  oauth_authorization_codes   one /oauth/authorize request, pending consent ->
                              approved/denied -> code used. The code is stored
                              as a SHA-256 hash only. user_id (the person who
                              approved) is ON DELETE CASCADE. client_id has no
                              foreign key (an account-owned table may only
                              reference account-owned rows; the client is
                              looked up in code on every use).

ALTERS
  auth_sessions               + oauth_client_id (nullable, indexed) and scope
                              (nullable). NULL on every existing row = a web /
                              app sign-in, unchanged.

LOCKING (PostgreSQL): the two nullable columns with no default are catalog
changes, but still need ACCESS EXCLUSIVE on auth_sessions for an instant (every
refresh writes that table). Bounded with lock_timeout = 15s (as 0071/0082/0084):
a stuck lock fails the migration and the old instance keeps serving.

DOWNGRADE drops both tables and both columns. Every connector session is then
indistinguishable from a web session that no client can refresh (its refresh
token's typ is refused by /auth/refresh), so connected Claude / ChatGPT
clients must reconnect. No web session is touched.

Revision ID: 0091_oauth_connector
Revises: 0090_email_network
"""

import sqlalchemy as sa
from alembic import op

revision = "0091_oauth_connector"
down_revision = "0090_email_network"
branch_labels = None
depends_on = None


def _bounded_lock_wait() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '15s'")


def upgrade() -> None:
    _bounded_lock_wait()
    op.add_column("auth_sessions", sa.Column("oauth_client_id", sa.String(100), nullable=True))
    op.add_column("auth_sessions", sa.Column("scope", sa.String(200), nullable=True))
    op.create_index("ix_auth_sessions_oauth_client_id", "auth_sessions", ["oauth_client_id"])

    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(100), nullable=False),
        sa.Column("client_name", sa.String(200), nullable=True),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        sa.Column("scope", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_clients"),
    )
    op.create_index("ix_oauth_clients_client_id", "oauth_clients", ["client_id"], unique=True)

    op.create_table(
        "oauth_authorization_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(100), nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("scope", sa.String(200), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("state", sa.String(500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("code_hash", sa.String(64), nullable=True),
        sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_family_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_oauth_authorization_codes_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_authorization_codes"),
        sa.UniqueConstraint("code_hash", name="uq_oauth_authorization_codes_code_hash"),
    )
    op.create_index("ix_oauth_authorization_codes_client_id", "oauth_authorization_codes",
                    ["client_id"])
    op.create_index("ix_oauth_authorization_codes_user_id", "oauth_authorization_codes",
                    ["user_id"])


def downgrade() -> None:
    _bounded_lock_wait()
    op.drop_index("ix_oauth_authorization_codes_user_id", table_name="oauth_authorization_codes")
    op.drop_index("ix_oauth_authorization_codes_client_id",
                  table_name="oauth_authorization_codes")
    op.drop_table("oauth_authorization_codes")
    op.drop_index("ix_oauth_clients_client_id", table_name="oauth_clients")
    op.drop_table("oauth_clients")
    op.drop_index("ix_auth_sessions_oauth_client_id", table_name="auth_sessions")
    with op.batch_alter_table("auth_sessions") as batch:
        batch.drop_column("scope")
        batch.drop_column("oauth_client_id")
