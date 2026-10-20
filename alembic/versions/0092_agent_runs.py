"""Vectorae agents: the master supervisor's run log.

Spec: docs/features/vectorae-agents.md.

CREATES
  agent_runs   one run of one agent for one account: agent name, ok, latency,
               backend (native | python), a short error class, item count,
               started_at. user_id is ON DELETE CASCADE (account-owned; listed
               in account_export.OWNERSHIP and account_erasure.DELETED).
               Index (agent, started_at): the supervisor reads an agent's most
               recent runs on every call.

LOCKING: a new table only; nothing existing is locked.

DOWNGRADE drops the table. The agents keep working; every circuit breaker
starts closed again because its history is gone.

Revision ID: 0092_agent_runs
Revises: 0091_oauth_connector
"""

import sqlalchemy as sa
from alembic import op

revision = "0092_agent_runs"
down_revision = "0091_oauth_connector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("agent", sa.String(40), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("backend", sa.String(10), nullable=False),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    op.create_index("ix_agent_runs_agent_started_at", "agent_runs", ["agent", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_agent_started_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_user_id", table_name="agent_runs")
    op.drop_table("agent_runs")
