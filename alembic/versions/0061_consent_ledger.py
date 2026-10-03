"""Compliance and consent layer (Part 1, Feature 9).

CREATES
  consent_events   an append-only record of every time consent changed: it was
                   granted, it was withdrawn, an identifier was suppressed, or
                   personal data was erased -- with the region, the regime that
                   applied, where the instruction came from, and who acted.

WHY THIS IS NOT compliance_audit_log (FG9). That table answers "on what basis
did you SEND this message?" -- one row per send decision. This one answers a
different question, the one a regulator or a prospect actually asks: "when did
they tell you to stop, and what did you do about it?" Those have different
lifetimes (a consent withdrawal outlives every message), different retention
needs, and different cardinality (one per instruction, not one per send).

WHY lead_id IS SET NULL AND NOT CASCADE. The whole point of the erasure event
is that it survives the erasure. A consent ledger that deletes itself when the
prospect record goes cannot prove the request was honoured -- which is the one
moment the ledger exists for. `identifier` (the address or profile the
instruction covers) is stored on the row for the same reason: after the lead is
gone, the suppression still has to be matchable.

Revision ID: 0061_consent_ledger
Revises: 0060_attribution_ledger
"""

import sqlalchemy as sa
from alembic import op

revision = "0061_consent_ledger"
down_revision = "0060_attribution_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consent_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("identifier", sa.String(length=320), nullable=True),
        sa.Column("region", sa.String(length=10), nullable=True),
        sa.Column("regime", sa.String(length=40), nullable=True),
        sa.Column("basis", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("detail", sa.String(length=300), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_consent_events"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL",
                                name="fk_consent_events_lead_id_leads"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_consent_events_user_id_users"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_consent_events_actor_user_id_users"),
    )
    op.create_index("ix_consent_events_lead_id", "consent_events", ["lead_id"])
    op.create_index("ix_consent_events_user_id", "consent_events", ["user_id"])
    op.create_index("ix_consent_events_identifier", "consent_events", ["identifier"])
    # Composite, not a bare ts index: every read of this table is
    # "WHERE user_id = ? ORDER BY ts DESC", which a (user_id, ts) index
    # satisfies on its own.
    op.create_index("ix_consent_events_user_ts", "consent_events", ["user_id", "ts"])


def downgrade() -> None:
    op.drop_index("ix_consent_events_user_ts", table_name="consent_events")
    op.drop_index("ix_consent_events_identifier", table_name="consent_events")
    op.drop_index("ix_consent_events_user_id", table_name="consent_events")
    op.drop_index("ix_consent_events_lead_id", table_name="consent_events")
    op.drop_table("consent_events")
