"""mailbox_health.complaint_source: where a mailbox's complaint rate came from (F03).

ADDS one nullable column. Nothing is backfilled and no existing row changes:
NULL means "proxy", which is what every existing row's rate is, and the API
keeps answering "proxy" for it. With the Deliverability Autopilot on, a
refresh writes "postmaster" when the rate is Google Postmaster's real spam
rate and "proxy" otherwise.

Downgrade drops the column; the only information lost is which source each
stored rate came from (the rates themselves stay).

Revision ID: 0075_deliverability_autopilot
Revises: 0074_signal_radar
"""

import sqlalchemy as sa
from alembic import op

revision = "0075_deliverability_autopilot"
down_revision = "0074_signal_radar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mailbox_health",
                  sa.Column("complaint_source", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("mailbox_health", "complaint_source")
