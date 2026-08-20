"""Make device_tokens.token globally unique.

app/api/devices.py upserts with ON CONFLICT (token) and documents the
behaviour explicitly: "Tokens from OTHER users that match are updated to this
user (token transfer after device wipe / new install)". The schema, however,
only ever declared UNIQUE (user_id, token) - see 0009_device_tokens.py - so
PostgreSQL rejected every registration with:

    InvalidColumnReference: there is no unique or exclusion constraint
    matching the ON CONFLICT specification

POST /devices/register therefore returned 500 for every request; push
notification registration has never worked. This aligns the schema with the
handler's documented intent rather than the reverse, because an FCM
registration token identifies one app install: allowing (user_id, token) pairs
would let two accounts hold rows for the same physical device and both receive
its notifications.

Revision ID: 0013_device_token_unique
Revises: 0012_build_repairs
"""

from alembic import op

revision = "0013_device_token_unique"
down_revision = "0012_build_repairs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Collapse any pre-existing duplicates onto the most recently seen row so
    # the unique index can be created. No deployed database exists yet, but a
    # dev DB may hold rows from before this fix.
    op.execute(
        """
        DELETE FROM device_tokens a
        USING device_tokens b
        WHERE a.token = b.token
          AND (
                a.last_seen_at < b.last_seen_at
             OR (a.last_seen_at IS NOT DISTINCT FROM b.last_seen_at AND a.id < b.id)
          )
        """
    )
    op.drop_constraint("uq_device_tokens_user_token", "device_tokens", type_="unique")
    op.create_unique_constraint("uq_device_tokens_token", "device_tokens", ["token"])


def downgrade() -> None:
    op.drop_constraint("uq_device_tokens_token", "device_tokens", type_="unique")
    op.create_unique_constraint(
        "uq_device_tokens_user_token", "device_tokens", ["user_id", "token"]
    )
