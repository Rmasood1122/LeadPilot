"""The help-center search index in PostgreSQL (help_chunks, alembic 0094).

The in-memory BM25 index in app/services/help_center.py stays the source of
answers until Phase 3 and the fallback after it: nothing here is needed for
the support assistant to work, and an empty or stale help_chunks table only
means dense retrieval is unavailable.

ONE SOURCE. Rows are derived from docs/help-center (help_center.load_corpus,
the same chunker the BM25 path uses: merge under 120 tokens, split over 700,
stable id "<article-id>#<heading-slug>"). Nothing from a user's question or
account is ever written here, and the table has no owner: every user
searches the same product documentation.

CONTENT HASH. A chunk's vector is a CONTEXTUALIZED embedding: Voyage embeds
it with the rest of its article as context (DECISIONS HELPAI-VENDOR). So the
hash covers the chunk's own embedding text AND its article's, and editing any
chunk of an article re-embeds that whole article -- the other chunks' context
changed too. Metadata that is not embedded (url) does not touch the hash.
A row is (re-)embedded when its hash changed, it has no vector, or its vector
came from a different embedder (help_chunks.model).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.db.models import HelpChunk
from app.services import help_center

logger = logging.getLogger(__name__)

HASH_VERSION = 1
CONTINUED = " (continued)"


@dataclass(frozen=True)
class IndexRow:
    id: str
    article_id: str
    heading: str
    heading_path: str
    url: str
    body: str
    embed_text: str
    content_hash: str


@dataclass
class SyncResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)      # text or metadata changed
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0
    embedded: list[str] = field(default_factory=list)     # vectors written this run
    pending: list[str] = field(default_factory=list)      # need a vector, none written
    embedding_note: str = ""                              # why nothing was embedded

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed or self.embedded)

    def summary(self) -> str:
        lines = [
            f"help_chunks: {len(self.added)} added, {len(self.updated)} updated, "
            f"{len(self.removed)} removed, {self.unchanged} unchanged",
            f"embeddings: {len(self.embedded)} written, {len(self.pending)} still pending"
            + (f" ({self.embedding_note})" if self.embedding_note else ""),
        ]
        for label, ids in (("+", self.added), ("~", self.updated), ("-", self.removed)):
            lines.extend(f"  {label} {chunk_id}" for chunk_id in ids)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rows from the corpus
# ---------------------------------------------------------------------------


def chunk_url(chunk: help_center.Chunk) -> str:
    """The page and heading anchor a citation of this chunk links to.

    The site renders each article at /help/<id>/ with GitHub-style anchors on
    its H2s (frontend/src/lib/content/markdown.ts slugify == help_center.slugify).
    A merged chunk links to its lead section; a split continuation links to
    the heading it continues; the article intro has no anchor."""
    base = f"/help/{chunk.article_id}/"
    if chunk.heading == chunk.article_title:
        return base
    heading = chunk.heading[:-len(CONTINUED)] if chunk.heading.endswith(CONTINUED) else chunk.heading
    return f"{base}#{help_center.slugify(heading)}"


def heading_path(chunk: help_center.Chunk) -> str:
    headings = [s.heading for s in chunk.sections if s.heading != chunk.article_title]
    return chunk.article_title + (" > " + " + ".join(headings) if headings else "")


def embedding_text(chunk: help_center.Chunk) -> str:
    """What is embedded for a chunk: its heading path, then its markdown."""
    return f"{heading_path(chunk)}\n\n{chunk.body}".strip()


def build_rows(corpus: help_center.Corpus) -> list[IndexRow]:
    by_article: dict[str, list[help_center.Chunk]] = {}
    for chunk in corpus.chunks:
        by_article.setdefault(chunk.article_id, []).append(chunk)
    rows: list[IndexRow] = []
    for article_id, chunks in by_article.items():
        texts = [embedding_text(c) for c in chunks]
        context = hashlib.sha256("\x1e".join(texts).encode("utf-8")).hexdigest()
        for chunk, embed_text in zip(chunks, texts):
            digest = hashlib.sha256(json.dumps(
                {"v": HASH_VERSION, "text": embed_text, "article": context},
                sort_keys=True).encode("utf-8")).hexdigest()
            rows.append(IndexRow(
                id=chunk.id, article_id=article_id, heading=chunk.heading,
                heading_path=heading_path(chunk), url=chunk_url(chunk), body=chunk.body,
                embed_text=embed_text, content_hash=digest,
            ))
    return rows


# ---------------------------------------------------------------------------
# Manifest: the CI staleness check
# ---------------------------------------------------------------------------


MANIFEST_PATH = Path(__file__).resolve().parents[2] / "scripts" / "help_center" / "index_manifest.json"


def manifest(rows: list[IndexRow]) -> dict:
    """{chunk id: content hash}, the committed record of what the index must
    hold. CI regenerates it from the corpus and fails on any difference, so
    a corpus edit cannot merge without the index change being visible in the
    same diff; the deploy reindex then makes the database match."""
    return {"hash_version": HASH_VERSION,
            "chunks": {row.id: row.content_hash for row in sorted(rows, key=lambda r: r.id)}}


def render_manifest(rows: list[IndexRow]) -> str:
    return json.dumps(manifest(rows), indent=2, sort_keys=True) + "\n"


def manifest_diff(expected: dict, committed: dict) -> list[str]:
    want, have = expected.get("chunks", {}), committed.get("chunks", {})
    out = [f"+ {k}" for k in sorted(set(want) - set(have))]
    out += [f"- {k}" for k in sorted(set(have) - set(want))]
    out += [f"~ {k}" for k in sorted(set(want) & set(have)) if want[k] != have[k]]
    if expected.get("hash_version") != committed.get("hash_version"):
        out.insert(0, f"hash_version {committed.get('hash_version')} -> {expected.get('hash_version')}")
    return out


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def has_vector_column(session: Session) -> bool:
    """True on PostgreSQL when 0094 could create help_chunks.embedding."""
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    return session.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = 'help_chunks' "
        "AND column_name = 'embedding' AND table_schema = current_schema()")).first() is not None


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"


def needs_embedding(row: IndexRow, stored: HelpChunk | None, embedder: str) -> bool:
    return (stored is None or stored.content_hash != row.content_hash
            or stored.embedded_at is None or stored.model != embedder)


def sync(session: Session, rows: list[IndexRow], *, embed: bool, embedder: str = "",
         embed_documents=None) -> SyncResult:
    """Make help_chunks equal `rows`; embed what needs it when `embed`.

    `embed_documents` is embeddings_client.embed_documents (injected so the
    caller decides the mode). Text is committed BEFORE any vendor call, so a
    vendor failure leaves a correct text index with vectors pending -- the
    next run embeds them; BM25 never waits on it."""
    result = SyncResult()
    stored = {c.id: c for c in session.execute(select(HelpChunk)).scalars()}
    wanted = {row.id: row for row in rows}

    for chunk_id in sorted(set(stored) - set(wanted)):
        result.removed.append(chunk_id)
    if result.removed:
        session.execute(delete(HelpChunk).where(HelpChunk.id.in_(result.removed)))

    vector_column = has_vector_column(session)
    for row in rows:
        current = stored.get(row.id)
        values = dict(article_id=row.article_id, heading=row.heading,
                      heading_path=row.heading_path, url=row.url, body=row.body)
        if current is None:
            session.add(HelpChunk(id=row.id, content_hash=row.content_hash,
                                  context_sentence="", embedded_at=None, model="", **values))
            result.added.append(row.id)
            continue
        text_changed = current.content_hash != row.content_hash
        meta_changed = any(getattr(current, k) != v for k, v in values.items())
        if not (text_changed or meta_changed):
            result.unchanged += 1
            continue
        for key, value in values.items():
            setattr(current, key, value)
        if text_changed:
            current.content_hash = row.content_hash
            current.embedded_at = None
            current.model = ""
            if vector_column:
                session.flush()
                session.execute(text("UPDATE help_chunks SET embedding = NULL WHERE id = :id"),
                                {"id": row.id})
        result.updated.append(row.id)
    session.commit()

    # `stored` holds the same (now updated) objects: a changed row has
    # embedded_at None, a new one is absent -- both need a vector.
    pending_articles = {row.article_id for row in rows
                        if needs_embedding(row, stored.get(row.id), embedder)}
    pending_rows = [row for row in rows if row.article_id in pending_articles]
    if not pending_rows:
        return result
    if not vector_column:
        result.pending = [r.id for r in pending_rows]
        result.embedding_note = "no embedding column (SQLite, or pgvector unavailable)"
        return result
    if not embed or embed_documents is None:
        result.pending = [r.id for r in pending_rows]
        result.embedding_note = "embedding disabled for this run"
        return result

    by_article: dict[str, list[IndexRow]] = {}
    for row in pending_rows:
        by_article.setdefault(row.article_id, []).append(row)
    groups = list(by_article.values())
    from app.services.embeddings_client import EmbeddingsUnavailable  # noqa: PLC0415

    try:
        vectors = embed_documents([[r.embed_text for r in group] for group in groups])
    except EmbeddingsUnavailable as exc:
        result.pending = [r.id for r in pending_rows]
        result.embedding_note = f"embeddings unavailable: {exc}"
        logger.warning("help index: %s; text index is current, %d vectors pending",
                       exc, len(pending_rows))
        return result

    now = datetime.now(timezone.utc)
    for group, group_vectors in zip(groups, vectors):
        for row, vector in zip(group, group_vectors):
            session.execute(text(
                "UPDATE help_chunks SET embedding = CAST(:v AS halfvec), embedded_at = :at, "
                "model = :model WHERE id = :id"),
                {"v": _vector_literal(vector), "at": now, "model": embedder, "id": row.id})
            result.embedded.append(row.id)
    session.commit()
    return result


def stale(session: Session, rows: list[IndexRow], embedder: str) -> list[str]:
    """What a sync would change, without changing it (reindex --check)."""
    stored = {c.id: c for c in session.execute(select(HelpChunk)).scalars()}
    out = [f"- {k}" for k in sorted(set(stored) - {r.id for r in rows})]
    vector_column = has_vector_column(session)
    for row in rows:
        current = stored.get(row.id)
        if current is None:
            out.append(f"+ {row.id}")
        elif (current.content_hash != row.content_hash or current.url != row.url
              or current.heading_path != row.heading_path):
            out.append(f"~ {row.id}")
        elif vector_column and needs_embedding(row, current, embedder):
            out.append(f"e {row.id}")
    return out


def vector_search(session: Session, query_vector: list[float], k: int) -> list[tuple[str, float]]:
    """Nearest chunks by cosine distance (HNSW), best first: [(id, distance)].
    PostgreSQL with the embedding column only. Rows without a vector are
    never returned."""
    rows = session.execute(text(
        "SELECT id, embedding <=> CAST(:q AS halfvec) AS distance FROM help_chunks "
        "WHERE embedding IS NOT NULL ORDER BY embedding <=> CAST(:q AS halfvec) LIMIT :k"),
        {"q": _vector_literal(query_vector), "k": int(k)}).all()
    return [(r.id, float(r.distance)) for r in rows]

