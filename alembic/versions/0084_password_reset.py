"""Forgotten-password reset: password_reset_tokens.

CREATES
  password_reset_tokens   one row per emailed reset link; stores sha256(token)
                          only (app/db/models.py PasswordResetToken,
                          app/services/password_reset.py)

ADDS
  users.password_changed_at   when the password was last changed or reset;
                              refresh/access tokens issued before it are
                              refused (app/services/auth_sessions.py
                              _issued_before_password_change). Nullable, no
                              backfill: NULL = no change on record, nothing
                              is refused.

user_id is ON DELETE CASCADE: deleting an account deletes its reset links.
token_hash is a UNIQUE index (lookup is by hash; a duplicate surfaces as an
error, never as a second live link). requested_ip is the requester's address
for the owner's security review.

Only additive: one new table, one nullable column. Types are portable (sa.Uuid,
DateTime(timezone=True), String), so the same file runs on SQLite (offline
migration test) and PostgreSQL.

LOCKING (PostgreSQL): adding a nullable column with no default is a catalog
change, but it still needs ACCESS EXCLUSIVE on users for an instant. Bounded
with lock_timeout = 15s (as 0071/0082): a stuck lock fails the migration and
the old instance keeps serving, instead of every sign-in queueing behind it.

DOWNGRADE drops the column and the table. Outstanding reset links stop
working (they are unknown tokens afterwards) and the record of the last
password change is lost; no password or session is touched.

Revision ID: 0084_password_reset
Revises: 0083_billing_retention
"""

import sqlalchemy as sa
from alembic import op

revision = "0084_password_reset"
down_revision = "0083_billing_retention"
branch_labels = None
depends_on = None


def _bounded_lock_wait() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '15s'")


def upgrade() -> None:
    _bounded_lock_wait()
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True),
                                     nullable=True))
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens",
                    ["user_id"])
    op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens",
                    ["token_hash"], unique=True)


def downgrade() -> None:
    _bounded_lock_wait()
    with op.batch_alter_table("users") as batch:
        batch.drop_column("password_changed_at")
    op.drop_index("ix_password_reset_tokens_token_hash", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
