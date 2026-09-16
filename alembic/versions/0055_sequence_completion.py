"""Sequence completion guarantee and its metric (Part 1, Feature 3).

ALTERS
  sequence_enrollments  planned_steps, steps_sent, completed_at, stopped_at,
                        stop_category

WHY planned_steps IS A SNAPSHOT. "Did this prospect receive every step?"
cannot be answered by counting the sequence's steps at read time -- steps are
editable, so adding a step 4 next month would retroactively turn every
completed enrollment into an incomplete one. The count is frozen at
enrollment, which is the plan the prospect was actually enrolled into.

WHY steps_sent IS DENORMALIZED. Counting SENT messages per enrollment is a
second query per row on a metric that runs over a whole campaign, and it
double-counts a step that was re-sent after a transient failure. The counter
is incremented once, on the send that advances the sequence.

WHY stop_category EXISTS BESIDE stop_reason. `stop_reason` is a free string
(`replied_interested`, `crm_closed_won`, `kill_signal:bounced`) written by a
dozen call sites. The metric needs a fixed vocabulary to break down by, and
the completion guarantee needs to know whether a stop was HUMAN-AUTHORISED or
a silent drop. Deriving that from the free string at read time would mean a
new call site could invent a reason nobody notices; deriving it at WRITE time
means an unrecognised reason lands in `other` and is logged as a warning.

steps_sent is NOT NULL with a server default of 0 (a safe backfill: an
enrollment from before this revision reports 0 sent and therefore no
completion, which the metric labels `unknown` rather than counting as a
failure). Everything else is nullable.

Revision ID: 0055_sequence_completion
Revises: 0054_fpta_scoring
"""

import sqlalchemy as sa
from alembic import op

revision = "0055_sequence_completion"
down_revision = "0054_fpta_scoring"
branch_labels = None
depends_on = None

TABLE = "sequence_enrollments"


def _columns() -> list[sa.Column]:
    return [
        sa.Column("planned_steps", sa.Integer(), nullable=True),
        sa.Column("steps_sent", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_category", sa.String(length=30), nullable=True),
    ]


def upgrade() -> None:
    for column in _columns():
        op.add_column(TABLE, column)
    op.create_index("ix_sequence_enrollments_stop_category", TABLE, ["stop_category"])


def downgrade() -> None:
    op.drop_index("ix_sequence_enrollments_stop_category", table_name=TABLE)
    with op.batch_alter_table(TABLE) as batch:
        for column in reversed(_columns()):
            batch.drop_column(column.name)
