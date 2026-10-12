"""Inbound reply threading headers: inbound_replies.rfc_message_id / rfc_references.

ADDS
  inbound_replies.rfc_message_id   VARCHAR(502), nullable -- the email's own
                                   Message-ID (one sanitised msg-id)
  inbound_replies.rfc_references   TEXT, nullable -- its References chain
                                   (sanitised, at most 20 ids)

WHY (gaps-sweep-2 #6). A Reply Copilot answer was sent with Gmail's threadId
only, so it threaded in the sender's Gmail but arrived in the prospect's own
client as a new, unrelated email. RFC 5322 section 3.6.4 threading needs the
parent's Message-ID (In-Reply-To) and References chain; nothing stored them.
The Gmail adapter now captures both (app/services/email_threading.py).

No backfill: replies stored before this migration keep NULL and their answers
go out exactly as before (threadId only). No index (never queried by these
columns). Only additive; types are portable (String, Text), so the same file
runs on SQLite (offline migration test) and PostgreSQL.

LOCKING (PostgreSQL): adding nullable columns with no default is a catalog
change that still takes ACCESS EXCLUSIVE on inbound_replies for an instant.
Bounded with lock_timeout = 15s (as 0084): a stuck lock fails the migration
and the old instance keeps serving.

DOWNGRADE drops both columns. Stored Message-IDs are lost; answers to those
replies then thread by Gmail threadId only (the pre-0086 behaviour).

Revision ID: 0086_inbound_reply_threading
Revises: 0085_webhook_foreign_keys
"""

import sqlalchemy as sa
from alembic import op

revision = "0086_inbound_reply_threading"
down_revision = "0085_webhook_foreign_keys"
branch_labels = None
depends_on = None


def _bounded_lock_wait() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '15s'")


def upgrade() -> None:
    _bounded_lock_wait()
    op.add_column("inbound_replies",
                  sa.Column("rfc_message_id", sa.String(502), nullable=True))
    op.add_column("inbound_replies",
                  sa.Column("rfc_references", sa.Text(), nullable=True))


def downgrade() -> None:
    _bounded_lock_wait()
    with op.batch_alter_table("inbound_replies") as batch:
        batch.drop_column("rfc_references")
        batch.drop_column("rfc_message_id")
