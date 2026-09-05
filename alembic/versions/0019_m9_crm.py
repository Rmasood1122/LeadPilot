"""M9 — native CRM layer: notes, activity, tags, saved views, custom fields.

WHAT THIS ADDS
Eight new tables, all additive:
  crm_notes                free text on a lead, authored by a user
  crm_activities           append-only, UI-facing audit trail per lead
  crm_tags                 per-user labels
  crm_lead_tags            lead <-> tag association
  crm_saved_views          named filters+sort+columns, persisted per user
  crm_custom_fields        user-defined column definitions
  crm_custom_field_values  EAV values for those definitions
  crm_lead_meta            CRM-only per-lead state (owner, stage_entered_at)

WHAT THIS DOES NOT TOUCH
No existing table is altered. `leads`, `strategies` and `outcomes` are read by
the M2 sourcing chain, the M3/M4 sequence engine, the M8 nightly learning loop
and the published SDK. Two columns were the obvious shortcut here -- an
`owner_user_id` and a `custom_fields_json` on `leads` -- and both were rejected:
the first would be a column that only the CRM UI ever writes sitting in the row
every one of those readers loads, and the second cannot be sorted or filtered
server-side by a query that is spelled the same way in SQLite (json_extract)
and PostgreSQL (->>), which would mean the test suite exercising a different
query shape than production. crm_lead_meta and the field definition/value pair
carry both instead, joined on lead_id.

WHY crm_activities IS NOT `outcomes`
`outcomes` is the learning loop's immutable event log. The nightly aggregation,
the A/B sweep and the playbook scorer all read it and compute RATES from its
row counts. Writing "note added" and "tag removed" rows into it would change
the denominators those rates are built from, silently, in a table three
milestones of code already depend on. They stay separate on purpose; a reply
legitimately writes one row to each.

STAGE HISTORY STARTS EMPTY
crm_lead_meta.stage_entered_at is NOT backfilled. The information does not
exist: `leads.updated_at` moves on any write at all (a WhatsApp opt-in
timestamp, an enrichment refresh), so copying it in would manufacture a
stage-entry time that is simply wrong for an unknowable share of rows, and the
lead-velocity dashboard would then report a precise-looking average built on
it. Leads keep NULL until their next status change writes a real value; the
dashboard falls back to updated_at for those and labels the figure estimated.

DOWNGRADE
Drops all eight tables. Notes, activity history, tags, saved views and every
custom field value are destroyed and exist nowhere else -- they are not derived
from anything. Take a dump before downgrading.

Revision ID: 0019_m9_crm
Revises: 0018_tutorial_catalogue
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_m9_crm"
down_revision = "0018_tutorial_catalogue"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    """created_at/updated_at exactly as TimestampMixin declares them."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    # ---- crm_tags --------------------------------------------------------
    # Created before crm_lead_tags, which references it.
    op.create_table(
        "crm_tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        # A theme TOKEN name, never a hex value -- see the model docstring.
        sa.Column("color_token", sa.String(length=20), nullable=False,
                  server_default="muted"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_crm_tags"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_crm_tags_user_id_users"),
        sa.UniqueConstraint("user_id", "name", name="crm_tag_user_name"),
    )
    op.create_index("ix_crm_tags_user_id", "crm_tags", ["user_id"])

    # ---- crm_notes -------------------------------------------------------
    op.create_table(
        "crm_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_crm_notes"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_crm_notes_lead_id_leads"),
        # SET NULL, not CASCADE: deleting a user must not erase notes that are
        # still attached to a live lead.
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"],
                                ondelete="SET NULL",
                                name="fk_crm_notes_author_user_id_users"),
    )
    op.create_index("ix_crm_notes_lead_id", "crm_notes", ["lead_id"])
    op.create_index("ix_crm_notes_author_user_id", "crm_notes",
                    ["author_user_id"])
    op.create_index("ix_crm_notes_lead_created", "crm_notes",
                    ["lead_id", "created_at"])

    # ---- crm_activities --------------------------------------------------
    op.create_table(
        "crm_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        # VARCHAR-backed enum (native_enum=False everywhere in this schema):
        # adding a kind later is a data-free change on both dialects.
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("from_value", sa.String(length=200), nullable=True),
        sa.Column("to_value", sa.String(length=200), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_crm_activities"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_crm_activities_lead_id_leads"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"],
                                ondelete="SET NULL",
                                name="fk_crm_activities_strategy_id_strategies"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"],
                                ondelete="SET NULL",
                                name="fk_crm_activities_actor_user_id_users"),
    )
    op.create_index("ix_crm_activities_lead_id", "crm_activities", ["lead_id"])
    op.create_index("ix_crm_activities_strategy_id", "crm_activities",
                    ["strategy_id"])
    op.create_index("ix_crm_activities_kind", "crm_activities", ["kind"])
    # The two composite indexes the feed actually reads through: per-lead
    # timeline, and the account-wide feed filtered by strategy.
    op.create_index("ix_crm_activities_lead_ts", "crm_activities",
                    ["lead_id", "ts"])
    op.create_index("ix_crm_activities_strategy_ts", "crm_activities",
                    ["strategy_id", "ts"])

    # ---- crm_lead_tags ---------------------------------------------------
    op.create_table(
        "crm_lead_tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_crm_lead_tags"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_crm_lead_tags_lead_id_leads"),
        sa.ForeignKeyConstraint(["tag_id"], ["crm_tags.id"], ondelete="CASCADE",
                                name="fk_crm_lead_tags_tag_id_crm_tags"),
        # Makes double-tagging impossible at the schema level, so the bulk-tag
        # endpoint can be naively idempotent instead of reading before writing.
        sa.UniqueConstraint("lead_id", "tag_id", name="crm_lead_tag_unique"),
    )
    op.create_index("ix_crm_lead_tags_lead_id", "crm_lead_tags", ["lead_id"])
    op.create_index("ix_crm_lead_tags_tag_id", "crm_lead_tags", ["tag_id"])

    # ---- crm_saved_views -------------------------------------------------
    op.create_table(
        "crm_saved_views",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("view_type", sa.String(length=32), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column("sort_json", sa.JSON(), nullable=False),
        sa.Column("columns_json", sa.JSON(), nullable=False),
        # Quoted '0': PostgreSQL casts the string literal to boolean false.
        sa.Column("is_default", sa.Boolean(), nullable=False,
                  server_default="0"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_crm_saved_views"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_crm_saved_views_user_id_users"),
        sa.UniqueConstraint("user_id", "view_type", "name",
                            name="crm_view_user_type_name"),
    )
    op.create_index("ix_crm_saved_views_user_id", "crm_saved_views", ["user_id"])
    op.create_index("ix_crm_saved_views_view_type", "crm_saved_views",
                    ["view_type"])

    # ---- crm_custom_fields -----------------------------------------------
    op.create_table(
        "crm_custom_fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # `key` is the stable machine name saved views reference; `label` is
        # what the header shows. Separate so a rename does not orphan views.
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("field_type", sa.String(length=32), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False,
                  server_default="0"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_crm_custom_fields"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_crm_custom_fields_user_id_users"),
        sa.UniqueConstraint("user_id", "key", name="crm_field_user_key"),
    )
    op.create_index("ix_crm_custom_fields_user_id", "crm_custom_fields",
                    ["user_id"])

    # ---- crm_custom_field_values ----------------------------------------
    op.create_table(
        "crm_custom_field_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("field_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        # Canonical sortable/filterable form, ALWAYS populated (numbers
        # zero-padded, dates ISO-8601, bools "true"/"false") so that lexical
        # ordering matches semantic ordering on both dialects.
        sa.Column("value_text", sa.String(length=500), nullable=True),
        sa.Column("value_json", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_crm_custom_field_values"),
        sa.ForeignKeyConstraint(
            ["field_id"], ["crm_custom_fields.id"], ondelete="CASCADE",
            name="fk_crm_custom_field_values_field_id_crm_custom_fields"),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="CASCADE",
            name="fk_crm_custom_field_values_lead_id_leads"),
        sa.UniqueConstraint("field_id", "lead_id",
                            name="crm_field_value_unique"),
    )
    op.create_index("ix_crm_custom_field_values_field_id",
                    "crm_custom_field_values", ["field_id"])
    op.create_index("ix_crm_custom_field_values_lead_id",
                    "crm_custom_field_values", ["lead_id"])
    # The index the grid's per-field sort and filter runs through.
    op.create_index("ix_crm_field_values_field_text", "crm_custom_field_values",
                    ["field_id", "value_text"])

    # ---- crm_lead_meta ---------------------------------------------------
    op.create_table(
        "crm_lead_meta",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=True),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        # NOT backfilled -- see the module docstring.
        sa.Column("stage_entered_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_crm_lead_meta"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_crm_lead_meta_lead_id_leads"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"],
                                ondelete="SET NULL",
                                name="fk_crm_lead_meta_owner_user_id_users"),
        sa.UniqueConstraint("lead_id", name="crm_lead_meta_lead"),
    )
    op.create_index("ix_crm_lead_meta_lead_id", "crm_lead_meta", ["lead_id"])
    op.create_index("ix_crm_lead_meta_owner_user_id", "crm_lead_meta",
                    ["owner_user_id"])


def downgrade() -> None:
    # Reverse creation order: children before the tables they reference.
    op.drop_index("ix_crm_lead_meta_owner_user_id", table_name="crm_lead_meta")
    op.drop_index("ix_crm_lead_meta_lead_id", table_name="crm_lead_meta")
    op.drop_table("crm_lead_meta")

    op.drop_index("ix_crm_field_values_field_text",
                  table_name="crm_custom_field_values")
    op.drop_index("ix_crm_custom_field_values_lead_id",
                  table_name="crm_custom_field_values")
    op.drop_index("ix_crm_custom_field_values_field_id",
                  table_name="crm_custom_field_values")
    op.drop_table("crm_custom_field_values")

    op.drop_index("ix_crm_custom_fields_user_id", table_name="crm_custom_fields")
    op.drop_table("crm_custom_fields")

    op.drop_index("ix_crm_saved_views_view_type", table_name="crm_saved_views")
    op.drop_index("ix_crm_saved_views_user_id", table_name="crm_saved_views")
    op.drop_table("crm_saved_views")

    op.drop_index("ix_crm_lead_tags_tag_id", table_name="crm_lead_tags")
    op.drop_index("ix_crm_lead_tags_lead_id", table_name="crm_lead_tags")
    op.drop_table("crm_lead_tags")

    op.drop_index("ix_crm_activities_strategy_ts", table_name="crm_activities")
    op.drop_index("ix_crm_activities_lead_ts", table_name="crm_activities")
    op.drop_index("ix_crm_activities_kind", table_name="crm_activities")
    op.drop_index("ix_crm_activities_strategy_id", table_name="crm_activities")
    op.drop_index("ix_crm_activities_lead_id", table_name="crm_activities")
    op.drop_table("crm_activities")

    op.drop_index("ix_crm_notes_lead_created", table_name="crm_notes")
    op.drop_index("ix_crm_notes_author_user_id", table_name="crm_notes")
    op.drop_index("ix_crm_notes_lead_id", table_name="crm_notes")
    op.drop_table("crm_notes")

    op.drop_index("ix_crm_tags_user_id", table_name="crm_tags")
    op.drop_table("crm_tags")
