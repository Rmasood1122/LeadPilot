"""GDPR erasure: billing rows can no longer be deleted by deleting their user.

ALTERS (no table created, no column added, no data touched)
  billing_subscriptions.user_id  FK users.id  ON DELETE CASCADE -> RESTRICT
  billable_meetings.user_id      FK users.id  ON DELETE CASCADE -> RESTRICT

WHY. Decision E1 (docs/features/gdpr-erasure.md, needs founder/legal
confirmation): when an account is erased, its subscription mirror and its
invoiced meetings are KEPT, anonymised, for BILLING_RETENTION_YEARS (7) as
tax/accounting records. The erasure itself never deletes the users row (it
becomes a non-personal tombstone), so this is the second line: a hand-written
`DELETE FROM users` -- an operator, a future admin feature -- now fails loudly
instead of silently cascading away records the business must keep.

DOWNGRADE restores ON DELETE CASCADE exactly; nothing is lost either way.

Revision ID: 0083_billing_retention
Revises: 0082_annual_billing
"""

from alembic import op

revision = "0083_billing_retention"
down_revision = "0082_annual_billing"
branch_labels = None
depends_on = None

_FKS = (
    ("billing_subscriptions", "fk_billing_subscriptions_user_id_users"),
    ("billable_meetings", "fk_billable_meetings_user_id_users"),
)


def _set(ondelete: str) -> None:
    for table, name in _FKS:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="foreignkey")
            batch.create_foreign_key(name, "users", ["user_id"], ["id"], ondelete=ondelete)


def upgrade() -> None:
    _set("RESTRICT")


def downgrade() -> None:
    _set("CASCADE")
