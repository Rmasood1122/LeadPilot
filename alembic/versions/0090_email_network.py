"""Email network -- the LinkedIn network's twin for the people a user already
emails (contacts files, a mailbox export read for HEADERS ONLY, or a scan of
the connected Gmail with format=metadata).

Spec: docs/features/email-network.md.

CREATES (all new tables; no existing table or row changes)
  email_network_imports   one upload or Gmail scan: kind, status, attestation
                          time + version, counts, excluded counts by reason
                          (JSON of numbers), an honest cap note, the Gmail
                          page token + chunk sequence, and tally_json -- the
                          TRANSIENT running tallies of a Gmail scan, cleared
                          when the scan finishes.
  email_contacts          one correspondent per account: name, address,
                          domain, company (+ whether it was guessed from the
                          domain), title (contacts files only), sent / received
                          counts, first / last seen, two-way, per-source counts.
                          UNIQUE (user_id, email).
  email_contact_matches   score against each of the account's products.
                          UNIQUE (contact_id, product_id).
  email_network_messages  a warm first email the user drafts and saves; links
                          to the campaign lead / message it was attached to.
                          UNIQUE (user_id, contact_id).

There is NO column for a subject, a body, a Message-ID, an attachment or a
signature of anyone's email (tests/test_email_network_guards.py scans the
schema). email_network_messages.subject/body are the USER'S OWN draft.

Every user_id is ON DELETE CASCADE. Types work on SQLite and PostgreSQL (plain
sa.JSON everywhere). Constraint/index names follow app/db/base.py NAMING_CONVENTION and
are all under PostgreSQL's 63-character limit (the longest,
fk_email_network_messages_contact_id_email_contacts, is 51).

A partial UNIQUE index uq_email_network_imports_active_scan (user_id) WHERE
kind = 'gmail_scan' AND status IN ('queued', 'running') allows ONE active Gmail
scan per account (SQLite and PostgreSQL both support partial indexes).

DOWNGRADE drops the four tables: every imported contact, score, draft and
import record is lost (re-importable from the user's own files). Campaign leads
created from contacts are ordinary leads and are NOT touched.

Revision ID: 0090_email_network
Revises: 0089_voice_twin
"""

import sqlalchemy as sa
from alembic import op

revision = "0090_email_network"
down_revision = "0089_voice_twin"
branch_labels = None
depends_on = None


_ACTIVE_SCAN = "kind = 'gmail_scan' AND status IN ('queued', 'running')"


def _timestamps() -> list:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    ]


def _int(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), nullable=False, server_default=sa.text("0"))


def upgrade() -> None:
    op.create_table(
        "email_network_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'done'")),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attestation_version", sa.String(10), nullable=True),
        _int("rows_in_file"),
        _int("messages_scanned"),
        _int("people_found"),
        _int("added"),
        _int("updated"),
        _int("excluded"),
        sa.Column("excluded_json", sa.JSON(), nullable=True),
        sa.Column("cap_note", sa.String(300), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("page_token", sa.String(500), nullable=True),
        _int("chunk_seq"),
        sa.Column("tally_json", sa.JSON(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_email_network_imports_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_email_network_imports"),
    )
    op.create_index("ix_email_network_imports_user_id", "email_network_imports", ["user_id"])
    op.create_index("uq_email_network_imports_active_scan", "email_network_imports",
                    ["user_id"], unique=True,
                    sqlite_where=sa.text(_ACTIVE_SCAN), postgresql_where=sa.text(_ACTIVE_SCAN))

    op.create_table(
        "email_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("full_name", sa.String(300), nullable=True),
        sa.Column("company", sa.String(300), nullable=True),
        sa.Column("company_from_domain", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("title", sa.String(300), nullable=True),
        _int("sent_to_count"),
        _int("received_from_count"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("two_way", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("in_contacts_file", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_counts_json", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_email_contacts_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_email_contacts"),
        sa.UniqueConstraint("user_id", "email", name="uq_email_contacts_user_id_email"),
    )
    op.create_index("ix_email_contacts_user_id", "email_contacts", ["user_id"])

    op.create_table(
        "email_contact_matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        _int("icp_score"),
        _int("relationship_score"),
        sa.Column("segment", sa.String(120), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_email_contact_matches_user_id_users"),
        sa.ForeignKeyConstraint(["contact_id"], ["email_contacts.id"], ondelete="CASCADE",
                                name="fk_email_contact_matches_contact_id_email_contacts"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE",
                                name="fk_email_contact_matches_product_id_products"),
        sa.PrimaryKeyConstraint("id", name="pk_email_contact_matches"),
        sa.UniqueConstraint("contact_id", "product_id",
                            name="uq_email_contact_matches_contact_id_product_id"),
    )
    op.create_index("ix_email_contact_matches_user_id", "email_contact_matches", ["user_id"])
    op.create_index("ix_email_contact_matches_contact_id", "email_contact_matches",
                    ["contact_id"])
    op.create_index("ix_email_contact_matches_product_id", "email_contact_matches",
                    ["product_id"])

    op.create_table(
        "email_network_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_email_network_messages_user_id_users"),
        sa.ForeignKeyConstraint(["contact_id"], ["email_contacts.id"], ondelete="CASCADE",
                                name="fk_email_network_messages_contact_id_email_contacts"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE",
                                name="fk_email_network_messages_product_id_products"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL",
                                name="fk_email_network_messages_strategy_id_strategies"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL",
                                name="fk_email_network_messages_lead_id_leads"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL",
                                name="fk_email_network_messages_message_id_messages"),
        sa.PrimaryKeyConstraint("id", name="pk_email_network_messages"),
        sa.UniqueConstraint("user_id", "contact_id",
                            name="uq_email_network_messages_user_id_contact_id"),
    )
    for column in ("user_id", "contact_id", "product_id", "strategy_id", "lead_id",
                   "message_id"):
        op.create_index(f"ix_email_network_messages_{column}", "email_network_messages",
                        [column])


def downgrade() -> None:
    for column in ("message_id", "lead_id", "strategy_id", "product_id", "contact_id",
                   "user_id"):
        op.drop_index(f"ix_email_network_messages_{column}",
                      table_name="email_network_messages")
    op.drop_table("email_network_messages")
    for column in ("product_id", "contact_id", "user_id"):
        op.drop_index(f"ix_email_contact_matches_{column}", table_name="email_contact_matches")
    op.drop_table("email_contact_matches")
    op.drop_index("ix_email_contacts_user_id", table_name="email_contacts")
    op.drop_table("email_contacts")
    op.drop_index("uq_email_network_imports_active_scan", table_name="email_network_imports")
    op.drop_index("ix_email_network_imports_user_id", table_name="email_network_imports")
    op.drop_table("email_network_imports")
