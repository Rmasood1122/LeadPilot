"""Unified cross-channel inbox (Part 1, Feature 6).

ALTERS
  inbound_replies  handled_at, handled_by_user_id

WHY "HANDLED" IS PER REPLY AND NOT PER PROSPECT. The inbox is threaded by
prospect, but "does this thread still need me?" is decided by the newest
INBOUND message: a prospect who replies twice in a week has one thread and two
things to answer, and a per-prospect flag would let the second reply be cleared
by a decision made about the first.

WHY A FLAG AT ALL, rather than deriving it. "The latest inbound is newer than
the latest outbound" is a good default and it is what an unhandled reply looks
like -- but it cannot represent the two cases that matter most: a reply
answered OUTSIDE LeadPilot (picked up the phone, replied from Gmail directly),
and a reply that needs no answer. Both are "done" and neither produces an
outbound row here. Without this column the inbox would keep showing them
forever, and an inbox that lies about what is outstanding stops being opened.

Both nullable: every reply stored before this revision is simply unhandled,
which is what it was.

Revision ID: 0058_inbox_handling
Revises: 0057_send_reviews
"""

import sqlalchemy as sa
from alembic import op

revision = "0058_inbox_handling"
down_revision = "0057_send_reviews"
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handled_by_user_id", sa.Uuid(), nullable=True),
    ]


def upgrade() -> None:
    # batch_alter_table, not a bare add_column + create_foreign_key: SQLite
    # cannot add a foreign key to an existing table with ALTER, and the test
    # suite runs on SQLite. Batch mode recreates the table there and emits
    # ordinary ALTERs on PostgreSQL, so one spelling works on both.
    # batch_alter_table, not a bare add_column + create_foreign_key: SQLite
    # cannot ALTER a table to add a foreign key, and the test suite runs on
    # SQLite. Batch mode recreates the table there and emits ordinary ALTERs
    # on PostgreSQL, so one spelling is correct on both.
    #
    # TWO batches, not one: batch mode builds the new table from the schema it
    # reflected when the block opened, so a foreign key declared in the same
    # block as the column it references is emitted against a copy that does
    # not have that column yet.
    with op.batch_alter_table("inbound_replies") as batch:
        for column in _columns():
            batch.add_column(column)
    with op.batch_alter_table("inbound_replies") as batch:
        batch.create_foreign_key("fk_inbound_replies_handled_by_user_id_users",
                                 "users", ["handled_by_user_id"], ["id"],
                                 ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("inbound_replies") as batch:
        batch.drop_constraint("fk_inbound_replies_handled_by_user_id_users",
                              type_="foreignkey")
        for column in reversed(_columns()):
            batch.drop_column(column.name)
