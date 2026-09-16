"""Data provenance tags (Part 1, Feature 10).

ALTERS
  leads  provenance_json, provenance_updated_at

WHY A JSON COLUMN AND NOT AN EAV TABLE. The repo argued the opposite case for
custom fields (see CrmLeadMeta / CrmCustomFieldValue): a JSON bag is wrong when
the values are SORTED AND FILTERED SERVER-SIDE across thousands of rows,
because JSON extraction is spelled differently on SQLite and PostgreSQL and the
test suite would then exercise a different query than production runs.

Provenance is the other case. It is never sorted, never filtered, never
aggregated -- it is read exactly once, for one prospect, when a person hovers a
field and asks "where did this come from?". One column read with the lead it
describes is the cheapest possible answer, and a per-field table would mean a
second query (or a join fanning out one lead into twenty rows) on the lead
detail page for data nobody queries.

The shape is {field: {source, confidence, observed_at, detail, value}}.
`provenance_updated_at` exists so a UI can say "provenance last refreshed on
..." without walking the map.

Both nullable: a lead sourced before this revision has NO provenance, which is
a different fact from "sourced by an unknown source" -- and the service says so
rather than inventing a source for history.

Revision ID: 0062_data_provenance
Revises: 0061_consent_ledger
"""

import sqlalchemy as sa
from alembic import op

revision = "0062_data_provenance"
down_revision = "0061_consent_ledger"
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("provenance_json", sa.JSON(), nullable=True),
        sa.Column("provenance_updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    for column in _columns():
        op.add_column("leads", column)


def downgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        for column in reversed(_columns()):
            batch.drop_column(column.name)
