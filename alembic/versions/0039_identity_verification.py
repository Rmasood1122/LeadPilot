"""Identity, location and phone verification at onboarding.

ALTERS
  users  identity_required, personal_country, account_type, company_name,
         company_country, identity_submitted_at, signup_ip,
         geo_detected_country, geo_check_status, geo_review_status,
         geo_reviewed_by, geo_reviewed_at, geo_review_note,
         phone_number, phone_verified, phone_verified_at

CREATES
  phone_verification_codes  one SMS one-time code (HMAC only, never the code)
  account_security_events   append-only risk/verification audit

NO BACKFILL, DELIBERATELY. identity_required and phone_verified are added
NOT NULL with a server default of false. For phone_verified that is simply
true -- nobody has proved a number yet. For identity_required it is what keeps
every account that already exists OUT of the new gates: only /auth/signup sets
it, so the onboarding redirect and the phone gate apply to accounts created
from here on and never lock out someone who signed up before they existed
(the 0015 lesson, where the equivalent mistake would have locked out the only
admin).

server_default is the quoted '0' for the same reason 0015 gives: PostgreSQL
casts the string to boolean false, SQLite stores 0.

Revision ID: 0039_identity_verification
Revises: 0038_website_builder
"""

import sqlalchemy as sa
from alembic import op

revision = "0039_identity_verification"
down_revision = "0038_website_builder"
branch_labels = None
depends_on = None

def _user_columns() -> list[sa.Column]:
    """Fresh Column objects per call -- a Column can belong to one Table only,
    and Column.copy() is deprecated in SQLAlchemy 2.0."""
    return [
    sa.Column("identity_required", sa.Boolean(), server_default="0", nullable=False),
    sa.Column("personal_country", sa.String(length=2), nullable=True),
    sa.Column("account_type", sa.String(length=10), nullable=True),
    sa.Column("company_name", sa.String(length=200), nullable=True),
    sa.Column("company_country", sa.String(length=2), nullable=True),
    sa.Column("identity_submitted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("signup_ip", sa.String(length=64), nullable=True),
    sa.Column("geo_detected_country", sa.String(length=2), nullable=True),
    sa.Column("geo_check_status", sa.String(length=10), nullable=True),
    sa.Column("geo_review_status", sa.String(length=20), nullable=True),
    sa.Column("geo_reviewed_by", sa.String(length=320), nullable=True),
    sa.Column("geo_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("geo_review_note", sa.String(length=500), nullable=True),
    sa.Column("phone_number", sa.String(length=20), nullable=True),
    sa.Column("phone_verified", sa.Boolean(), server_default="0", nullable=False),
    sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    for column in _user_columns():
        op.add_column("users", column)
    op.create_index("ix_users_geo_review_status", "users", ["geo_review_status"])
    op.create_index("ix_users_phone_number", "users", ["phone_number"])

    op.create_table(
        "phone_verification_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_phone_verification_codes"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_phone_verification_codes_user_id_users"),
    )
    op.create_index("ix_phone_verification_codes_user_id",
                    "phone_verification_codes", ["user_id"])

    op.create_table(
        "account_security_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_account_security_events"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_account_security_events_user_id_users"),
    )
    op.create_index("ix_account_security_events_user_id",
                    "account_security_events", ["user_id"])
    op.create_index("ix_account_security_events_event_ts",
                    "account_security_events", ["event", "ts"])


def downgrade() -> None:
    op.drop_index("ix_account_security_events_event_ts",
                  table_name="account_security_events")
    op.drop_index("ix_account_security_events_user_id",
                  table_name="account_security_events")
    op.drop_table("account_security_events")
    op.drop_index("ix_phone_verification_codes_user_id",
                  table_name="phone_verification_codes")
    op.drop_table("phone_verification_codes")
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_index("ix_users_geo_review_status", table_name="users")
    with op.batch_alter_table("users") as batch:
        for column in reversed(_user_columns()):
            batch.drop_column(column.name)
