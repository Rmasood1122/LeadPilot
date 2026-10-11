"""PD-2: the foreign keys migration 0011 never created on the webhook tables.

THE DEFECT
0011 created webhook_targets.user_id and webhook_deliveries.target_id as bare
uuid columns. The model (app/db/models.py WebhookTarget / WebhookDelivery)
declares both as ForeignKey(..., ondelete="CASCADE"), and the offline suite
builds its tables from the model, so only PostgreSQL ever lacked them. There:

  * removing a user (by hand, or any future account erasure) left its
    webhook targets behind -- and their delivery rows, whose payload_json
    carries lead data -- owned by nobody;
  * removing a target left its deliveries behind the same way.

THE CHANGE
  1. Delete the orphans, in dependency order, and log how many:
       webhook_targets    whose user_id matches no users.id
       webhook_deliveries whose target_id matches no webhook_targets.id
                          (this includes the deliveries of the targets just
                          deleted)
     These rows are unreachable through the API -- every webhook route
     filters by the signed-in owner -- and an orphaned delivery still holds a
     payload of lead data for an account that no longer exists, so deleting
     it is also the GDPR storage-limitation answer. They cannot be restored.
  2. Add the two constraints, named by the project's naming convention
     (app/db/base.py NAMING_CONVENTION, the same names the model metadata
     produces, as earlier FK migrations do, e.g. 0063, 0026):
       fk_webhook_targets_user_id_users                 ON DELETE CASCADE
       fk_webhook_deliveries_target_id_webhook_targets  ON DELETE CASCADE

A constraint that already exists is left alone (a database built from the
model, e.g. the offline suite's, already has both), so the migration is safe on
any database at 0081. SQLite cannot ALTER a constraint in place, so there it
runs in batch mode (table copy), which is how the offline migration test
exercises it.

LOCKING (PostgreSQL): ADD CONSTRAINT ... FOREIGN KEY takes SHARE ROW EXCLUSIVE
on the table and its parent while it validates. Bounded with lock_timeout =
15s, same reasoning as 0071: a stuck lock fails the migration (the old
instance keeps serving) instead of hanging the deploy.

DOWNGRADE drops the two constraints. The orphans deleted by upgrade are not
restored (there is nothing to restore them from).

Revision ID: 0085_webhook_foreign_keys
Revises: 0084_password_reset
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "0085_webhook_foreign_keys"
down_revision = "0084_password_reset"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# (table, column, referred table, constraint name)
_FKS = (
    ("webhook_targets", "user_id", "users", "fk_webhook_targets_user_id_users"),
    ("webhook_deliveries", "target_id", "webhook_targets",
     "fk_webhook_deliveries_target_id_webhook_targets"),
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _has_fk(table: str, column: str, referred: str) -> bool:
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk.get("constrained_columns") == [column] and fk.get("referred_table") == referred:
            return True
    return False


def _delete_orphans() -> None:
    bind = op.get_bind()
    targets = bind.execute(sa.text(
        "DELETE FROM webhook_targets WHERE NOT EXISTS "
        "(SELECT 1 FROM users WHERE users.id = webhook_targets.user_id)"))
    deliveries = bind.execute(sa.text(
        "DELETE FROM webhook_deliveries WHERE NOT EXISTS "
        "(SELECT 1 FROM webhook_targets WHERE webhook_targets.id = webhook_deliveries.target_id)"))
    logger.info("0082: deleted %s orphaned webhook_targets and %s orphaned "
                "webhook_deliveries before adding foreign keys",
                targets.rowcount, deliveries.rowcount)


def upgrade() -> None:
    if _is_postgres():
        op.execute("SET LOCAL lock_timeout = '15s'")
    _delete_orphans()
    for table, column, referred, name in _FKS:
        if _has_fk(table, column, referred):
            continue
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(name, referred, [column], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    if _is_postgres():
        op.execute("SET LOCAL lock_timeout = '15s'")
    for table, column, referred, name in reversed(_FKS):
        if not _has_fk(table, column, referred):
            continue
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="foreignkey")
