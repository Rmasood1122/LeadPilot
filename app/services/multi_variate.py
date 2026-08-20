"""
Multi-variate A/B/C/D testing — up to MV_MAX_VARIANTS variants.

Statistical method:
  1. Kruskal-Wallis H-test for initial multi-group significance.
     Non-parametric — no normality assumption; appropriate for
     conversion rate data with small samples per group.
  2. Pairwise Mann-Whitney U post-hoc tests with Bonferroni correction
     on all k*(k-1)/2 pairs to determine which pairs differ.
  3. Winner declared only when:
     (a) Kruskal-Wallis p < 0.05 overall
     (b) Best vs second-best pairwise passes Bonferroni-corrected threshold
     (c) Same lift + harm guards from M8 Ch2 hold

All formulas implemented directly (no scipy, no external stats libraries).

# TODO: These approximations are good for n>5 per group. For very small
#        samples (n<5) treat results as inconclusive rather than incorrect.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from app.core.logging import get_logger

logger = get_logger("services.multi_variate")


@dataclass
class PerVariantStats:
    variant: str
    rate: float
    sample_size: int
    event_count: int
    rank: int                    # 1 = best
    effective_n: Optional[float] = None


@dataclass
class PairwiseResult:
    variant_a: str
    variant_b: str
    p_value: float
    corrected_threshold: float   # Bonferroni-corrected significance level
    significant: bool            # p_value < corrected_threshold


@dataclass
class MultiVariateResult:
    strategy_id: str
    variants: list[str]
    metric: str
    per_variant_stats: dict[str, PerVariantStats]
    overall_significant: bool
    overall_p_value: float
    pairwise_results: list[PairwiseResult]
    winner: Optional[str]
    runner_up: Optional[str]
    harm_flags: dict[str, bool]  # variant → True if harm metric is elevated
    recommendation: str


# ---------------------------------------------------------------------------
# Core statistics — pure Python / math module
# ---------------------------------------------------------------------------

def _rank_all(groups: dict[str, list[int]]) -> dict[str, list[float]]:
    """
    Assign ranks to all observations across all groups combined.
    Tied values receive the average of their rank positions.
    Returns {variant: [ranks for that variant's observations]}.
    """
    # Build (value, variant, position) list
    all_obs: list[tuple[int, str]] = []
    for variant, obs in groups.items():
        for v in obs:
            all_obs.append((v, variant))

    # Sort by value
    all_obs.sort(key=lambda x: x[0])
    n_total = len(all_obs)

    # Assign ranks with tie handling
    ranked: list[tuple[str, float]] = []
    i = 0
    while i < n_total:
        j = i
        while j < n_total and all_obs[j][0] == all_obs[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0  # 1-indexed average
        for k in range(i, j):
            ranked.append((all_obs[k][1], avg_rank))
        i = j

    # Group by variant
    result: dict[str, list[float]] = {v: [] for v in groups}
    for variant, rank in ranked:
        result[variant].append(rank)
    return result


def _kruskal_wallis_h(groups: dict[str, list[int]]) -> tuple[float, float]:
    """
    Kruskal-Wallis H statistic and approximate p-value via chi-squared distribution.
    Groups: {variant: list of 0/1 outcome values}
    Returns (H, p_value).
    """
    k = len(groups)
    n_total = sum(len(v) for v in groups.values())
    if n_total == 0 or k < 2:
        return 0.0, 1.0

    ranked = _rank_all(groups)

    # H = 12 / (N*(N+1)) * Σ (R_i^2 / n_i) - 3*(N+1)
    sum_term = sum(
        (sum(r) ** 2) / len(ranked[variant])
        for variant, r in ranked.items()
        if len(ranked[variant]) > 0
    )
    H = (12.0 / (n_total * (n_total + 1))) * sum_term - 3 * (n_total + 1)

    # Tie correction
    all_vals = [v for obs in groups.values() for v in obs]
    from collections import Counter
    counts = Counter(all_vals)
    tie_correction = sum(c ** 3 - c for c in counts.values())
    correction = 1.0 - tie_correction / (n_total ** 3 - n_total) if n_total > 1 else 1.0
    if correction != 0:
        H = H / correction

    # p-value from chi-squared CDF with df = k-1
    p = _chi2_sf(H, k - 1)
    return H, p


def _mann_whitney_u(a: list[int], b: list[int]) -> tuple[float, float]:
    """
    Mann-Whitney U test. Returns (U, approximate p-value two-tailed).
    Uses normal approximation (valid when n_a, n_b > 5).
    """
    n_a, n_b = len(a), len(b)
    if n_a == 0 or n_b == 0:
        return 0.0, 1.0

    # Count pairs where a_i > b_j
    U_a = sum(1 for ai in a for bj in b if ai > bj) + 0.5 * sum(1 for ai in a for bj in b if ai == bj)
    U_b = n_a * n_b - U_a

    U = min(U_a, U_b)
    mu_U = n_a * n_b / 2.0
    sigma_U = math.sqrt(n_a * n_b * (n_a + n_b + 1) / 12.0)

    if sigma_U == 0:
        return U, 1.0

    z = (U - mu_U) / sigma_U
    p_one_tail = _normal_sf(abs(z))
    return U, 2 * p_one_tail  # two-tailed


def _chi2_sf(x: float, df: int) -> float:
    """
    Survival function of chi-squared distribution (1 - CDF).
    Uses regularized incomplete gamma function approximation.
    # TODO: This is a numerical approximation. For production use with
    #        very small p-values (< 1e-6), verify against a reference.
    """
    if x <= 0:
        return 1.0
    return _gammaincc(df / 2.0, x / 2.0)


def _gammaincc(a: float, x: float) -> float:
    """Upper regularized incomplete gamma function via continued fraction."""
    if x < 0:
        return 1.0
    if x == 0:
        return 1.0
    # Use series expansion for small x, continued fraction for large x
    if x < a + 1:
        return 1.0 - _gammainc_series(a, x)
    return _gammainc_cf(a, x)


def _gammainc_series(a: float, x: float) -> float:
    """Regularized incomplete gamma via series expansion."""
    if x == 0:
        return 0.0
    ap = a
    delta = 1.0 / a
    total = delta
    for _ in range(200):
        ap += 1
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * 1e-12:
            break
    return total * math.exp(-x + a * math.log(x) - _lgamma(a))


def _gammainc_cf(a: float, x: float) -> float:
    """Regularized incomplete gamma via Lentz continued fraction."""
    FPMIN = 1e-300
    b = x + 1.0 - a
    c = 1.0 / FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, 201):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < FPMIN:
            d = FPMIN
        c = b + an / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return math.exp(-x + a * math.log(x) - _lgamma(a)) * h


def _lgamma(x: float) -> float:
    return math.lgamma(x)


def _normal_sf(z: float) -> float:
    """One-sided p-value from standard normal: P(Z > z)."""
    return 0.5 * math.erfc(z / math.sqrt(2))


# ---------------------------------------------------------------------------
# Multi-variate comparison
# ---------------------------------------------------------------------------

def compare_multi_variants(
    strategy_id: str,
    variants: list[str],
    metric: str = "meeting_rate",
    harm_metric: str = "unsubscribe_rate",
    harm_ceiling: float = 0.05,   # if variant's unsubscribe_rate exceeds this → harm flag
    min_lift: Optional[float] = None,
    alpha: float = 0.05,
    db_session=None,
) -> MultiVariateResult:
    """
    Multi-variate test for up to MV_MAX_VARIANTS variants.

    Fetches outcome data from DB, runs Kruskal-Wallis, then pairwise
    Mann-Whitney U with Bonferroni correction.
    """
    from app.core.config import settings

    if min_lift is None:
        min_lift = settings.AB_MIN_LIFT

    max_variants = getattr(settings, "MV_MAX_VARIANTS", 5)
    variants = variants[:max_variants]

    k = len(variants)
    if k < 2:
        return MultiVariateResult(
            strategy_id=strategy_id,
            variants=variants,
            metric=metric,
            per_variant_stats={},
            overall_significant=False,
            overall_p_value=1.0,
            pairwise_results=[],
            winner=None,
            runner_up=None,
            harm_flags={},
            recommendation="Need at least 2 variants to compare.",
        )

    # Fetch per-variant aggregates from DB
    variant_data = _fetch_variant_data(strategy_id, variants, db_session)

    per_variant_stats: dict[str, PerVariantStats] = {}
    groups: dict[str, list[int]] = {}  # {variant: [0/1 outcome per send]}
    harm_flags: dict[str, bool] = {}

    for v in variants:
        data = variant_data.get(v, {"sends": 0, "replies": 0, "bookings": 0, "unsubscribes": 0})
        sends = max(data["sends"], 1)
        replies = data["replies"]
        bookings = data["bookings"]
        unsubs = data["unsubscribes"]

        rate = bookings / sends if metric == "meeting_rate" else replies / sends
        unsub_rate = unsubs / sends

        harm_flags[v] = unsub_rate > harm_ceiling

        per_variant_stats[v] = PerVariantStats(
            variant=v,
            rate=round(rate, 4),
            sample_size=sends,
            event_count=bookings if metric == "meeting_rate" else replies,
            rank=0,  # assigned below
        )

        # Build binary outcome array for non-parametric tests
        event_count = per_variant_stats[v].event_count
        non_event_count = sends - event_count
        groups[v] = [1] * event_count + [0] * non_event_count

    # Assign ranks by rate
    sorted_variants = sorted(variants, key=lambda v: per_variant_stats[v].rate, reverse=True)
    for i, v in enumerate(sorted_variants):
        per_variant_stats[v].rank = i + 1

    # Kruskal-Wallis overall test
    H, overall_p = _kruskal_wallis_h(groups)
    overall_significant = overall_p < alpha

    # Pairwise Mann-Whitney U with Bonferroni correction
    n_pairs = k * (k - 1) // 2
    bonferroni_threshold = alpha / max(n_pairs, 1)

    pairwise_results: list[PairwiseResult] = []
    for i in range(len(variants)):
        for j in range(i + 1, len(variants)):
            va, vb = variants[i], variants[j]
            _, p = _mann_whitney_u(groups[va], groups[vb])
            pairwise_results.append(PairwiseResult(
                variant_a=va,
                variant_b=vb,
                p_value=round(p, 6),
                corrected_threshold=round(bonferroni_threshold, 6),
                significant=p < bonferroni_threshold,
            ))

    # Determine winner
    winner: Optional[str] = None
    runner_up: Optional[str] = None

    if overall_significant and len(sorted_variants) >= 2:
        best = sorted_variants[0]
        second = sorted_variants[1]

        # Check best vs second-best pairwise result
        best_vs_second = next(
            (pr for pr in pairwise_results
             if set([pr.variant_a, pr.variant_b]) == {best, second}),
            None,
        )
        best_passes_pairwise = best_vs_second is not None and best_vs_second.significant

        # Lift check: best must be at least AB_MIN_LIFT better than second
        rate_best = per_variant_stats[best].rate
        rate_second = per_variant_stats[second].rate
        relative_lift = (rate_best - rate_second) / max(rate_second, 1e-9)
        lift_ok = relative_lift >= min_lift

        # Harm check
        harm_ok = not harm_flags.get(best, False)

        if best_passes_pairwise and lift_ok and harm_ok:
            winner = best
            runner_up = second

    # Recommendation string
    if winner:
        recommendation = (
            f"Promote '{winner}' as default variant "
            f"({per_variant_stats[winner].rate:.1%} vs {per_variant_stats[runner_up].rate:.1%} "
            f"for '{runner_up}'). All gates passed."
        )
    elif not overall_significant:
        recommendation = "No significant difference between variants. Collect more data."
    elif harm_flags.get(sorted_variants[0], False):
        recommendation = f"Best variant '{sorted_variants[0]}' has elevated harm metric. No promotion."
    else:
        recommendation = "Significant difference found but lift/pairwise thresholds not met. Monitor."

    return MultiVariateResult(
        strategy_id=strategy_id,
        variants=variants,
        metric=metric,
        per_variant_stats=per_variant_stats,
        overall_significant=overall_significant,
        overall_p_value=round(overall_p, 6),
        pairwise_results=pairwise_results,
        winner=winner,
        runner_up=runner_up,
        harm_flags=harm_flags,
        recommendation=recommendation,
    )


def _fetch_variant_data(
    strategy_id: str,
    variants: list[str],
    db_session,
) -> dict[str, dict]:
    """Pull per-variant aggregate counts from the outcomes table."""
    if db_session is None:
        return {v: {"sends": 0, "replies": 0, "bookings": 0, "unsubscribes": 0} for v in variants}

    from sqlalchemy import text
    sql = text("""
        SELECT
            variant,
            COUNT(*) FILTER (WHERE event = 'sent') AS sends,
            COUNT(*) FILTER (WHERE event = 'replied') AS replies,
            COUNT(*) FILTER (WHERE event = 'booked') AS bookings,
            COUNT(*) FILTER (WHERE event = 'unsubscribed') AS unsubscribes
        FROM outcomes
        WHERE strategy_id = :sid
          AND variant = ANY(:variants)
        GROUP BY variant
    """)
    try:
        rows = db_session.execute(sql, {"sid": strategy_id, "variants": variants}).mappings().all()
        result = {v: {"sends": 0, "replies": 0, "bookings": 0, "unsubscribes": 0} for v in variants}
        for row in rows:
            result[row["variant"]] = {
                "sends": row["sends"] or 0,
                "replies": row["replies"] or 0,
                "bookings": row["bookings"] or 0,
                "unsubscribes": row["unsubscribes"] or 0,
            }
        return result
    except Exception as e:
        logger.error("multi_variate.fetch_failed", error=str(e))
        return {v: {"sends": 0, "replies": 0, "bookings": 0, "unsubscribes": 0} for v in variants}
