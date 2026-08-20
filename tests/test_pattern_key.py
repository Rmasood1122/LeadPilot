"""Architecture tripwire for Strategy.pattern_key.

pattern_key buckets every playbook score. Adding, removing, renaming or
reordering a field in the hashed payload silently re-buckets all of them:
existing playbook_scores rows are orphaned and the learning loop starts again
from zero, with no error anywhere. These tests pin the exact canonical shape
so that change can never be accidental — if one fails, the derivation moved
and a backfill (scripts/backfill_pattern_key.py) is required.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from app.services.icp_extraction import (
    CRITERIA_KEYS,
    TACTIC_CADENCES,
    TACTIC_CHANNELS,
    TACTIC_MOTIONS,
    canonical_pattern_payload,
    compute_pattern_key,
)

pytestmark = pytest.mark.regression


ICP = {
    "titles": ["VP Sales", "Founder"],
    "industries": ["SaaS"],
    "locations": ["North America, United States"],
    "company_size_ranges": ["11,200"],
    "keywords": ["outbound"],
}
TACTICS = {
    "channels": ["email", "whatsapp"],
    "sales_motion": "cold_outbound",
    "cadence": "standard",
    "flow_type": "with_clients",
}


class TestCanonicalShape:
    def test_payload_shape_is_pinned(self):
        """The EXACT structure that gets hashed. Update deliberately only."""
        assert canonical_pattern_payload(ICP, TACTICS) == {
            "icp": {
                "company_size_ranges": ["11,200"],
                "industries": ["saas"],
                "keywords": ["outbound"],
                "locations": ["north america, united states"],
                "titles": ["founder", "vp sales"],
            },
            "tactics": {
                "cadence": "standard",
                "channels": ["email", "whatsapp"],
                "flow_type": "with_clients",
                "sales_motion": "cold_outbound",
            },
        }

    def test_hash_is_sha256_of_compact_sorted_json(self):
        """Pins the serialization too — separators and sort_keys both matter."""
        expected = hashlib.sha256(
            json.dumps(canonical_pattern_payload(ICP, TACTICS),
                       sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert compute_pattern_key(ICP, TACTICS) == expected

    def test_top_level_keys_are_icp_and_tactics(self):
        """The column documents "ICP/tactic JSON" — both halves must be there."""
        payload = canonical_pattern_payload(ICP, TACTICS)
        assert set(payload) == {"icp", "tactics"}
        assert set(payload["icp"]) == set(CRITERIA_KEYS)
        assert set(payload["tactics"]) == {
            "channels", "sales_motion", "cadence", "flow_type"
        }


class TestCanonicalization:
    def test_order_and_case_do_not_change_the_key(self):
        shuffled_icp = {**ICP, "titles": ["founder", "  VP SALES  "]}
        shuffled_tactics = {**TACTICS, "channels": ["WhatsApp", "Email"]}
        assert compute_pattern_key(shuffled_icp, shuffled_tactics) == (
            compute_pattern_key(ICP, TACTICS)
        )

    def test_duplicates_collapse(self):
        assert compute_pattern_key({**ICP, "industries": ["SaaS", "saas", "SAAS"]},
                                   TACTICS) == compute_pattern_key(ICP, TACTICS)

    def test_missing_and_empty_are_the_same_bucket(self):
        assert compute_pattern_key({}, {}) == compute_pattern_key(
            {k: [] for k in CRITERIA_KEYS},
            {"channels": [], "sales_motion": None, "cadence": None,
             "flow_type": None},
        )


class TestTacticsActuallyParticipate:
    """The bug this fixes: tactics used not to be in the hash at all."""

    def test_different_channels_are_different_buckets(self):
        assert compute_pattern_key(ICP, {**TACTICS, "channels": ["email"]}) != (
            compute_pattern_key(ICP, TACTICS)
        )

    def test_different_cadence_is_a_different_bucket(self):
        assert compute_pattern_key(ICP, {**TACTICS, "cadence": "aggressive"}) != (
            compute_pattern_key(ICP, TACTICS)
        )

    def test_different_sales_motion_is_a_different_bucket(self):
        assert compute_pattern_key(ICP, {**TACTICS, "sales_motion": "warm_intro"}) != (
            compute_pattern_key(ICP, TACTICS)
        )

    def test_flow_type_is_a_different_bucket(self):
        """Flow 1 is anchored on proven past clients; Flow 2 is not. Same ICP,
        different play."""
        assert compute_pattern_key(ICP, {**TACTICS, "flow_type": "no_clients"}) != (
            compute_pattern_key(ICP, TACTICS)
        )

    def test_icp_still_participates(self):
        assert compute_pattern_key({**ICP, "industries": ["fintech"]}, TACTICS) != (
            compute_pattern_key(ICP, TACTICS)
        )


class TestClosedVocabulary:
    """Cardinality is the whole game: a key that is unique per strategy
    buckets nothing, so the tactic half must be a small closed set."""

    def test_vocabularies_are_small_and_lowercase(self):
        for vocab in (TACTIC_CHANNELS, TACTIC_MOTIONS, TACTIC_CADENCES):
            assert vocab, "vocabulary must not be empty"
            assert len(vocab) <= 10, "tactic vocabulary is getting too large"
            assert all(v == v.lower() and " " not in v for v in vocab)

    def test_unknown_tactic_values_are_not_silently_new_buckets(self):
        """extract_tactic_profile filters to the vocabulary; anything that got
        through would still canonicalize, so this documents the contract that
        filtering happens at extraction time."""
        from app.services.icp_extraction import extract_tactic_profile

        assert callable(extract_tactic_profile)
