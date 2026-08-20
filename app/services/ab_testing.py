"""A/B testing — binary variant comparison with auto-promotion gating (M8-C2).

Reconstructed for the combined build to the original M8-C2 contract:

    compare_variants(strategy_id, variant_a, variant_b, db_session) -> ABTestResult
        .winner  — the winning variant label, or None if no promotion allowed

Statistics: two-proportion z-test implemented with ONLY the stdlib
(`math.erfc`) — no scipy dependency, by design.

Auto-promotion requires ALL FOUR gates to pass (harm-guard convention used
across M8):

    Gate 1 — sample size:  each variant has >= settings.PLAYBOOK_MIN_SAMPLE sends
    Gate 2 — significance: two-sided p-value < settings.AB_SIGNIFICANCE_THRESHOLD
    Gate 3 — minimum lift: relative lift of winner >= settings.AB_MIN_LIFT
    Gate 4 — harm ceiling: winner's harm rate (bounced + unsubscribed +
             opted_out per send) <= AB_HARM_CEILING (default 0.05)

If any gate fails, .winner is None and the reason is recorded — the sweep in
app.workers.learning_tasks simply skips promotion.

In-flight safety: this module only READS the outcomes log. Promotion (done by
the caller) updates strategies.default_variant, which affects future message
rendering only — rows where sent_at IS NOT NULL are never modified.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text

__all__ = ["ABTestResult", "VariantStats", "compare_variants", "two_proportion_z_test"]


# --------------------------------------------------------------------------- #
# Statistics (stdlib only)
# --------------------------------------------------------------------------- #

def _normal_sf(z: float) -> float:
    """Survival function of the standard normal: P(Z > z), via erfc."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def two_proportion_z_test(
    successes_a: int, n_a: int, successes_b: int, n_b: int
) -> tuple[float, float]:
    """Two-sided two-proportion z-test (pooled). Returns (z, p_value).

    Degenerate inputs (empty samples, zero pooled variance) return (0.0, 1.0)
    — i.e. "no evidence", which fails Gate 2 and safely blocks promotion.
    """
    if n_a <= 0 or n_b <= 0:
        return 0.0, 1.0
    p_a = successes_a / n_a
    p_b = successes_b / n_b
    pooled = (successes_a + successes_b) / (n_a + n_b)
    var = pooled * (1.0 - pooled) * (1.0 / n_a + 1.0 / n_b)
    if var <= 0.0:
        return 0.0, 1.0
    z = (p_a - p_b) / math.sqrt(var)
    p_value = 2.0 * _normal_sf(abs(z))
    return z, p_value


# --------------------------------------------------------------------------- #
# Result containers
# --------------------------------------------------------------------------- #

@dataclass
class VariantStats:
    variant: str
    sends: int = 0
    replies: int = 0
    bookings: int = 0
    harms: int = 0  # bounced + unsubscribed + opted_out

    @property
    def conversion_rate(self) -> float:
        return (self.bookings / self.sends) if self.sends else 0.0

    @property
    def reply_rate(self) -> float:
        return (self.replies / self.sends) if self.sends else 0.0

    @property
    def harm_rate(self) -> float:
        return (self.harms / self.sends) if self.sends else 0.0


@dataclass
class ABTestResult:
    strategy_id: str
    variant_a: VariantStats
    variant_b: VariantStats
    metric: str = "booked"
    z_score: float = 0.0
    p_value: float = 1.0
    lift: float = 0.0                    # relative lift of the leader
    winner: Optional[str] = None         # None => no promotion
    gates: dict = field(default_factory=dict)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "metric": self.metric,
            "z_score": round(self.z_score, 4),
            "p_value": round(self.p_value, 6),
            "lift": round(self.lift, 4),
            "winner": self.winner,
            "gates": self.gates,
            "reason": self.reason,
            "variants": {
                self.variant_a.variant: {
                    "sends": self.variant_a.sends,
                    "replies": self.variant_a.replies,
                    "bookings": self.variant_a.bookings,
                    "harm_rate": round(self.variant_a.harm_rate, 4),
                },
                self.variant_b.variant: {
                    "sends": self.variant_b.sends,
                    "replies": self.variant_b.replies,
                    "bookings": self.variant_b.bookings,
                    "harm_rate": round(self.variant_b.harm_rate, 4),
                },
            },
        }


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #

_HARM_EVENTS = ("bounced", "unsubscribed", "opted_out")


def _load_variant_stats(db_session, strategy_id: str, variant: str) -> VariantStats:
    row = db_session.execute(text("""
        SELECT
            SUM(CASE WHEN event = 'sent'   THEN 1 ELSE 0 END) AS sends,
            SUM(CASE WHEN event = 'replied' THEN 1 ELSE 0 END) AS replies,
            SUM(CASE WHEN event = 'booked' THEN 1 ELSE 0 END) AS bookings,
            SUM(CASE WHEN event IN ('bounced', 'unsubscribed', 'opted_out')
                     THEN 1 ELSE 0 END) AS harms
        FROM outcomes
        WHERE strategy_id = :sid AND variant = :variant
    """), {"sid": strategy_id, "variant": variant}).mappings().first()
    return VariantStats(
        variant=variant,
        sends=int(row["sends"] or 0),
        replies=int(row["replies"] or 0),
        bookings=int(row["bookings"] or 0),
        harms=int(row["harms"] or 0),
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def compare_variants(
    strategy_id: str,
    variant_a: str,
    variant_b: str,
    db_session,
    metric: str = "booked",
) -> ABTestResult:
    """Compare two variants of a strategy on the booking (meeting) rate.

    Returns an ABTestResult whose .winner is set ONLY if all four promotion
    gates pass. Reads settings lazily so tests can monkeypatch them.
    """
    from app.core.config import settings

    min_sample = int(getattr(settings, "PLAYBOOK_MIN_SAMPLE", 30))
    alpha = float(getattr(settings, "AB_SIGNIFICANCE_THRESHOLD", 0.05))
    min_lift = float(getattr(settings, "AB_MIN_LIFT", 0.10))
    harm_ceiling = float(getattr(settings, "AB_HARM_CEILING", 0.05))

    a = _load_variant_stats(db_session, strategy_id, variant_a)
    b = _load_variant_stats(db_session, strategy_id, variant_b)

    result = ABTestResult(strategy_id=strategy_id, variant_a=a, variant_b=b,
                          metric=metric)

    # ---- Gate 1: sample size (per variant) --------------------------------
    gate1 = a.sends >= min_sample and b.sends >= min_sample
    result.gates["sample_size"] = gate1
    if not gate1:
        result.reason = (
            f"gate 1 failed: need >= {min_sample} sends per variant "
            f"(got {a.sends} / {b.sends})"
        )
        return result

    # ---- Gate 2: statistical significance ---------------------------------
    z, p = two_proportion_z_test(a.bookings, a.sends, b.bookings, b.sends)
    result.z_score, result.p_value = z, p
    gate2 = p < alpha
    result.gates["significance"] = gate2

    leader, trailer = (a, b) if a.conversion_rate >= b.conversion_rate else (b, a)

    if not gate2:
        result.reason = f"gate 2 failed: p={p:.4f} >= alpha={alpha}"
        return result

    # ---- Gate 3: minimum relative lift ------------------------------------
    if trailer.conversion_rate > 0:
        lift = (leader.conversion_rate - trailer.conversion_rate) / trailer.conversion_rate
    else:
        # Trailer converted nothing; any leader conversion is treated as full lift.
        lift = 1.0 if leader.conversion_rate > 0 else 0.0
    result.lift = lift
    gate3 = lift >= min_lift
    result.gates["min_lift"] = gate3
    if not gate3:
        result.reason = f"gate 3 failed: lift={lift:.3f} < min_lift={min_lift}"
        return result

    # ---- Gate 4: harm ceiling (winner must not win by burning the list) ---
    gate4 = leader.harm_rate <= harm_ceiling
    result.gates["harm_ceiling"] = gate4
    if not gate4:
        result.reason = (
            f"gate 4 failed: winner harm_rate={leader.harm_rate:.3f} "
            f"> ceiling={harm_ceiling}"
        )
        return result

    result.winner = leader.variant
    result.reason = "all four gates passed"
    return result
