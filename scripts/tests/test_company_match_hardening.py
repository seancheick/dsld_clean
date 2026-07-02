#!/usr/bin/env python3
"""
Company-Matching Hardening Tests (2026-07 pipeline audit)

Covers three audit findings in manufacturer identification:

1. `_fuzzy_company_match` used max(WRatio, partial_ratio) >= 0.85.
   partial_ratio returns ~1.0 for any substring / shared-token containment,
   so distinct companies cross-matched ("HUM Nutrition" ~ "Goli Nutrition Inc.",
   brand "Country Life Gut Connection" ~ "Garden of Life").

2. `_check_violations` applied a manufacturer's violation deduction on ANY
   fuzzy hit with no exactness gate -> penalties misattributed across brands
   that merely share a token like "Nutrition".

3. `_check_top_manufacturer` returned on the FIRST fuzzy hit in DB iteration
   order, so an early weak fuzzy match preempted a later exact match; the
   fuzzy path also ignored aliases while the exact path used them.

4. `normalization.normalize_company_name` stripped 2-letter corporate
   suffixes glued to the end of a word ("Costco" -> "cost", "Visa" -> "vi"),
   corrupting the keys that feed all of the above.

Run with: pytest tests/test_company_match_hardening.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enrich_supplements_v3 import SupplementEnricherV3
from normalization import normalize_company_name


@pytest.fixture(scope="module")
def enricher():
    return SupplementEnricherV3()


# ---------------------------------------------------------------------------
# 4) normalize_company_name must not eat word endings
# ---------------------------------------------------------------------------

class TestNormalizeCompanyName:
    def test_suffix_requires_own_token(self):
        # Glued endings must survive
        assert normalize_company_name("Costco") == "costco"
        assert normalize_company_name("Nabisco") == "nabisco"
        assert normalize_company_name("Visa") == "visa"
        assert normalize_company_name("Tabasco") == "tabasco"

    def test_real_suffixes_still_stripped(self):
        assert normalize_company_name("Thorne Research Inc.") == normalize_company_name("Thorne Research")
        assert normalize_company_name("Country Life, LLC") == normalize_company_name("Country Life")
        assert normalize_company_name("Acme Co") == normalize_company_name("Acme")
        assert normalize_company_name("Acme, Co.") == normalize_company_name("Acme")


# ---------------------------------------------------------------------------
# 1) _fuzzy_company_match must not cross-match distinct companies
# ---------------------------------------------------------------------------

class TestFuzzyCompanyMatch:
    CROSS_PAIRS = [
        ("HUM Nutrition", "Goli Nutrition Inc."),
        ("Naked Nutrition", "Dorado Nutrition"),
        ("Country Life Gut Connection", "Garden of Life"),
        ("Nature's Way", "Nature's Bounty"),
        ("Life", "Garden of Life"),
        ("Pure", "Pure Encapsulations"),
        ("Bounty", "Nature's Bounty"),
    ]

    LEGIT_PAIRS = [
        # docstring-promised variations that MUST keep matching
        ("Healthy Directions", "Healthy Directions, LLC"),
        ("Natural Living", "Natural Living, Inc."),
        ("Thorne", "Thorne Research Inc."),
        ("Nordic Naturals", "Nordic Naturals Inc."),
        ("Jarrow Formulas", "Jarrow Formulas Inc."),
        ("Dr. David Williams", "David Williams"),
    ]

    def test_distinct_companies_do_not_match(self, enricher):
        for a, b in self.CROSS_PAIRS:
            is_match, score = enricher._fuzzy_company_match(a, b)
            assert not is_match, (
                f"{a!r} must NOT fuzzy-match {b!r} (score={score:.3f})"
            )

    def test_legit_variations_still_match(self, enricher):
        for a, b in self.LEGIT_PAIRS:
            is_match, score = enricher._fuzzy_company_match(a, b)
            assert is_match, (
                f"{a!r} SHOULD fuzzy-match {b!r} (score={score:.3f})"
            )


# ---------------------------------------------------------------------------
# 2) _check_violations must not misattribute penalties across brands
# ---------------------------------------------------------------------------

class TestViolationAttribution:
    def test_shared_token_brand_gets_no_penalty(self, enricher):
        """A brand sharing only a generic token with a violator gets no deduction."""
        violators = {
            v.get("manufacturer", "")
            for v in enricher.databases.get("manufacturer_violations", {}).get(
                "manufacturer_violations", []
            )
        }
        # Build an innocent brand from a violator's generic suffix token
        # (e.g. "* Nutrition"): must not inherit that violator's penalty.
        result = enricher._check_violations("HUM Nutrition", "HUM Nutrition")
        assert "HUM Nutrition" not in violators  # test-precondition sanity
        assert result["found"] is False, (
            f"innocent brand matched violations: {result}"
        )
        assert result["total_deduction_applied"] == 0.0

    def test_exact_violator_still_caught(self, enricher):
        """The real violator (exact name and suffix variation) keeps its penalty."""
        violations = enricher.databases.get("manufacturer_violations", {}).get(
            "manufacturer_violations", []
        )
        if not violations:
            pytest.skip("no violations DB loaded")
        target = violations[0].get("manufacturer", "")
        assert target
        result = enricher._check_violations(target, target)
        assert result["found"] is True

        # Suffix variation must also still match ("X" vs "X, LLC")
        result2 = enricher._check_violations(f"{target}, LLC", "")
        assert result2["found"] is True


# ---------------------------------------------------------------------------
# 3) _check_top_manufacturer: exact must beat fuzzy; order-independent
# ---------------------------------------------------------------------------

class TestTopManufacturerResolution:
    def test_exact_match_wins_over_earlier_fuzzy(self, enricher):
        """FullWell is late in the DB; earlier entries must not fuzzy-preempt it."""
        result = enricher._check_top_manufacturer("FullWell", "")
        assert result["found"] is True
        assert result["match_type"] == "exact"
        assert result["name"] == "FullWell"

    def test_alias_exact_match_wins(self, enricher):
        result = enricher._check_top_manufacturer("Pharmavite LLC", "")
        assert result["found"] is True
        assert result["match_type"] == "exact"
        assert result["name"] == "Nature Made"

    def test_shared_token_brand_is_not_top_manufacturer(self, enricher):
        """'Country Life Gut Connection' must not resolve to 'Garden of Life'
        (observed on a real DSLD product in the pre-fix baseline)."""
        result = enricher._check_top_manufacturer("Country Life Gut Connection", "Country Life, LLC")
        if result.get("found"):
            matched = result.get("name", "")
            assert matched != "Garden of Life", f"cross-brand fuzzy match: {result}"

    def test_fuzzy_still_matches_close_variation(self, enricher):
        """Fuzzy remains available for near-identical names not in aliases."""
        result = enricher._check_top_manufacturer("Thorne Research", "")
        assert result["found"] is True
        assert result["name"] == "Thorne"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
