# Help AI v2, Phase 2: indexing

Date: 2026-10-22. Decisions: `DECISIONS.md` HELPAI-VENDOR, HELPAI-RERANK, HELPAI-INDEX.

## What exists after this phase

| Piece | File | Notes |
|---|---|---|
| Voyage gateway | `app/services/embeddings_client.py` | `embed(texts, input_type)`, `embed_documents(documents)` (contextualized), `rerank(query, docs, top_k)`. Mock mode = deterministic feature hashing. Timeout 15 s per attempt, 3 attempts on network/timeout/408/409/425/429/5xx with 1 s, 2 s backoff. Every live call is metered through `usage_meter` as `voyage` or `voyage_rerank`. Failures raise `EmbeddingsUnavailable`. |
| Prices | `app/services/system_settings.py` | `voyage_embed_cost_per_mtok` 0.12, `voyage_rerank_cost_per_mtok` 0.02 (admin-editable; input tokens only). |
| Settings | `app/config.py` | `VOYAGE_API_KEY`, `EMBEDDINGS_MODE` (empty = auto), `VOYAGE_EMBED_MODEL` = voyage-context-4, `VOYAGE_EMBED_DIMENSION` = 1024, `VOYAGE_RERANK_MODEL` = rerank-3-lite, `VOYAGE_TIMEOUT_SECONDS`, `VOYAGE_MAX_ATTEMPTS`. |
| Table | `alembic/versions/0094_help_chunks.py`, `app/db/models.py` `HelpChunk` | Columns per the brief. `embedding halfvec(1024)` with HNSW (`halfvec_cosine_ops`, m=16, ef_construction=64), and `body_tsv` generated tsvector with GIN, are PostgreSQL only and not mapped (the SQLite suite creates the mapped columns only). Without pgvector ≥ 0.7 the table is created without `embedding`. `context_sentence` stays empty (contextual embeddings). |
| Index logic | `app/services/help_index.py` | Rows = `help_center` chunks (same chunker, same ids). Content hash = chunk embedding text + its article's. Sync, staleness, manifest, and `vector_search` for Phase 3. |
| CLI | `scripts/help_center/reindex.py` | Sync, `--check`, `--write-manifest`, `--check-manifest`, `--allow-mock`. Prints a diff summary. Postgres advisory lock on its own connection. Metered as purpose `help_index` (counted only, no account). |
| Manifest | `scripts/help_center/index_manifest.json` | 296 chunks. Regenerate after any corpus edit. |
| Deploy hook | `scripts/render_api_entrypoint.sh` | See below. |

## The Render hook (exact)

`render.yaml` → `leadpilot-api` → `dockerCommand: bash scripts/render_api_entrypoint.sh`. That script now runs:

```bash
python -m app.db.migrate                      # set -e: a failed migration stops the boot
timeout 180 python -m scripts.help_center.reindex \
  || echo "[api-entrypoint] help-center reindex did not complete (exit $?); serving with the existing index"
exec uvicorn app.main:app ...
```

- **Order.** Migrations first, so `help_chunks` exists.
- **Not preDeployCommand.** That is paid-plan only on Render (see the comments in `render.yaml`).
- **Non-fatal.** The `||` keeps `set -e` from stopping the API when the reindex fails. BM25 needs no index.
- **Bounded.** `timeout 180` caps the boot delay.

What a deploy does:

- **No `VOYAGE_API_KEY` (current state).** The text rows are synced, vectors stay pending, and the log says so.
- **Key set.** Changed articles are embedded; unchanged deploys embed nothing.

To run it by hand on the Render shell:

```bash
python -m scripts.help_center.reindex           # sync + embed changes
python -m scripts.help_center.reindex --check   # exit 1 if the database is stale
```

## CI staleness check

`tests/help_center/test_help_index.py::TestManifest::test_committed_manifest_matches_the_corpus` runs on every CI run, in the offline suite. It rebuilds `{chunk id: content hash}` from `docs/help-center` and fails if `index_manifest.json` differs.

Fix: `python -m scripts.help_center.reindex --write-manifest`, then commit the result.

The database copy is brought to the same state by the deploy hook, and checked with `reindex --check`.

## Exit gate 2

| Gate | Test | Result 2026-10-22 |
|---|---|---|
| reindex twice → zero re-embeds | `tests/integration/test_help_index_pg.py::test_second_reindex_embeds_nothing` (also: one edited article re-embeds exactly that article) | pass, local PostgreSQL 16.15 + pgvector 0.8.1 |
| PG vector search returns the expected chunk for 10 fixed queries | `test_vector_search_finds_the_expected_chunk` (HNSW used per EXPLAIN; top-3 equal to an exact cosine scan) | pass, 10/10 top-1 |

The vectors are mock (feature hashes), because no Voyage key is available here.

- **What this proves:** the index machinery: storage, hashing, idempotency, and HNSW cosine ordering.
- **What it does not prove:** Voyage's retrieval quality, which is **not verified**.

For context, mock-vector recall over all 151 golden questions is 77 top-1 and 130 in the top 6. The 10 fixed queries were chosen from questions that are top-1 under mock, one per article area, so they are a machinery check, not a quality claim.

## Not done here (later phases)

- **Phase 3:** query embedding at question time, hybrid BM25 + dense with RRF, rerank, `retrieval_mode`.
- **Article 43 (subprocessors):** gains Voyage when user questions are first sent to it, in Phase 3. Phase 2 sends only help-center text.
- **Live quality:** measured in Phase 5 with a key.
