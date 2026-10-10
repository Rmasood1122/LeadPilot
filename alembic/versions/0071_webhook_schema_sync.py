"""Bring the outbound-webhook tables in line with the model (PD-1).

0011 created these tables for the M8-C5 raw-SQL delivery code. Feature Group 4
rebuilt app/services/webhook_delivery.py on the ORM model (app/db/models.py
WebhookTarget / WebhookDelivery), and 0029 added only source, disabled_reason
and last_attempt_at. So on PostgreSQL:

  webhook_targets.event_types      text[]  but the model writes JSON
                                   -> every create_target failed (DatatypeMismatch)
  webhook_deliveries.payload_json  text    but the model writes JSON
  webhook_deliveries               no last_status_code, no delivered_at
                                   -> every delivery INSERT failed (UndefinedColumn)

SQLite never showed this: the offline suite builds tables from the model.

CHANGES (PostgreSQL only; other dialects build from the model):
  webhook_targets.event_types      text[] -> json, existing arrays kept
  webhook_deliveries.payload_json  text   -> json; text that is not valid JSON
                                   is kept as {"legacy_text": "<original>"}
  webhook_deliveries.last_status_code  added, copied from last_response_code
  webhook_deliveries.delivered_at      added (timestamptz, nullable)

NOT DROPPED: last_response_code and max_retries. Nothing reads them any more,
but dropping data is a separate, deliberate decision. max_retries is NOT NULL
with server default 5, so ORM inserts that omit it still succeed.

Downgrade restores the 0070 shapes (event_types back to text[], payload_json
back to text with legacy_text unwrapped, last_status_code copied back into
last_response_code). delivered_at values are dropped on downgrade.

Both directions set lock_timeout = 15s for their transaction (see
_bounded_lock_wait).

Revision ID: 0071_webhook_schema_sync
Revises: 0070_linkedin_network_messages
"""

import sqlalchemy as sa
from alembic import op

revision = "0071_webhook_schema_sync"
down_revision = "0070_linkedin_network_messages"
branch_labels = None
depends_on = None

# USING clauses cannot hold subqueries or exception handlers, so the two
# conversions that need them are temporary functions, dropped in the same
# transaction.
_TRY_JSON = """
CREATE FUNCTION pg_temp.lp_try_json(value text) RETURNS json
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    RETURN value::json;
EXCEPTION WHEN others THEN
    RETURN json_build_object('legacy_text', value);
END $$;
"""
_JSON_TO_TEXT_ARRAY = """
CREATE FUNCTION pg_temp.lp_json_to_text_array(value json) RETURNS text[]
LANGUAGE sql IMMUTABLE AS $$
    SELECT COALESCE(array_agg(e), '{}'::text[]) FROM json_array_elements_text(value) AS e
$$;
"""


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _bounded_lock_wait() -> None:
    """Both ALTER TYPEs take ACCESS EXCLUSIVE on their table. app/db/migrate.py
    sets no lock timeout, so a transaction still open on these tables (the
    outgoing API instance) would make this deploy's startup wait forever and
    queue every webhook query behind it. Fail the migration instead; the
    entrypoint then never starts uvicorn and the old instance keeps serving."""
    op.execute("SET LOCAL lock_timeout = '15s'")


def upgrade() -> None:
    if not _is_postgres():
        return
    _bounded_lock_wait()

    op.execute("ALTER TABLE webhook_targets ALTER COLUMN event_types DROP DEFAULT")
    op.execute("ALTER TABLE webhook_targets ALTER COLUMN event_types TYPE json "
               "USING to_json(event_types)")
    op.execute("ALTER TABLE webhook_targets ALTER COLUMN event_types SET DEFAULT '[]'::json")

    op.execute(_TRY_JSON)
    op.execute("ALTER TABLE webhook_deliveries ALTER COLUMN payload_json TYPE json "
               "USING pg_temp.lp_try_json(payload_json)")
    op.execute("DROP FUNCTION pg_temp.lp_try_json(text)")

    op.add_column("webhook_deliveries", sa.Column("last_status_code", sa.Integer(), nullable=True))
    op.execute("UPDATE webhook_deliveries SET last_status_code = last_response_code "
               "WHERE last_response_code IS NOT NULL")
    op.add_column("webhook_deliveries",
                  sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    if not _is_postgres():
        return
    _bounded_lock_wait()

    # delivered_at did not exist before 0071; its values are dropped.
    op.drop_column("webhook_deliveries", "delivered_at")
    op.execute("UPDATE webhook_deliveries SET last_response_code = last_status_code "
               "WHERE last_status_code IS NOT NULL")
    op.drop_column("webhook_deliveries", "last_status_code")
    # Unwrap what upgrade wrapped: a {"legacy_text": ...} object goes back to
    # its original text. Nested CASE so json_object_keys-style operators never
    # see a non-object.
    op.execute("""
        ALTER TABLE webhook_deliveries ALTER COLUMN payload_json TYPE text USING
        CASE WHEN json_typeof(payload_json) = 'object' THEN
            CASE WHEN payload_json::jsonb ? 'legacy_text'
                  AND payload_json::jsonb - 'legacy_text' = '{}'::jsonb
                 THEN payload_json->>'legacy_text'
                 ELSE payload_json::text END
        ELSE payload_json::text END
    """)

    op.execute(_JSON_TO_TEXT_ARRAY)
    op.execute("ALTER TABLE webhook_targets ALTER COLUMN event_types DROP DEFAULT")
    op.execute("ALTER TABLE webhook_targets ALTER COLUMN event_types TYPE text[] "
               "USING pg_temp.lp_json_to_text_array(event_types)")
    op.execute("DROP FUNCTION pg_temp.lp_json_to_text_array(json)")
    op.execute("ALTER TABLE webhook_targets ALTER COLUMN event_types SET DEFAULT '{}'::text[]")
