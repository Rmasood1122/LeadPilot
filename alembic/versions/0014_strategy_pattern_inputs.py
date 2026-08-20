"""Persist the canonical payload that produced strategies.pattern_key.

pattern_key is a SHA-256 and nothing else was stored, so the inputs that
produced it were thrown away the moment it was computed. That had three
consequences:

  1. The bucket could not be audited. Two strategies either share a playbook
     bucket or they do not, and there was no way to see WHY - the hash is
     opaque and the ICP criteria / tactic profile behind it existed only in
     memory during the pipeline run.
  2. scripts/backfill_pattern_key.py had to re-derive the inputs from the
     research steps through TWO Anthropic calls per strategy, so a backfill
     needed a live API key, cost money per row, and could not run offline.
  3. Worse, re-derivation is not deterministic: the model can answer the ICP
     and tactic prompts differently on a later run (or a later model version),
     so a "recompute" could legitimately produce a different key for an
     unchanged strategy and silently move it to a new bucket - orphaning its
     playbook_scores rows for reasons that had nothing to do with the
     strategy changing.

Storing the exact canonical dict that was hashed fixes all three: the key
becomes auditable, the backfill can rehash offline from the stored payload,
and a recompute is reproducible.

Nullable: rows written before this migration have no payload, and the backfill
falls back to re-derivation for those.

Revision ID: 0014_strategy_pattern_inputs
Revises: 0013_device_token_unique
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_strategy_pattern_inputs"
down_revision = "0013_device_token_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategies",
        sa.Column("pattern_inputs_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strategies", "pattern_inputs_json")
