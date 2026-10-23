"""Help AI v2, Phase 2: the help-center search index (help_chunks).

Spec: docs/program/plans/help-ai-v2-02-indexing.md.

WHY
  The support assistant retrieves help-center chunks with an in-memory BM25
  index rebuilt in every process. Phase 3 adds dense retrieval (Voyage
  voyage-context-4, DECISIONS HELPAI-VENDOR) and PostgreSQL full-text search,
  so the chunks, their vectors and a tsvector live in one table, written only
  by scripts/help_center/reindex.py from docs/help-center.

CHANGES (PostgreSQL)
  CREATE EXTENSION IF NOT EXISTS vector -- only when pgvector >= 0.7.0 is
  available (halfvec and HNSW-on-halfvec arrived in 0.7.0).
  help_chunks(id text pk, article_id, heading, heading_path, url, body,
              context_sentence, content_hash, embedded_at, model,
              body_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english',
                  heading || ' ' || body)) STORED,
              embedding halfvec(1024))
  ix_help_chunks_article_id      btree (article_id)
  ix_help_chunks_body_tsv        GIN (body_tsv)
  ix_help_chunks_embedding_hnsw  HNSW (embedding halfvec_cosine_ops)
                                 WITH (m = 16, ef_construction = 64)

WHEN PGVECTOR IS NOT AVAILABLE
  The table is created WITHOUT the embedding column and the HNSW index, and a
  warning is logged. Retrieval stays BM25 (in-memory and body_tsv) and the
  reindex job stores text only. This is deliberate: render's API entrypoint
  runs migrations with `set -e`, so a missing extension must not stop the API
  from booting. Adding the column later is its own migration.

SQLITE (the offline suite)
  Neither extension nor tsvector exists, so only the mapped columns are
  created -- exactly app.db.models.HelpChunk. The PostgreSQL-only columns are
  read and written by app/services/help_index.py, never through the model.

LOCKING
  A new, empty table: no reader or writer exists before this revision.
  CREATE EXTENSION takes a brief lock on pg_extension.

DOWNGRADE
  Drops the table and its indexes. The extension is left installed: another
  database object may use it, and dropping it is not needed to restore the
  pre-0094 schema.

Revision ID: 0094_help_chunks
Revises: 0093_playbook_scores_owner
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "0094_help_chunks"
down_revision = "0093_playbook_scores_owner"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

TABLE = "help_chunks"
DIMENSION = 1024
MIN_PGVECTOR = (0, 7, 0)


def _version(text: str) -> tuple[int, ...]:
    parts = []
    for piece in (text or "").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _pgvector_usable(bind) -> bool:
    """True when pgvector is installed at >= 0.7.0 or can be installed."""
    installed = bind.execute(sa.text(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar()
    if installed is not None:
        return _version(installed) >= MIN_PGVECTOR
    available = bind.execute(sa.text(
        "SELECT default_version FROM pg_available_extensions WHERE name = 'vector'")).scalar()
    return available is not None and _version(available) >= MIN_PGVECTOR


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(200), nullable=False),
        sa.Column("article_id", sa.String(100), nullable=False),
        sa.Column("heading", sa.String(300), nullable=False),
        sa.Column("heading_path", sa.Text(), nullable=False),
        sa.Column("url", sa.String(400), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("context_sentence", sa.Text(), server_default="", nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String(80), server_default="", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_help_chunks_article_id", TABLE, ["article_id"])

    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "ALTER TABLE help_chunks ADD COLUMN body_tsv tsvector GENERATED ALWAYS AS "
        "(to_tsvector('english', coalesce(heading, '') || ' ' || coalesce(body, ''))) STORED"
    )
    op.execute("CREATE INDEX ix_help_chunks_body_tsv ON help_chunks USING gin (body_tsv)")

    if not _pgvector_usable(bind):
        logger.warning(
            "0094_help_chunks: pgvector >= 0.7.0 is not available on this server -- "
            "help_chunks has NO embedding column; help-center retrieval stays BM25. "
            "Run: SELECT name, default_version FROM pg_available_extensions "
            "WHERE name = 'vector';")
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(f"ALTER TABLE help_chunks ADD COLUMN embedding halfvec({DIMENSION})")
    op.execute(
        "CREATE INDEX ix_help_chunks_embedding_hnsw ON help_chunks "
        "USING hnsw (embedding halfvec_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.drop_table(TABLE)
