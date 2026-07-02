#!/usr/bin/env python3
"""
Golden Benchmark Regression Test

Pins the full clean -> enrich -> score result of the shipped prenatal
reference label (tests/fixtures/prenatal_benchmark_label.json) so that future
pipeline changes cannot silently move the score or start rewarding the wrong
things. This is the "save the scorer breakdown as a regression test" step.

If a deliberate scoring change moves these numbers, update the expected values
here in the same commit and explain the delta.

Run with: pytest tests/test_prenatal_benchmark_golden.py -v
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enhanced_normalizer import EnhancedDSLDNormalizer
from enrich_supplements_v3 import SupplementEnricherV3
from score_supplements import SupplementScorer

FIXTURE = Path(__file__).parent / "fixtures" / "prenatal_benchmark_label.json"


@pytest.fixture(scope="module")
def scored():
    raw = json.loads(FIXTURE.read_text())
    cleaned = EnhancedDSLDNormalizer().normalize_product(raw)
    enriched, _ = SupplementEnricherV3().enrich_product(cleaned)
    result = SupplementScorer().score_product(enriched)
    return enriched, result


class TestGoldenScore:
    def test_headline(self, scored):
        _, r = scored
        assert r["quality_score"] == pytest.approx(77.0, abs=0.01)
        assert r["score_100_equivalent"] == pytest.approx(96.25, abs=0.1)
        assert r["verdict"] == "SAFE"
        assert r["flags"] == []
        assert r["mapped_coverage"] == pytest.approx(1.0)

    def test_section_breakdown(self, scored):
        _, r = scored
        b = r["breakdown"]
        assert b["A"]["score"] == pytest.approx(22.48, abs=0.05)
        assert b["B"]["score"] == pytest.approx(35.0, abs=0.01)
        assert b["C"]["score"] == pytest.approx(15.0, abs=0.01)
        assert b["D"]["score"] == pytest.approx(4.5, abs=0.01)

    def test_section_a_components(self, scored):
        """The A-section levers that the fixture is engineered to earn."""
        _, r = scored
        a = r["breakdown"]["A"]
        assert a["A2"] == pytest.approx(3.0)   # premium forms saturated
        assert a["A3"] == pytest.approx(3.0)   # tier-1 liposomal delivery
        assert a["A4"] == pytest.approx(3.0)   # absorption pairing (post-fix)
        assert a["A5"] == pytest.approx(3.0)   # organic + botanical + synergy


class TestGoldenCoverageLedger:
    def test_ledger_present_and_isolated(self, scored):
        enriched, _ = scored
        cov = enriched.get("prenatal_coverage", {})
        assert cov, "prenatal_coverage ledger missing"
        assert cov["scoring_impact"] == "none"
        assert cov["is_prenatal_positioned"] is True

    def test_anchor_statuses(self, scored):
        enriched, _ = scored
        cov = enriched["prenatal_coverage"]
        summary = cov["summary"]
        # Complete panel: the 7 DHA/choline/folate/iron/iodine/D/B12 anchors meet
        for anchor in ["folate", "iron", "iodine", "vitamin_d",
                       "vitamin_b12", "choline", "dha"]:
            assert anchor in summary["meets_target"], (
                f"{anchor} expected meets_target, got "
                f"{cov['anchors'][anchor]['status']}"
            )
        # Calcium is intentionally diet/companion-supplied (200 mg vs 1000 mg)
        assert "calcium" in summary["below_target"]
        # Nothing missing, nothing over UL
        assert summary["missing"] == []
        assert summary["above_ul"] == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
