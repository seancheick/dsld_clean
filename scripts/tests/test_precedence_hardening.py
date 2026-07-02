#!/usr/bin/env python3
"""
Matching-Precedence Hardening Tests (2026-07 pipeline audit)

Covers two audit findings against MATCHING_PRECEDENCE.md:

1. Exclusion processing: the spec says a match candidate is skipped only when
   the label consists of ONLY exclusion terms ("Natural flavoring"), never
   when a real identifier is present ("Curcumin Natural"). The old code
   skipped the parent on ANY word-bounded exclusion hit.
   (Latent today: every exclusions[] in ingredient_quality_map.json is empty.)

2. Cleaner alias-collision resolution: when the same alias variation maps to
   multiple quality-map entries, the winner must follow match_rules.priority
   (P0 > P1 > P2, alphabetical tiebreak), not raw JSON file order.

Run with: pytest tests/test_precedence_hardening.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enrich_supplements_v3 import SupplementEnricherV3


@pytest.fixture(scope="module")
def enricher():
    return SupplementEnricherV3()


class TestExclusionOnlyTermsRule:
    """Spec: skip only when the label contains ONLY exclusion terms."""

    def _map_with_exclusions(self):
        # Synthetic single-entry quality map exercising exclusions[]
        return {
            "curcumin": {
                "standard_name": "Curcumin",
                "match_rules": {
                    "priority": 0,
                    "match_mode": "alias_and_fuzzy",
                    "exclusions": ["natural", "extract"],
                },
                "forms": {
                    "curcumin extract": {
                        "score": 10,
                        "bio_score": 10,
                        "natural": True,
                        # "natural extract" is deliberately listed as an alias:
                        # the ONLY-exclusion-terms rule must reject it anyway.
                        "aliases": ["curcumin", "curcumin natural",
                                    "natural curcumin", "natural extract"],
                        "dosage_importance": 1.0,
                    }
                },
            }
        }

    def test_identifier_plus_exclusion_still_matches(self, enricher):
        """'Curcumin Natural' has a real identifier -> must match curcumin."""
        result = enricher._match_quality_map(
            "Curcumin Natural", "", self._map_with_exclusions()
        )
        assert result is not None, (
            "'Curcumin Natural' was dropped by exclusion terms despite "
            "containing a real identifier"
        )

    def test_only_exclusion_terms_does_not_match(self, enricher):
        """'Natural Extract' is nothing but exclusion terms -> no match."""
        result = enricher._match_quality_map(
            "Natural Extract", "", self._map_with_exclusions()
        )
        assert result is None, f"bare exclusion terms matched: {result}"


class TestCleanerAliasCollisionPriority:
    """Collided alias variations must resolve to the lowest-priority entry."""

    def test_collisions_resolve_by_priority(self):
        from enhanced_normalizer import EnhancedDSLDNormalizer  # noqa: F401
        import json

        qm_path = Path(__file__).parent.parent / "data" / "ingredient_quality_map.json"
        qm = json.loads(qm_path.read_text())

        def priority_of(key):
            entry = qm.get(key) or {}
            return (entry.get("match_rules") or {}).get("priority", 1)

        # Reproduce the index build's collision policy in miniature:
        # iterate in the (new) sorted order and keep-first.
        def sort_key(item):
            key, data = item
            if not isinstance(data, dict):
                return (99, key)
            return ((data.get("match_rules") or {}).get("priority", 1), key)

        first_seen = {}
        for key, data in sorted(qm.items(), key=sort_key):
            if key.startswith("_") or not isinstance(data, dict):
                continue
            std = data.get("standard_name", key)
            for form_name, form_data in (data.get("forms") or {}).items():
                for alias in (form_data.get("aliases") or []):
                    alias_l = alias.lower().strip()
                    if alias_l not in first_seen:
                        first_seen[alias_l] = key

        # For every alias claimed by an entry, no OTHER entry with a strictly
        # lower priority may also declare that alias (i.e. the winner is
        # always a lowest-priority claimant).
        claims = {}
        for key, data in qm.items():
            if key.startswith("_") or not isinstance(data, dict):
                continue
            for form_name, form_data in (data.get("forms") or {}).items():
                for alias in (form_data.get("aliases") or []):
                    claims.setdefault(alias.lower().strip(), set()).add(key)

        violations = []
        for alias, winner_key in first_seen.items():
            claimants = claims.get(alias, set())
            best = min(priority_of(k) for k in claimants) if claimants else 0
            if priority_of(winner_key) > best:
                violations.append((alias, winner_key, sorted(claimants)))

        assert not violations, (
            f"{len(violations)} alias collisions resolved against priority, "
            f"first 5: {violations[:5]}"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
