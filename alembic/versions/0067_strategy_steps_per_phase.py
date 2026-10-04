"""How many steps per phase a strategy's pipeline runs.

F-AI-01b. A strategy given a small budget runs a reduced plan -- the phase
synthesis plus as many supporting steps as the budget affords -- instead of the
full nine steps per phase. `steps_per_phase` records that plan so a resume
follows it. NULLABLE with no default: NULL = all nine, exactly what every
existing strategy did, so nothing is retroactively changed.

Revision ID: 0067_strategy_steps_per_phase
Revises: 0066_strategy_budget
"""

import sqlalchemy as sa
from alembic import op

revision = "0067_strategy_steps_per_phase"
down_revision = "0066_strategy_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("steps_per_phase", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("strategies") as batch:
        batch.drop_column("steps_per_phase")
