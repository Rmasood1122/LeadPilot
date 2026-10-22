"""Help AI v2, Phase 2 exit gate, on PostgreSQL with pgvector.

  * alembic 0094 creates help_chunks with halfvec(1024), the HNSW index
    (halfvec_cosine_ops, m=16, ef_construction=64) and the GIN tsvector index;
  * reindex run twice: the first embeds every chunk, the second writes and
    embeds NOTHING; editing one article re-embeds exactly that article;
  * vector search through the HNSW index returns the expected chunk for 10
    fixed golden questions, and the same order as an exact cosine scan;
  * the vendor down: the text index is still synced, vectors stay pending
    and the next run embeds them;
  * downgrade removes the table.

Vectors come from the deterministic mock embedder (no network in this
suite). This proves the index machinery -- storage, hashing, HNSW cosine
ordering -- not Voyage's retrieval quality, which only scripts/help_center/
live_eval.py with a real key can measure (Phase 5).

The 10 questions are golden-set items whose expected chunk is unambiguous
under the mock embedder (top-1 on 2026-10-22: 77 of 151 golden questions were
top-1 and 130 of 151 in the top 6), one per article area. Expected ids are
read from tests/help_center/golden_questions.yaml, so a heading change fails
here exactly as it fails the BM25 recall test.

Same scratch-database technique as test_migration_0093_playbook_owner_pg.py.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.services import embeddings_client, help_center, help_index
from scripts.help_center import reindex
from tests.integration.conftest import TEST_DATABASE_URL

REPO = Path(__file__).resolve().parents[2]
HELP = REPO / "docs" / "help-center"
GOLDEN = REPO / "tests" / "help_center" / "golden_questions.yaml"
FIXED_QUERIES = ("q03", "q09", "q15", "q24", "q36", "q53", "n05", "n21", "n33", "n53")


def _alembic(url: str, *args: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=str(REPO),
        env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, f"alembic {' '.join(args)} failed:\n{proc.stdout}\n{proc.stderr}"


@pytest.fixture()
def scratch_url():
    base = make_url(TEST_DATABASE_URL)
    assert base.host in ("localhost", "127.0.0.1"), "scratch databases are local only"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        available = c.execute(text(
            "SELECT default_version FROM pg_available_extensions WHERE name = 'vector'")).scalar()
    if available is None:
        admin.dispose()
        if os.environ.get("CI"):
            pytest.fail("CI's PostgreSQL has no pgvector; .github/workflows/verify.yml must "
                        "use the pgvector image -- the Phase 2 exit gate cannot be skipped")
        pytest.skip("this PostgreSQL has no pgvector >= 0.7 (CI uses pgvector/pgvector:0.8.1-pg16)")
    name = f"lp_help_{uuid.uuid4().hex[:8]}"
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture()
def session(scratch_url, monkeypatch):
    monkeypatch.setattr(settings, "embeddings_mode", "mock")
    _alembic(scratch_url, "upgrade", "head")
    engine = create_engine(scratch_url)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_schema(session):
    columns = dict(session.execute(text(
        "SELECT column_name, format_type(atttypid, atttypmod) FROM information_schema.columns "
        "JOIN pg_attribute ON attrelid = 'help_chunks'::regclass AND attname = column_name "
        "WHERE table_name = 'help_chunks'")).all())
    assert columns["embedding"] == "halfvec(1024)"
    assert columns["body_tsv"] == "tsvector"
    indexes = dict(session.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'help_chunks'")).all())
    hnsw = indexes["ix_help_chunks_embedding_hnsw"]
    assert "USING hnsw (embedding halfvec_cosine_ops)" in hnsw
    assert "m='16'" in hnsw and "ef_construction='64'" in hnsw
    assert "USING gin (body_tsv)" in indexes["ix_help_chunks_body_tsv"]
    assert help_index.has_vector_column(session)


def test_second_reindex_embeds_nothing(session, tmp_path):
    first = reindex.run(session, allow_mock=True, directory=HELP)
    total = len(help_index.build_rows(help_center.load_corpus(HELP)))
    assert len(first.added) == len(first.embedded) == total and first.pending == []

    second = reindex.run(session, allow_mock=True, directory=HELP)
    assert second.embedded == [] and second.added == second.updated == second.removed == []
    assert second.unchanged == total
    assert help_index.stale(session, help_index.build_rows(help_center.load_corpus(HELP)),
                            embeddings_client.embedder_id()) == []
    assert session.execute(text(
        "SELECT count(*) FROM help_chunks WHERE embedding IS NULL OR embedded_at IS NULL "
        "OR model <> :m"), {"m": embeddings_client.embedder_id()}).scalar() == 0

    # One article edited: exactly that article's chunks are re-embedded.
    corpus = tmp_path / "help-center"
    shutil.copytree(HELP, corpus)
    path = next(corpus.glob("13-*.md"))
    raw = path.read_text(encoding="utf-8")
    cut = raw.index("\n## ")
    path.write_text(raw[:cut] + "\n\nOne more sentence." + raw[cut:], encoding="utf-8")
    article = help_center._parse_article(path).id
    third = reindex.run(session, allow_mock=True, directory=corpus)
    assert third.embedded and {i.split("#")[0] for i in third.embedded} == {article}
    assert sorted(third.embedded) == sorted(
        r.id for r in help_index.build_rows(help_center.load_corpus(corpus))
        if r.article_id == article)


def test_vector_search_finds_the_expected_chunk(session):
    reindex.run(session, allow_mock=True, directory=HELP)
    golden = {q["id"]: q for q in yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["answerable"]}
    session.execute(text("SET enable_seqscan = off"))   # make the planner use HNSW
    plan = "\n".join(r[0] for r in session.execute(text(
        "EXPLAIN SELECT id FROM help_chunks ORDER BY embedding <=> CAST(:q AS halfvec) LIMIT 6"),
        {"q": help_index._vector_literal(embeddings_client.embed(["x"], "query")[0])}))
    assert "ix_help_chunks_embedding_hnsw" in plan, plan

    stored = {cid: [float(x) for x in vec.strip("[]").split(",")] for cid, vec in session.execute(
        text("SELECT id, embedding::text FROM help_chunks"))}
    misses = []
    for qid in FIXED_QUERIES:
        item = golden[qid]
        vector = embeddings_client.embed([item["question"]], "query")[0]
        hits = help_index.vector_search(session, vector, 6)
        if hits[0][0] not in item["expected"]:
            misses.append(f"{qid}: {item['question']!r} -> {hits[0][0]}")
        # HNSW order == an exact cosine scan over the stored (half-precision) vectors.
        exact = sorted(stored, key=lambda cid: -embeddings_client._dot(vector, stored[cid]))
        assert [cid for cid, _ in hits[:3]] == exact[:3], qid
    assert misses == [], "\n".join(misses)


def test_vendor_down_then_recovered(session, monkeypatch):
    def down(documents, input_type="document"):
        raise embeddings_client.EmbeddingsUnavailable("Voyage /contextualizedembeddings HTTP 503")

    monkeypatch.setattr(embeddings_client, "embed_documents", down)
    failed = reindex.run(session, allow_mock=True, directory=HELP)
    assert failed.added and failed.embedded == [] and len(failed.pending) == len(failed.added)
    assert session.execute(text("SELECT count(*) FROM help_chunks")).scalar() == len(failed.added)
    assert session.execute(text(
        "SELECT count(*) FROM help_chunks WHERE body_tsv @@ plainto_tsquery('english', 'cancel')"
    )).scalar() > 0, "full-text search works without vectors"

    monkeypatch.undo()
    monkeypatch.setattr(settings, "embeddings_mode", "mock")
    recovered = reindex.run(session, allow_mock=True, directory=HELP)
    assert recovered.added == [] and len(recovered.embedded) == len(failed.added)


def test_without_a_key_and_without_allow_mock_nothing_is_embedded(session):
    result = reindex.run(session, allow_mock=False, directory=HELP)
    assert result.added and result.embedded == []
    assert "VOYAGE_API_KEY" in result.embedding_note
    assert session.execute(text(
        "SELECT count(*) FROM help_chunks WHERE embedding IS NOT NULL")).scalar() == 0


def test_downgrade_drops_the_table(scratch_url, session):
    _alembic(scratch_url, "downgrade", "0093_playbook_scores_owner")
    assert session.execute(text("SELECT to_regclass('help_chunks')")).scalar() is None
    _alembic(scratch_url, "upgrade", "head")
