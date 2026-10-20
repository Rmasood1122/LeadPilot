"""F-DB-01: playbook_scores gets an owner.

Spec: docs/program/plans/f-db-01-playbook-owner.md.

WHY
  playbook_scores was keyed on (pattern_key, variant) with no owner column.
  The nightly aggregation pooled the outcomes of EVERY account whose strategy
  shared a pattern_key, and the research pipeline put those pooled rates into
  each account's prompts as "learned from this account's real outcomes"
  (app/services/playbook_service.py). With sign-up open (DECISIONS P0-D-ENF)
  that is one customer's results inside another customer's prompts.

CHANGES
  playbook_scores.user_id  uuid NULL, FK users.id ON DELETE CASCADE, indexed.
  UNIQUE (pattern_key, variant) "pattern_variant"  ->  UNIQUE (user_id,
  pattern_key, variant) "uq_playbook_scores_owner_pattern_variant", the new
  upsert key of app/workers/learning_tasks._upsert_playbook_score.

EXISTING ROWS ARE KEPT, NOT ATTRIBUTED AND NOT DELETED.
  A pooled row cannot be split between accounts, so it keeps user_id NULL.
  No reader returns a NULL-owner row and the aggregation never updates one
  (its upsert always carries a user_id); the next nightly run writes one row
  per (account, pattern_key, variant) from the outcomes table, which is the
  source of truth. Deleting the legacy rows is left to a separate,
  founder-approved step.

LOCKING
  ADD COLUMN (nullable, no default) and the constraint swap take brief
  ACCESS EXCLUSIVE locks; the new unique index is built on a small table
  (one row per pattern/variant). Readers are the nightly task and pipeline
  prompt assembly.

DOWNGRADE
  Deletes the per-account rows (user_id NOT NULL) -- they cannot satisfy the
  old (pattern_key, variant) key once two accounts share a pattern -- then
  restores the old constraint and drops the column. The legacy pooled rows
  are untouched, so the pre-0093 state returns exactly; the next nightly run
  of the pre-0093 code repopulates the pool.

Revision ID: 0093_playbook_scores_owner
Revises: 0092_agent_runs
"""

import sqlalchemy as sa
from alembic import op

revision = "0093_playbook_scores_owner"
down_revision = "0092_agent_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("playbook_scores") as batch:
        batch.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_playbook_scores_user_id_users", "users",
            ["user_id"], ["id"], ondelete="CASCADE",
        )
        batch.create_index("ix_playbook_scores_user_id", ["user_id"])
        batch.drop_constraint("pattern_variant", type_="unique")
        batch.create_unique_constraint(
            "uq_playbook_scores_owner_pattern_variant",
            ["user_id", "pattern_key", "variant"],
        )


def downgrade() -> None:
    op.execute("DELETE FROM playbook_scores WHERE user_id IS NOT NULL")
    with op.batch_alter_table("playbook_scores") as batch:
        batch.drop_constraint("uq_playbook_scores_owner_pattern_variant", type_="unique")
        batch.create_unique_constraint("pattern_variant", ["pattern_key", "variant"])
        batch.drop_index("ix_playbook_scores_user_id")
        batch.drop_constraint("fk_playbook_scores_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")
