"""A dollar budget per strategy run.

F-AI-01. A strategy's pipeline plus its verification loop is the most expensive
operation in the product (about 150 model calls) and nothing limited it: the
only brake was the balance on the Anthropic account. `budget_micros` is the cap,
in millionths of a US dollar -- the same unit as api_usage.cost_micros, so the
two compare directly.

NULLABLE with no default on purpose. Existing rows keep NULL = "no limit", which
is exactly how they behaved before; this migration does not retroactively cap a
strategy that is already running. New strategies get a value from the API.

No change to the status column: it is a VARCHAR holding enum VALUES, with no
CHECK constraint, so the new 'budget_exhausted' value needs no DDL.

Revision ID: 0066_strategy_budget
Revises: 0065_messages_dispatch_index
"""

import sqlalchemy as sa
from alembic import op

revision = "0066_strategy_budget"
down_revision = "0065_messages_dispatch_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("budget_micros", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("strategies") as batch:
        batch.drop_column("budget_micros")
