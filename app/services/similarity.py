"""Strategy similarity — TF-IDF cosine similarity in pure Python (M8).

Reconstructed for the combined build to the original contract used by
app/api/playbook.py:

    StrategySimilarityIndex.find_similar(query, db, user_id=..., top_n=...)
        -> list[dict]  (strategy_id, product_id, product_name, similarity, status)

Design constraints carried over from the M8 delivery:
  * stdlib only — `math` + `collections`; no scikit-learn / numpy
  * user-scoped: only the requesting user's strategies are searchable
    (cross-tenant isolation)
  * corpus = product name + description + (optional) strategy document head
  * graceful empty handling: no strategies → []
"""
from __future__ import annotations

import math
import re
from collections import Counter

from sqlalchemy import text

__all__ = ["StrategySimilarityIndex", "tokenize", "cosine_similarity"]

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Minimal english stop list — enough to stop trivial words dominating scores
# without pulling in a dependency.
_STOP = frozenset("""
a an and are as at be by for from has have i in is it its of on or our that
the this to was we were will with you your
""".split())


def tokenize(text_: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text_ or "").lower())
            if len(t) > 1 and t not in _STOP]


def _tf(tokens: list[str]) -> dict[str, float]:
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = float(len(tokens))
    return {term: c / total for term, c in counts.items()}


def _idf(docs_tokens: list[list[str]]) -> dict[str, float]:
    n_docs = len(docs_tokens)
    df: Counter = Counter()
    for tokens in docs_tokens:
        df.update(set(tokens))
    # Smoothed IDF — never zero, never negative.
    return {term: math.log((1 + n_docs) / (1 + dfc)) + 1.0
            for term, dfc in df.items()}


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    return {term: w * idf.get(term, 0.0) for term, w in _tf(tokens).items()}


def cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
    if not v1 or not v2:
        return 0.0
    # Iterate the smaller vector for the dot product.
    if len(v2) < len(v1):
        v1, v2 = v2, v1
    dot = sum(w * v2.get(term, 0.0) for term, w in v1.items())
    n1 = math.sqrt(sum(w * w for w in v1.values()))
    n2 = math.sqrt(sum(w * w for w in v2.values()))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return dot / (n1 * n2)


class StrategySimilarityIndex:
    """Stateless index — corpus is small (one user's strategies), so it is
    built per request rather than cached. If a user grows past ~10k
    strategies, move the vectors to Redis keyed by strategy id."""

    @classmethod
    def find_similar(
        cls,
        query: str,
        db,
        user_id: str,
        top_n: int = 5,
    ) -> list[dict]:
        rows = db.execute(text("""
            SELECT s.id            AS strategy_id,
                   s.status        AS status,
                   s.strategy_document AS document,
                   p.id            AS product_id,
                   p.name          AS product_name,
                   p.description   AS product_description
            FROM strategies s
            JOIN products p ON p.id = s.product_id
            WHERE p.user_id = :uid
            ORDER BY s.created_at DESC
            LIMIT 500
        """), {"uid": user_id}).mappings().all()

        if not rows:
            return []

        docs_tokens: list[list[str]] = []
        for r in rows:
            doc_head = (r["document"] or "")[:2000]  # cap document contribution
            docs_tokens.append(
                tokenize(f"{r['product_name']} {r['product_description']} {doc_head}")
            )

        query_tokens = tokenize(query)
        idf = _idf(docs_tokens + [query_tokens])
        query_vec = _tfidf_vector(query_tokens, idf)

        scored: list[dict] = []
        for r, tokens in zip(rows, docs_tokens):
            sim = cosine_similarity(query_vec, _tfidf_vector(tokens, idf))
            if sim <= 0.0:
                continue
            scored.append({
                "strategy_id": str(r["strategy_id"]),
                "product_id": str(r["product_id"]),
                "product_name": r["product_name"],
                "status": str(r["status"]),
                "similarity": round(sim, 4),
            })

        scored.sort(key=lambda d: d["similarity"], reverse=True)
        return scored[:top_n]
