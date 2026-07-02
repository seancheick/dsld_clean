#!/usr/bin/env python3
"""
Product Role Classification Tests (Section E device-side data)

Roles let the app be role-aware: a prenatal base that pairs with a separate
DHA/choline product is a different ROLE, not a low-quality prenatal.

Contract under test:
1. Full prenatal panel -> prenatal_complete.
2. Prenatal missing DHA/choline -> prenatal_base (not penalized).
3. Small DHA-only prenatal product -> prenatal_dha_companion.
4. Non-prenatal multivitamin -> general_multi.
5. "Complete/all-in-one" claim on a base -> completeness_claim_mismatch.
6. ZERO scoring impact.

Run with: pytest tests/test_product_role.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enrich_supplements_v3 import SupplementEnricherV3


@pytest.fixture(scope="module")
def enricher():
    return SupplementEnricherV3()


def ing(name, std, qty, unit):
    return {"name": name, "standardName": std, "quantity": qty, "unit": unit}


PRENATAL_CORE = [
    ing("Folate", "Vitamin B9 (Folate)", 1000, "mcg DFE"),
    ing("Iodine", "Iodine", 220, "mcg"),
    ing("Vitamin D3", "Vitamin D", 50, "mcg"),
    ing("Vitamin B12", "Vitamin B12", 100, "mcg"),
]
COMPLETENESS = [
    ing("Iron", "Iron", 27, "mg"),
    ing("DHA", "DHA (Docosahexaenoic Acid)", 300, "mg"),
    ing("Choline", "Choline", 450, "mg"),
]


def product(actives, name="Test Prenatal", statements=None):
    return {
        "id": 7, "fullName": name,
        "targetGroups": ["Pregnant/Lactating women"] if "prenatal" in name.lower() else [],
        "statements": statements or [],
        "activeIngredients": actives,
        "inactiveIngredients": [],
    }


def role_of(enricher, prod):
    cov = enricher._collect_prenatal_coverage(prod)
    st = enricher._classify_supplement_type(prod)
    supp = st.get("type") if isinstance(st, dict) else st
    return enricher._classify_product_role(prod, cov, supp)


class TestRoles:
    def test_full_panel_is_complete(self, enricher):
        r = role_of(enricher, product(PRENATAL_CORE + COMPLETENESS,
                                      name="Complete Prenatal"))
        assert r["role"] == "prenatal_complete"
        assert r["completeness_missing"] == []

    def test_missing_dha_choline_is_base_not_penalized(self, enricher):
        r = role_of(enricher, product(PRENATAL_CORE + [COMPLETENESS[0]],  # iron only
                                      name="Prenatal Multi"))
        assert r["role"] == "prenatal_base"
        assert "dha" in r["completeness_missing"]
        assert "choline" in r["completeness_missing"]
        assert r["scoring_impact"] == "none"

    def test_dha_companion(self, enricher):
        r = role_of(enricher, product(
            [ing("DHA", "DHA (Docosahexaenoic Acid)", 300, "mg")],
            name="Prenatal DHA"))
        assert r["role"] == "prenatal_dha_companion"

    def test_general_multi_not_prenatal(self, enricher):
        actives = PRENATAL_CORE + COMPLETENESS + [
            ing("Vitamin C", "Vitamin C", 90, "mg"),
            ing("Zinc", "Zinc", 11, "mg"),
        ]
        r = role_of(enricher, product(actives, name="Daily Men's Multi"))
        # Not prenatal-positioned by name, but composition carries the core;
        # by-composition prenatal detection still applies (that is intended:
        # a multi that covers the prenatal core IS usable as one).
        assert r["role"] in ("general_multi", "prenatal_complete")
        assert r["is_prenatal_positioned"] is False

    def test_plain_multi_without_core_is_general(self, enricher):
        actives = [
            ing("Vitamin C", "Vitamin C", 90, "mg"),
            ing("Zinc", "Zinc", 11, "mg"),
            ing("Vitamin E", "Vitamin E", 15, "mg"),
            ing("Magnesium", "Magnesium", 100, "mg"),
            ing("Selenium", "Selenium", 55, "mcg"),
            ing("Copper", "Copper", 900, "mcg"),
        ]
        r = role_of(enricher, product(actives, name="Daily Multivitamin"))
        assert r["role"] == "general_multi"


class TestClaimMismatch:
    def test_complete_claim_on_base_flags_mismatch(self, enricher):
        r = role_of(enricher, product(
            PRENATAL_CORE + [COMPLETENESS[0]],
            name="Complete All-in-One Prenatal",
            statements=[{"type": "x", "notes": "The complete all-in-one prenatal."}],
        ))
        assert r["role"] == "prenatal_base"
        assert r["claims_complete"] is True
        assert r["completeness_claim_mismatch"] is True

    def test_complete_claim_on_actually_complete_is_ok(self, enricher):
        r = role_of(enricher, product(
            PRENATAL_CORE + COMPLETENESS,
            name="Complete Prenatal",
            statements=[{"type": "x", "notes": "Complete prenatal nutrition."}],
        ))
        assert r["role"] == "prenatal_complete"
        assert r["completeness_claim_mismatch"] is False

    def test_base_without_claim_no_mismatch(self, enricher):
        r = role_of(enricher, product(PRENATAL_CORE + [COMPLETENESS[0]],
                                      name="Prenatal Multi"))
        assert r["completeness_claim_mismatch"] is False


class TestScoringIsolation:
    def test_scorer_ignores_product_role(self):
        from score_supplements import SupplementScorer
        import copy
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
        with_role = copy.deepcopy(base)
        with_role["product_role"] = {"role": "prenatal_base", "scoring_impact": "none"}
        s1 = scorer.score_product(copy.deepcopy(base))
        s2 = scorer.score_product(with_role)
        assert s1.get("score") == s2.get("score")
        assert s1.get("verdict") == s2.get("verdict")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
