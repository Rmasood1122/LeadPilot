"""Tamper-evident send/reply audit trail (Feature A2).

CREATES
  activity_audit_events  append-only, hash-chained per account: every send,
                         open, click, reply and meeting-booked event

UNIQUE (user_id, seq_no) is what makes a sealed chain linear: two records can
never claim the same position. UNIQUE (outcome_ref) makes recording
idempotent: one Outcome row is one audit record, however often it is flushed.

POSTGRESQL ONLY: a BEFORE UPDATE OR DELETE trigger refuses any DELETE, any
change to a record's content, and any change to a record's chain fields once it
has been sealed. Sealing itself (NULL -> value, exactly once) is the only
permitted update. SQLite (the unit-test database) has no plpgsql; there the ORM
guard in app/services/audit_trail.py is the enforcement, and it applies on
PostgreSQL too.

Revision ID: 0042_activity_audit_trail
Revises: 0041_claim_verification_log
"""

import sqlalchemy as sa
from alembic import op

revision = "0042_activity_audit_trail"
down_revision = "0041_claim_verification_log"
branch_labels = None
depends_on = None

_GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION activity_audit_events_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'activity_audit_events is append-only (delete refused)';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.user_id IS DISTINCT FROM OLD.user_id
       OR NEW.lead_ref IS DISTINCT FROM OLD.lead_ref
       OR NEW.strategy_ref IS DISTINCT FROM OLD.strategy_ref
       OR NEW.message_ref IS DISTINCT FROM OLD.message_ref
       OR NEW.outcome_ref IS DISTINCT FROM OLD.outcome_ref
       OR NEW.event IS DISTINCT FROM OLD.event
       OR NEW.channel IS DISTINCT FROM OLD.channel
       OR NEW.occurred_at IS DISTINCT FROM OLD.occurred_at
       OR NEW.payload_json::text IS DISTINCT FROM OLD.payload_json::text
       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'activity_audit_events content is immutable';
    END IF;
    IF OLD.chain_hash IS NOT NULL AND (
           NEW.chain_hash IS DISTINCT FROM OLD.chain_hash
        OR NEW.prev_hash IS DISTINCT FROM OLD.prev_hash
        OR NEW.seq_no IS DISTINCT FROM OLD.seq_no
        OR NEW.sealed_at IS DISTINCT FROM OLD.sealed_at) THEN
        RAISE EXCEPTION 'activity_audit_events: a sealed record cannot be re-sealed';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "activity_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lead_ref", sa.Uuid(), nullable=True),
        sa.Column("strategy_ref", sa.Uuid(), nullable=True),
        sa.Column("message_ref", sa.Uuid(), nullable=True),
        sa.Column("outcome_ref", sa.Uuid(), nullable=True),
        sa.Column("event", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("seq_no", sa.Integer(), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("chain_hash", sa.String(length=64), nullable=True),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_activity_audit_events"),
        sa.UniqueConstraint("user_id", "seq_no", name="audit_event_user_seq"),
        sa.UniqueConstraint("outcome_ref", name="audit_event_outcome"),
    )
    op.create_index("ix_activity_audit_events_user_created", "activity_audit_events",
                    ["user_id", "created_at"])
    op.create_index("ix_activity_audit_events_lead_ref", "activity_audit_events",
                    ["lead_ref"])
    if _is_postgres():
        op.execute(_GUARD_FUNCTION)
        op.execute("CREATE TRIGGER activity_audit_events_append_only "
                   "BEFORE UPDATE OR DELETE ON activity_audit_events "
                   "FOR EACH ROW EXECUTE FUNCTION activity_audit_events_guard()")


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP TRIGGER IF EXISTS activity_audit_events_append_only "
                   "ON activity_audit_events")
        op.execute("DROP FUNCTION IF EXISTS activity_audit_events_guard()")
    op.drop_index("ix_activity_audit_events_lead_ref", table_name="activity_audit_events")
    op.drop_index("ix_activity_audit_events_user_created", table_name="activity_audit_events")
    op.drop_table("activity_audit_events")
