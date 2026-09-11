"""Feature Group 2 — hyper-personalization.

ADDS (all NULLABLE, no defaults: metadata-only ALTERs on PostgreSQL, and every
existing row reads as "never fetched" / "no voice profile", which is true)

  leads     linkedin_url, linkedin_posts_json, linkedin_posts_fetched_at,
            company_news_json, company_news_fetched_at, loom_video_json
  users     style_profile_json, style_samples_json, style_profile_updated_at
  messages  personalization_json -- which post / article / voice / video CTA
            the message was written from

No new tables: every one of these is a property of a row that already exists,
and each is read wherever that row is read (the send path reads the lead, the
render path reads the owner).

DOWNGRADE drops the ten columns. Fetched posts and news are re-fetchable; the
voice samples and recorded Loom links are not -- take a dump first.

Revision ID: 0025_personalization
Revises: 0024_ai_intelligence
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_personalization"
down_revision = "0024_ai_intelligence"
branch_labels = None
depends_on = None

_LEAD_COLUMNS = [
    ("linkedin_url", sa.String(length=500)),
    ("linkedin_posts_json", sa.JSON()),
    ("linkedin_posts_fetched_at", sa.DateTime(timezone=True)),
    ("company_news_json", sa.JSON()),
    ("company_news_fetched_at", sa.DateTime(timezone=True)),
    ("loom_video_json", sa.JSON()),
]
_USER_COLUMNS = [
    ("style_profile_json", sa.JSON()),
    ("style_samples_json", sa.JSON()),
    ("style_profile_updated_at", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    for name, type_ in _LEAD_COLUMNS:
        op.add_column("leads", sa.Column(name, type_, nullable=True))
    for name, type_ in _USER_COLUMNS:
        op.add_column("users", sa.Column(name, type_, nullable=True))
    op.add_column("messages", sa.Column("personalization_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("personalization_json")
    with op.batch_alter_table("users") as batch:
        for name, _ in reversed(_USER_COLUMNS):
            batch.drop_column(name)
    with op.batch_alter_table("leads") as batch:
        for name, _ in reversed(_LEAD_COLUMNS):
            batch.drop_column(name)
