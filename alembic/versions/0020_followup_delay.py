"""Engagement Hub, Feature 1 — per-step automated follow-up settings.

WHAT THIS ADDS
Two columns on `sequence_steps`, and nothing else:

  followup_enabled      BOOLEAN NOT NULL DEFAULT TRUE
  followup_delay_hours  INTEGER NOT NULL DEFAULT 72

WHY THEY ARE NOT `delay_days`
`sequence_steps.delay_days` already exists and answers a different question:
how long to wait before scheduling the NEXT step once this one has SENT. That
timer starts on a successful send and runs regardless of what the lead does.

These two answer "this step went out and the lead has said nothing — now
what?". The sweep in app/workers/outreach_tasks.py::check_followup_due reads
them per step, in hours rather than days because the useful range for a
follow-up nudge (24h, 48h, 72h) is not expressible in whole days without
rounding the shortest and most common setting into a different product.

WHY BOTH DEFAULTS ARE SERVER-SIDE
`sequence_steps` has rows in every deployed database. Adding a NOT NULL column
to a populated table requires a server default or the ALTER is rejected, and a
nullable column instead would mean the sweep's `now - sent_at >= delay` test
silently compares against NULL for every step that existed before this
migration -- i.e. the feature would appear to work and would never fire for
any existing sequence. The defaults are declared identically on the model
(app/db/models.py::SequenceStep) so create_all and the migration agree; that
equality is asserted by tests/test_engagement_migrations.py.

72 hours is the brief's default and matches the existing `delay_days=3`.

DOWNGRADE
Drops both columns. Follow-up configuration is lost; nothing else is. No data
outside these two columns is derived from them.

Revision ID: 0020_followup_delay
Revises: 0019_m9_crm
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_followup_delay"
down_revision = "0019_m9_crm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sequence_steps",
        sa.Column("followup_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
    )
    op.add_column(
        "sequence_steps",
        sa.Column("followup_delay_hours", sa.Integer(), nullable=False,
                  server_default=sa.text("72")),
    )


def downgrade() -> None:
    op.drop_column("sequence_steps", "followup_delay_hours")
    op.drop_column("sequence_steps", "followup_enabled")
