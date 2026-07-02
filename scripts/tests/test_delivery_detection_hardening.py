#!/usr/bin/env python3
"""
Delivery-Detection Hardening Tests (2026-07 pipeline audit)

Covers two audit findings in Section A3 delivery detection:

1. `_collect_delivery_data` matched DB keys as raw substrings of product
   text, so short keys false-positived: "raw" (tier 3) matched inside
   "Strawberry", "drawn", etc. -> spurious delivery bonus.

2. `_get_all_product_text` omitted active-ingredient NAMES and FORM names,
   although enhanced_delivery.json's own detection_note says to search
   "labelText.raw + ingredient forms + product name". A product whose only
   delivery signal is an ingredient like "Liposomal Vitamin C" or a form
   like "Magnesium Bisglycinate" got no A3 credit (and the same text feeds
   the certification/organic/physician/sustainability scanners).

Run with: pytest tests/test_delivery_detection_hardening.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enrich_supplements_v3 import SupplementEnricherV3


@pytest.fixture(scope="module")
def enricher():
    return SupplementEnricherV3()


def make_product(name="Test Product", statements=None, actives=None):
    return {
        "id": 1,
        "fullName": name,
        "brandName": "TestBrand",
        "statements": statements or [],
        "claims": [],
        "targetGroups": [],
        "physicalState": {"langualCodeDescription": "Capsule"},
        "activeIngredients": actives or [],
        "inactiveIngredients": [],
    }


class TestSubstringFalsePositives:
    def test_strawberry_does_not_match_raw(self, enricher):
        product = make_product(
            name="Strawberry Flavor Chews",
            statements=[{"type": "x", "notes": "Delicious strawberry flavor."}],
        )
        result = enricher._collect_delivery_data(product)
        matched = [s["name"] for s in result["systems"]]
        assert "raw" not in matched, f"'raw' substring-matched Strawberry: {matched}"

    def test_gumdrops_does_not_match_drops(self, enricher):
        product = make_product(name="Vitamin Gumdrops")
        result = enricher._collect_delivery_data(product)
        matched = [s["name"] for s in result["systems"]]
        assert "drops" not in matched, f"'drops' substring-matched Gumdrops: {matched}"

    def test_whole_word_raw_still_matches(self, enricher):
        product = make_product(
            statements=[{"type": "x", "notes": "Made with raw whole-food nutrients."}]
        )
        result = enricher._collect_delivery_data(product)
        matched = [s["name"] for s in result["systems"]]
        assert "raw" in matched

    def test_liposomal_in_statement_matches_tier1(self, enricher):
        product = make_product(
            statements=[{"type": "x", "notes": "Uses liposomal delivery technology."}]
        )
        result = enricher._collect_delivery_data(product)
        assert result["highest_tier"] == 1

    def test_hyphenated_key_matches(self, enricher):
        product = make_product(
            statements=[{"type": "x", "notes": "Enteric-coated for gut delivery."}]
        )
        result = enricher._collect_delivery_data(product)
        matched = [s["name"] for s in result["systems"]]
        assert "enteric-coated" in matched


class TestIngredientNamesInProductText:
    def test_ingredient_name_reaches_pattern_text(self, enricher):
        product = make_product(
            actives=[{"name": "Liposomal Vitamin C", "quantity": 500, "unit": "mg"}]
        )
        text = enricher._get_all_product_text(product).lower()
        assert "liposomal vitamin c" in text

    def test_ingredient_form_reaches_pattern_text(self, enricher):
        product = make_product(
            actives=[{
                "name": "Magnesium",
                "quantity": 200,
                "unit": "mg",
                "forms": [{"name": "Magnesium Bisglycinate Chelate"}],
            }]
        )
        text = enricher._get_all_product_text(product).lower()
        assert "magnesium bisglycinate chelate" in text

    def test_liposomal_ingredient_name_earns_tier1(self, enricher):
        """Per enhanced_delivery.json detection_note: ingredient forms count."""
        product = make_product(
            actives=[{"name": "Liposomal Vitamin C", "quantity": 500, "unit": "mg"}]
        )
        result = enricher._collect_delivery_data(product)
        assert result["highest_tier"] == 1, f"systems={result['systems']}"

    def test_chelated_form_earns_tier2(self, enricher):
        product = make_product(
            actives=[{
                "name": "Magnesium",
                "quantity": 200,
                "unit": "mg",
                "forms": [{"name": "Chelated Magnesium Glycinate"}],
            }]
        )
        result = enricher._collect_delivery_data(product)
        assert result["highest_tier"] == 2, f"systems={result['systems']}"

    def test_no_delivery_signal_yields_no_tier(self, enricher):
        product = make_product(
            actives=[{"name": "Vitamin C", "quantity": 500, "unit": "mg",
                      "forms": [{"name": "Ascorbic Acid"}]}]
        )
        result = enricher._collect_delivery_data(product)
        assert result["highest_tier"] is None, f"systems={result['systems']}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
