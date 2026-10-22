"""Build the help-center search index (help_chunks) from docs/help-center.

    python -m scripts.help_center.reindex                  # sync the database, embed changes
    python -m scripts.help_center.reindex --check          # exit 1 if the database is stale
    python -m scripts.help_center.reindex --write-manifest # rewrite index_manifest.json
    python -m scripts.help_center.reindex --check-manifest # exit 1 if the manifest is stale (CI)

Idempotent: chunks are compared by content hash (app/services/help_index.py),
only new or changed chunks are written, and only articles with a new or
changed chunk -- or chunks with no vector from the current embedder -- are
sent to Voyage. A second run over the same corpus writes nothing and embeds
nothing. Every run prints a diff summary.

EMBEDDINGS
  live (VOYAGE_API_KEY set): vectors from voyage-context-4, metered as
       purpose "help_index" through usage_meter (no account: user_id NULL).
  no key: the text index is synced and vectors stay pending; mock vectors
       are written only with --allow-mock (tests, local development), so a
       production index never holds hash vectors that look like real ones.
  A vendor failure leaves the text index current and vectors pending; the
  exit code stays 0, because the BM25 path never depends on vectors.

DEPLOY
  scripts/render_api_entrypoint.sh runs this after `python -m app.db.migrate`
  and before uvicorn, and does not let it block the boot (see there).

Exit codes: 0 ok, 1 stale (--check / --check-manifest), 2 could not run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sqlalchemy import text  # noqa: E402

from app.services import embeddings_client, help_center, help_index  # noqa: E402

EXIT_OK, EXIT_STALE, EXIT_ERROR = 0, 1, 2

# pg_advisory_lock key: two API instances booting together must not both
# embed the same changes (the second waits, then finds nothing to do).
ADVISORY_LOCK_KEY = 0x48454C50  # "HELP"


def _rows(directory: Path | None = None) -> list[help_index.IndexRow]:
    return help_index.build_rows(help_center.load_corpus(directory))


def check_manifest(directory: Path | None = None,
                   path: Path = help_index.MANIFEST_PATH) -> list[str]:
    expected = help_index.manifest(_rows(directory))
    if not path.is_file():
        return [f"missing {path.relative_to(REPO)}"]
    return help_index.manifest_diff(expected, json.loads(path.read_text(encoding="utf-8")))


def write_manifest(directory: Path | None = None,
                   path: Path = help_index.MANIFEST_PATH) -> None:
    path.write_text(help_index.render_manifest(_rows(directory)), encoding="utf-8")


def run(session, *, allow_mock: bool = False, directory: Path | None = None
        ) -> help_index.SyncResult:
    """Sync `session`'s help_chunks to the corpus. Used by main() and tests."""
    from app.services import usage_meter  # noqa: PLC0415

    rows = _rows(directory)
    mode = embeddings_client.resolve_mode()
    embed = mode == "live" or allow_mock
    bind = session.get_bind()
    # The lock lives on its OWN connection: the session returns its connection
    # to the pool at every commit, and a session-level advisory lock taken on
    # it would be released on (or leak onto) whichever connection came back.
    lock = bind.connect() if bind.dialect.name == "postgresql" else None
    if lock is not None:
        lock.execute(text("SELECT pg_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY})
    try:
        with usage_meter.scope(session, purpose="help_index"):
            result = help_index.sync(
                session, rows, embed=embed, embedder=embeddings_client.embedder_id(),
                embed_documents=embeddings_client.embed_documents)
    finally:
        if lock is not None:
            lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
            lock.close()
    if not embed and result.pending and not result.embedding_note.startswith("no embedding"):
        result.embedding_note = "no VOYAGE_API_KEY (pass --allow-mock for hash vectors)"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true",
                       help="report what a sync would change; exit 1 if anything")
    group.add_argument("--write-manifest", action="store_true")
    group.add_argument("--check-manifest", action="store_true")
    parser.add_argument("--allow-mock", action="store_true",
                        help="write deterministic hash vectors when no Voyage key is set")
    args = parser.parse_args(argv)

    if args.write_manifest:
        write_manifest()
        print(f"wrote {help_index.MANIFEST_PATH.relative_to(REPO)}")
        return EXIT_OK
    if args.check_manifest:
        diff = check_manifest()
        if diff:
            print("help index manifest is stale relative to docs/help-center; run\n"
                  "  python -m scripts.help_center.reindex --write-manifest\n"
                  + "\n".join(diff))
            return EXIT_STALE
        print("help index manifest matches the corpus")
        return EXIT_OK

    from app.db.base import SessionLocal  # noqa: PLC0415

    session = SessionLocal()
    try:
        if args.check:
            diff = help_index.stale(session, _rows(), embeddings_client.embedder_id())
            print("\n".join(diff) if diff else "help_chunks is current")
            return EXIT_STALE if diff else EXIT_OK
        result = run(session, allow_mock=args.allow_mock)
        print(result.summary())
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001 -- reported, exit code says it
        session.rollback()
        print(f"reindex failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
