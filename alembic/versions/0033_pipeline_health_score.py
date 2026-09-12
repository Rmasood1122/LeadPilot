"""Feature 1 — pipeline health score.

ALTERS
  strategies  pipeline_health_score, health_band, health_updated_at,
              health_message

All four are NULLABLE with no server default, so the ALTER succeeds on a table
that already has rows and an existing campaign reads as "never scored" rather
than as a score of zero — the same distinction ai_booking_likelihood makes on
leads. app/workers/health_tasks.py fills them in within six hours of deploy;
GET /strategies/{id}/health computes on demand until then, so the endpoint is
correct on a database the refresh sweep has not reached yet.

NOTE ON THE REVISION NUMBER
The specification for this feature called the file 0021_pipeline_health_score.
0021 (and 0022-0025) were already taken by shipped migrations — calendar,
meetings, meeting prep, AI intelligence, personalization — so the standing
rule "next sequential number prefix" puts this at 0033, on top of
0032_tool_integrations.

Revision ID: 0033_pipeline_health
Revises: 0032_tool_integrations
"""

import sqlalchemy as sa
from alembic import op

revision = "0033_pipeline_health"
down_revision = "0032_tool_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategies",
                  sa.Column("pipeline_health_score", sa.Integer(), nullable=True))
    op.add_column("strategies",
                  sa.Column("health_band", sa.String(length=20), nullable=True))
    op.add_column("strategies",
                  sa.Column("health_updated_at", sa.DateTime(timezone=True),
                            nullable=True))
    op.add_column("strategies",
                  sa.Column("health_message", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("strategies") as batch:
        batch.drop_column("health_message")
        batch.drop_column("health_updated_at")
        batch.drop_column("health_band")
        batch.drop_column("pipeline_health_score")
