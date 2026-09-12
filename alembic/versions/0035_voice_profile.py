"""Feature 3 — founder voice cloning.

CREATES
  voice_profiles  one per product: the founder's own LinkedIn posts, the style
                  dimensions Claude extracted from them, and their signature
                  phrases

No existing table changes.

ONE PROFILE PER PRODUCT, enforced by a UNIQUE constraint on product_id rather
than by application code. A product with two voice profiles has no defined
answer to "which voice does this email go out in?", and the cheapest place to
make that unrepresentable is the schema. Re-analysing therefore UPDATES the
existing row (app/services/voice_profiler.py) instead of inserting a second.

`raw_posts_json` holds the posts the profile was built from. They are kept so a
profile stays auditable -- "why does it think I open with questions?" has an
answer -- and so a re-extraction after a prompt change does not need the user
to paste twenty posts again. They are NEVER put into an outreach prompt; only
the extracted dimensions are (see the module docstring of
app/services/style_profile.py, which makes the same distinction).

Revision ID: 0035_voice_profile
Revises: 0034_reply_intelligence
"""

import sqlalchemy as sa
from alembic import op

revision = "0035_voice_profile"
down_revision = "0034_reply_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("raw_posts_json", sa.JSON(), nullable=True),
        sa.Column("style_dimensions_json", sa.JSON(), nullable=True),
        sa.Column("sample_phrases", sa.JSON(), nullable=True),
        sa.Column("last_analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("post_count", sa.Integer(), server_default=sa.text("0"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_voice_profiles"),
        sa.UniqueConstraint("product_id", name="uq_voice_profiles_product_id"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE",
                                name="fk_voice_profiles_product_id_products"),
    )


def downgrade() -> None:
    op.drop_table("voice_profiles")
