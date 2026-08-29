"""Signup email verification: users.email_verified + email_verification_tokens.

Feature 1. Two changes and one backfill.

THE BACKFILL IS THE IMPORTANT PART
----------------------------------
`users.email_verified` is added NOT NULL DEFAULT false, which is correct for
every account created from here on. It is wrong for every account that already
exists: those users signed up before verification was a requirement, never
received a verification email, and have no way to ask for one for an account
they are locked out of. Shipping this without the backfill would have locked
out the live database's existing account — which is also the ADMIN_EMAIL
bootstrap target, i.e. the only administrator.

So `upgrade()` adds the column with a false default and then immediately marks
every PRE-EXISTING row true. The ordering matters: the UPDATE runs inside the
same migration, before any application process can serve a request against the
new schema, so there is no window in which an existing user is unverified.

email_verified_at is set to now() for backfilled rows rather than left NULL,
because a NULL there would later read as "verified but we don't know when",
which is indistinguishable from a bug. now() is honest: it records when the
account was *considered* verified, and the comment here says why.

TOKEN STORAGE
-------------
email_verification_tokens stores sha256(token), never the token. See the model
docstring in app/db/models.py for why. The unique index on token_hash is what
makes lookup-by-hash safe; the index on user_id is for the resend path, which
invalidates a user's outstanding tokens before issuing a new one.

DOWNGRADE
---------
Drops both. Note that downgrading DISCARDS which users had verified — there is
nowhere to put that information in the old schema. Re-upgrading afterwards
backfills everyone to verified again, which is the safe direction (nobody is
locked out) but is not a round trip.

Revision ID: 0015_email_verification
Revises: 0014_strategy_pattern_inputs
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_email_verification"
down_revision = "0014_strategy_pattern_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users.email_verified / email_verified_at --------------------------
    # server_default is a quoted '0': PostgreSQL casts the string literal to
    # boolean false, and SQLite (the unit-test database) stores 0. An unquoted
    # 0 would be an integer and PostgreSQL would refuse it on a boolean column.
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- BACKFILL: every account that existed before this migration --------
    # Bound parameters, not string interpolation, and no WHERE clause: at this
    # instant every row in the table is by definition pre-existing, because the
    # column was created two statements ago.
    op.execute(
        sa.text(
            "UPDATE users SET email_verified = :verified, "
            "email_verified_at = CURRENT_TIMESTAMP"
        ).bindparams(verified=True)
    )

    # --- email_verification_tokens ----------------------------------------
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_email_verification_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_email_verification_tokens"),
    )
    op.create_index(
        "ix_email_verification_tokens_token_hash",
        "email_verification_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_email_verification_tokens_user_id",
        "email_verification_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_verification_tokens_user_id",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "ix_email_verification_tokens_token_hash",
        table_name="email_verification_tokens",
    )
    op.drop_table("email_verification_tokens")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
