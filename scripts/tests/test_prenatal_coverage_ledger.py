#!/usr/bin/env python3
"""
Prenatal Coverage Ledger Tests (Section E device-side data)

The ledger reports pregnancy-anchor completeness (folate, iron, iodine,
vitamin D, B12, choline, DHA, calcium) for the app's stack /
"what's missing or underdosed" views.

Contract under test:
1. Anchors present at meaningful doses -> meets_target.
2. Anchors absent -> missing (a base prenatal that ships DHA/choline as a
   companion product is reported, NOT penalized).
3. Token doses (One A Day-style 110 mg choline) -> below_target.
4. Above pregnancy UL -> above_ul.
5. Unit handling: vitamin D IU -> mcg; g -> mg; mcg DFE treated as mcg.
6. ZERO scoring impact: the v3-series scorer never reads the block.

Run with: pytest tests/test_prenatal_coverage_ledger.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enrich_supplements_v3 import SupplementEnricherV3


@pytest.fixture(scope="module")
def enricher():
    return SupplementEnricherV3()


def make_product(actives, name="Test Prenatal", target_groups=None):
    return {
        "id": 42,
        "fullName": name,
        "targetGroups": target_groups or [],
        "activeIngredients": actives,
    }


def ing(name, std, qty, unit):
    return {"name": name, "standardName": std, "quantity": qty, "unit": unit}


FULL_PANEL = [
    ing("Folate", "Vitamin B9 (Folate)", 1000, "mcg DFE"),
    ing("Iron", "Iron", 27, "mg"),
    ing("Iodine", "Iodine", 220, "mcg"),
    ing("Vitamin D3", "Vitamin D", 50, "mcg"),
    ing("Vitamin B12", "Vitamin B12", 100, "mcg"),
    ing("Choline", "Choline", 450, "mg"),
    ing("DHA", "DHA (Docosahexaenoic Acid)", 300, "mg"),
    ing("Calcium", "Calcium", 1000, "mg"),
]


class TestCoverageStatuses:
    def test_complete_panel_all_meet_target(self, enricher):
        cov = enricher._collect_prenatal_coverage(make_product(FULL_PANEL))
        assert cov["summary"]["missing"] == []
        assert cov["summary"]["below_target"] == []
        assert cov["summary"]["above_ul"] == []
        assert sorted(cov["summary"]["meets_target"]) == sorted(
            ["folate", "iron", "iodine", "vitamin_d", "vitamin_b12",
             "choline", "dha", "calcium"]
        )

    def test_base_multi_reports_missing_dha_choline_without_penalty_semantics(self, enricher):
        base = [a for a in FULL_PANEL
                if a["standardName"] not in ("Choline", "DHA (Docosahexaenoic Acid)")]
        cov = enricher._collect_prenatal_coverage(make_product(base))
        assert "dha" in cov["summary"]["missing"]
        assert "choline" in cov["summary"]["missing"]
        # Ledger is informational: it must declare no scoring impact.
        assert cov["scoring_impact"] == "none"

    def test_token_choline_dose_is_below_target(self, enricher):
        actives = [a for a in FULL_PANEL if a["standardName"] != "Choline"]
        actives.append(ing("Choline", "Choline", 110, "mg"))  # One A Day-style
        cov = enricher._collect_prenatal_coverage(make_product(actives))
        assert cov["anchors"]["choline"]["status"] == "below_target"
        assert cov["anchors"]["choline"]["pct_of_target"] == pytest.approx(24.4, abs=0.2)

    def test_above_pregnancy_ul_flagged(self, enricher):
        actives = [a for a in FULL_PANEL if a["standardName"] != "Iron"]
        actives.append(ing("Iron", "Iron", 60, "mg"))  # preg UL 45 mg
        cov = enricher._collect_prenatal_coverage(make_product(actives))
        assert cov["anchors"]["iron"]["status"] == "above_ul"
        assert "iron" in cov["summary"]["above_ul"]


class TestUnitsAndAggregation:
    def test_vitamin_d_iu_converts(self, enricher):
        actives = [ing("Vitamin D3", "Vitamin D", 2000, "IU")]  # = 50 mcg
        cov = enricher._collect_prenatal_coverage(make_product(actives))
        assert cov["anchors"]["vitamin_d"]["status"] == "meets_target"
        assert cov["anchors"]["vitamin_d"]["amount_per_day"] == pytest.approx(50.0)

    def test_split_choline_forms_are_summed(self, enricher):
        actives = [
            ing("Choline bitartrate", "Choline", 250, "mg"),
            ing("Alpha-GPC", "Choline", 200, "mg"),
        ]
        cov = enricher._collect_prenatal_coverage(make_product(actives))
        assert cov["anchors"]["choline"]["amount_per_day"] == pytest.approx(450.0)
        assert cov["anchors"]["choline"]["status"] == "meets_target"

    def test_servings_multiplier_applies(self, enricher):
        actives = [ing("Iron", "Iron", 13.5, "mg")]
        cov = enricher._collect_prenatal_coverage(
            make_product(actives), max_servings_per_day=2
        )
        assert cov["anchors"]["iron"]["amount_per_day"] == pytest.approx(27.0)
        assert cov["anchors"]["iron"]["status"] == "meets_target"

    def test_dha_token_does_not_match_ashwagandha(self, enricher):
        # "dha" is a substring of "ashwagandha": word-boundary matching must
        # not report DHA coverage for an ashwagandha product.
        actives = [ing("KSM-66", "Ashwagandha", 600, "mg")]
        cov = enricher._collect_prenatal_coverage(make_product(actives))
        assert cov["anchors"]["dha"]["status"] == "missing"
        assert "dha" in cov["summary"]["missing"]

    def test_salt_cation_does_not_leak_into_calcium(self, enricher):
        # "Calcium Ascorbate" is vitamin C: standardName-based matching must
        # not count it toward the calcium anchor.
        actives = [ing("Vitamin C (as Calcium Ascorbate)", "Vitamin C", 120, "mg")]
        cov = enricher._collect_prenatal_coverage(make_product(actives))
        assert cov["anchors"]["calcium"]["status"] == "missing"


class TestRoleHintAndEmpty:
    def test_prenatal_positioning_detected(self, enricher):
        cov = enricher._collect_prenatal_coverage(
            make_product(FULL_PANEL, name="Complete Prenatal Multivitamin")
        )
        assert cov["is_prenatal_positioned"] is True

    def test_non_prenatal_not_positioned(self, enricher):
        cov = enricher._collect_prenatal_coverage(
            make_product(FULL_PANEL, name="Daily Men's Multi")
        )
        assert cov["is_prenatal_positioned"] is False

    def test_no_actives_all_missing_no_crash(self, enricher):
        cov = enricher._collect_prenatal_coverage(make_product([]))
        assert len(cov["summary"]["missing"]) == 8


class TestScoringIsolation:
    def test_scorer_ignores_ledger(self):
        """Identical enriched product with and without the ledger must score
        identically - completeness is app-layer, not quality-score."""
        from score_supplements import SupplementScorer
        scorer = SupplementScorer()
        base = {
            "dsld_id": "t1", "product_name": "T", "enrichment_version": "3.1.0",
            "supplement_type": {"type": "multivitamin"},
            "ingredient_quality_data": {
                "total_active": 1, "unmapped_count": 0,
                "ingredients": [{
                    "name": "Vitamin C", "standard_name": "Vitamin C",
                    "score": 12, "dosage_importance": 1.0, "mapped": True,
                    "has_dose": True, "quantity": 100, "unit": "mg",
                }],
            },
            "contaminant_data": {
                "banned_substances": {"substances": []},
                "harmful_additives": {"additives": []},
                "allergens": {"allergens": []},
            },
        }
        import copy
        with_ledger = copy.deepcopy(base)
        with_ledger["prenatal_coverage"] = {
            "summary": {"missing": ["dha", "choline"]},
            "scoring_impact": "none",
        }
        s1 = scorer.score_product(copy.deepcopy(base))
        s2 = scorer.score_product(with_ledger)
        assert s1.get("quality_score") == s2.get("quality_score")
        assert s1.get("verdict") == s2.get("verdict")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
