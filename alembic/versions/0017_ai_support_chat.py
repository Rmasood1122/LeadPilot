"""AI support chat: chat_sessions, chat_messages, support_tickets.

Feature 3. Three new tables, no change to any existing table, so this
migration cannot affect a single existing query.

WHY chat_session_id ON support_tickets IS "SET NULL" AND NOT "CASCADE"
---------------------------------------------------------------------
Chat history is purged after SUPPORT_CHAT_RETENTION_DAYS (30). A ticket must
outlive that purge: losing the conversation that produced a ticket is
acceptable, losing the ticket is not. CASCADE would delete a month-old open
ticket the moment its conversation aged out -- silently, on a nightly cron,
with no error anywhere.

WHY chat_messages HAS NO updated_at
-----------------------------------
A chat turn is immutable once written. An updated_at column on it would only
ever record that something went wrong.

INDEXES
-------
  chat_sessions.user_id           list "my conversations"
  chat_sessions.last_message_at   the retention purge scans on this
  chat_messages.(session_id, seq) load one conversation IN ORDER
  chat_messages.created_at        the retention purge

MESSAGE ORDER IS A COLUMN, NOT A TIMESTAMP
------------------------------------------
Both turns of one exchange are written inside a single request and can land on
the same created_at, which left a random UUID primary key as the tiebreak -- a
transcript could come back with the answer before the question. It failed
intermittently, which is how an ordering bug reaches production. `seq` makes
the order explicit instead of depending on clock resolution.
  support_tickets.user_id         list "my tickets"
  support_tickets.status          the admin queue is "open tickets"

NO BACKFILL
-----------
Nothing to backfill: no rows means no conversations and no tickets, which is
the correct state for every existing user.

DOWNGRADE
---------
Drops all three, discarding chat history and every support ticket. Order
matters -- support_tickets references chat_sessions, so it goes first.

Revision ID: 0017_ai_support_chat
Revises: 0016_tutorial_progress
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_ai_support_chat"
down_revision = "0016_tutorial_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_chat_sessions_user_id_users",
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_sessions"),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index("ix_chat_sessions_last_message_at", "chat_sessions",
                    ["last_message_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        # Position in the conversation. created_at alone is NOT a safe sort:
        # both turns of an exchange are written in one request and can share a
        # timestamp, leaving a random UUID as the tiebreak.
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # Diagnostics — assistant turns only, NULL on user turns.
        sa.Column("reason", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("faq_ids", sa.JSON(), nullable=True),
        # Quoted '0': PostgreSQL casts the string literal to boolean false.
        sa.Column("suggest_ticket", sa.Boolean(), nullable=False,
                  server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"],
                                name="fk_chat_messages_session_id_chat_sessions",
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_messages"),
    )
    # Composite: every read of a conversation is "this session, in order".
    op.create_index("ix_chat_messages_session_id", "chat_messages",
                    ["session_id", "seq"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("chat_session_id", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="open"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_support_tickets_user_id_users",
                                ondelete="CASCADE"),
        # SET NULL, not CASCADE — a ticket must survive the 30-day chat purge.
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"],
                                name="fk_support_tickets_chat_session_id_chat_sessions",
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_support_tickets"),
    )
    op.create_index("ix_support_tickets_user_id", "support_tickets", ["user_id"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])


def downgrade() -> None:
    op.drop_index("ix_support_tickets_status", table_name="support_tickets")
    op.drop_index("ix_support_tickets_user_id", table_name="support_tickets")
    op.drop_table("support_tickets")
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_last_message_at", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
