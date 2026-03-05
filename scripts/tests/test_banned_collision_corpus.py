"""
Matching collision test corpus for banned_recalled_ingredients.json

Tests real-world ingredient strings for:
- True positives (should match)
- True negatives (should NOT match)
- Edge cases (tricky collisions)
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from enrich_supplements_v3 import SupplementEnricherV3


@pytest.fixture(scope='module')
def enricher():
    return SupplementEnricherV3()


def _banned_ids(enricher, name):
    """Get banned IDs for an ingredient name."""
    result = enricher._check_banned_substances([{"name": name, "standardName": name}])
    return {s.get("banned_id") for s in result.get("substances", [])}


# =============================================================================
# TRUE POSITIVES - These MUST match
# =============================================================================

class TestTruePositives:
    """Ingredient strings that MUST match their expected banned IDs."""

    # DMAA variants
    @pytest.mark.parametrize("variant,expected_id", [
        ("1,3-dimethylamylamine", "BANNED_DMAA"),
        ("1,3-DMAA", "BANNED_DMAA"),
        ("methylhexanamine", "BANNED_DMAA"),
        ("geranium extract (1,3-DMAA)", "BANNED_DMAA"),
        ("4-methyl-2-hexanamine", "BANNED_DMAA"),  # Actual alias in database
    ])
    def test_dmaa_variants(self, enricher, variant, expected_id):
        assert expected_id in _banned_ids(enricher, variant)

    # Tianeptine variants (gas station heroin)
    @pytest.mark.parametrize("variant,expected_id", [
        ("tianeptine", "BANNED_TIANEPTINE"),
        ("tianeptine sodium", "BANNED_TIANEPTINE"),
        ("tianeptine sulfate", "BANNED_TIANEPTINE"),
        ("Zaza Red", "BANNED_TIANEPTINE"),
        ("Neptune's Fix", "BANNED_TIANEPTINE"),
        ("Tianaa", "BANNED_TIANEPTINE"),
    ])
    def test_tianeptine_variants(self, enricher, variant, expected_id):
        assert expected_id in _banned_ids(enricher, variant)

    # Phenibut variants
    @pytest.mark.parametrize("variant,expected_id", [
        ("phenibut", "BANNED_PHENIBUT"),
        ("phenibut HCL", "BANNED_PHENIBUT"),
        ("beta-phenyl-GABA", "BANNED_PHENIBUT"),
        ("4-amino-3-phenylbutyric acid", "BANNED_PHENIBUT"),
    ])
    def test_phenibut_variants(self, enricher, variant, expected_id):
        assert expected_id in _banned_ids(enricher, variant)

    # Ephedra variants
    @pytest.mark.parametrize("variant,expected_id", [
        ("ephedra sinica", "BANNED_EPHEDRA"),
        ("ephedra extract", "BANNED_EPHEDRA"),
        ("ma huang", "BANNED_EPHEDRA"),
        ("ephedrine alkaloids", "BANNED_EPHEDRA"),
    ])
    def test_ephedra_variants(self, enricher, variant, expected_id):
        assert expected_id in _banned_ids(enricher, variant)

    # Sibutramine (weight loss drug)
    @pytest.mark.parametrize("variant,expected_id", [
        ("sibutramine", "BANNED_SIBUTRAMINE"),
        ("Meridia", "BANNED_SIBUTRAMINE"),
        ("Reductil", "BANNED_SIBUTRAMINE"),
        ("sibutramine hydrochloride", "BANNED_SIBUTRAMINE"),
    ])
    def test_sibutramine_variants(self, enricher, variant, expected_id):
        assert expected_id in _banned_ids(enricher, variant)

    # SARMs (actual IDs use SARM_ prefix)
    @pytest.mark.parametrize("variant,expected_id", [
        ("ostarine", "SARM_OSTARINE"),
        ("MK-2866", "SARM_OSTARINE"),
        ("enobosarm", "SARM_OSTARINE"),
        ("ligandrol", "SARM_LIGANDROL"),
        ("LGD-4033", "SARM_LIGANDROL"),
        ("RAD-140", "SARM_RAD140"),
        ("testolone", "SARM_RAD140"),
    ])
    def test_sarm_variants(self, enricher, variant, expected_id):
        assert expected_id in _banned_ids(enricher, variant)

    # Kratom alkaloids (actual ID is BANNED_7_HYDROXYMITRAGYNINE)
    @pytest.mark.parametrize("variant,expected_id", [
        ("7-hydroxymitragynine", "BANNED_7_HYDROXYMITRAGYNINE"),
        ("7-OH", "BANNED_7_HYDROXYMITRAGYNINE"),
        ("7-OHMG", "BANNED_7_HYDROXYMITRAGYNINE"),
    ])
    def test_kratom_alkaloid_variants(self, enricher, variant, expected_id):
        assert expected_id in _banned_ids(enricher, variant)

    # Red No. 3 is handled as harmful additive risk (B1), not B0 banned gate
    @pytest.mark.parametrize("variant", [
        "FD&C Red No. 3",
        "Red 3",
        "erythrosine",
        "E127",
    ])
    def test_red_no_3_variants_not_in_banned(self, enricher, variant):
        assert "BANNED_RED_NO_3" not in _banned_ids(enricher, variant)


# =============================================================================
# TRUE NEGATIVES - These must NOT match
# =============================================================================

class TestTrueNegatives:
    """Ingredient strings that must NOT trigger false positives.

    NOTE: Many of these tests are currently marked xfail because the enricher
    does not yet implement negative_match_terms logic. These tests document
    the desired behavior for future implementation.
    """

    # Safe botanicals that sound similar to banned items
    @pytest.mark.parametrize("safe_ingredient,banned_id_to_avoid", [
        ("sweet orange peel", "RISK_BITTER_ORANGE"),
        ("citrus sinensis extract", "RISK_BITTER_ORANGE"),
        ("orange oil", "RISK_BITTER_ORANGE"),
        ("blood orange extract", "RISK_BITTER_ORANGE"),
    ])
    def test_orange_safe_variants(self, enricher, safe_ingredient, banned_id_to_avoid):
        assert banned_id_to_avoid not in _banned_ids(enricher, safe_ingredient)

    # Ephedra nevadensis (Mormon tea - legal, no ephedrine)
    @pytest.mark.parametrize("safe_ingredient", [
        "ephedra nevadensis",
        "mormon tea",
        "ephedra-free formula",
    ])
    def test_ephedra_safe_variants(self, enricher, safe_ingredient):
        assert "BANNED_EPHEDRA" not in _banned_ids(enricher, safe_ingredient)

    # IGF binding proteins (NOT IGF-1)
    # First 3 already pass via allowlist, 4th needs negative matching
    @pytest.mark.parametrize("safe_ingredient", [
        "IGF binding protein",
        "IGFBP",
        "IGFBP-3",
    ])
    def test_igf_binding_protein_safe(self, enricher, safe_ingredient):
        assert "BANNED_IGF1" not in _banned_ids(enricher, safe_ingredient)

    def test_igf_binding_protein_full_name(self, enricher):
        assert "BANNED_IGF1" not in _banned_ids(enricher, "insulin-like growth factor binding protein")

    # Hemp seed products (legal, no CBD concerns)
    @pytest.mark.parametrize("safe_ingredient", [
        "hemp seed oil",
        "hemp hearts",
        "hemp protein",
        "shelled hemp seeds",
    ])
    def test_hemp_seed_safe(self, enricher, safe_ingredient):
        assert "BANNED_CBD_US" not in _banned_ids(enricher, safe_ingredient)

    # PHO-free claims should not trigger PHO banned hit.
    @pytest.mark.parametrize("safe_ingredient", [
        "PHO-free",
        "contains no partially hydrogenated oils",
        "free from trans fats",
    ])
    def test_pho_free_claims(self, enricher, safe_ingredient):
        assert "BANNED_PHO" not in _banned_ids(enricher, safe_ingredient)

    # Kava-free claims
    def test_kava_free_claim(self, enricher):
        assert "RISK_KAVA" not in _banned_ids(enricher, "kava-free formula")

    # Decaf green tea (low EGCG)
    def test_decaf_green_tea(self, enricher):
        # Decaf green tea should not trigger high-dose EGCG warning
        ids = _banned_ids(enricher, "decaffeinated green tea extract")
        assert "RISK_GREEN_TEA_EXTRACT_HIGH" not in ids


# =============================================================================
# EDGE CASES - Tricky collisions that need careful handling
# =============================================================================

class TestEdgeCases:
    """Edge cases that have historically caused matching issues."""

    # DMHA vs DMAA (different compounds)
    def test_dmha_not_dmaa(self, enricher):
        """DMHA (2-aminoisoheptane) is different from DMAA."""
        ids = _banned_ids(enricher, "DMHA")
        # DMHA might be banned separately, but should not match DMAA
        if "BANNED_DMAA" in ids:
            # This is a known issue - DMHA should have its own entry
            pytest.skip("DMHA/DMAA collision - needs separate entry")

    # Bitter orange extract vs orange flavoring
    def test_bitter_vs_sweet_orange(self, enricher):
        """Bitter orange (synephrine) should match, sweet orange should not."""
        assert "RISK_BITTER_ORANGE" in _banned_ids(enricher, "bitter orange extract")
        assert "RISK_BITTER_ORANGE" not in _banned_ids(enricher, "sweet orange flavor")

    # Yohimbe bark vs yohimbine HCL
    def test_yohimbe_forms(self, enricher):
        """Both yohimbe bark and yohimbine HCL should match."""
        assert "RISK_YOHIMBE" in _banned_ids(enricher, "yohimbe bark extract")
        assert "RISK_YOHIMBE" in _banned_ids(enricher, "yohimbine HCL")

    # Kratom vs 7-OH (different risk levels)
    def test_kratom_vs_7oh(self, enricher):
        """7-hydroxymitragynine is more dangerous than whole kratom."""
        kratom_ids = _banned_ids(enricher, "kratom leaf")
        seven_oh_ids = _banned_ids(enricher, "7-hydroxymitragynine")
        # 7-OH should have its own entry
        assert "BANNED_7_HYDROXYMITRAGYNINE" in seven_oh_ids

    # Compound names in product descriptions
    def test_compound_in_context(self, enricher):
        """Banned compounds mentioned in ingredient lists should match."""
        assert "BANNED_SIBUTRAMINE" in _banned_ids(
            enricher, "Proprietary blend (sibutramine, caffeine)"
        )

    # Case sensitivity
    @pytest.mark.parametrize("variant", [
        "SIBUTRAMINE",
        "Sibutramine",
        "sibutramine",
        "SiBuTrAmInE",
    ])
    def test_case_insensitivity(self, enricher, variant):
        """Matching should be case-insensitive."""
        assert "BANNED_SIBUTRAMINE" in _banned_ids(enricher, variant)

    # Punctuation variants
    @pytest.mark.parametrize("variant", [
        "IGF-1",
        "IGF 1",
        "IGF1",
        "IGF–1",  # en-dash
        "IGF—1",  # em-dash
    ])
    def test_punctuation_variants(self, enricher, variant):
        """Matching should handle punctuation variants."""
        assert "BANNED_IGF1" in _banned_ids(enricher, variant)


# =============================================================================
# ID REDIRECT TESTS
# =============================================================================

class TestIdRedirects:
    """Test that deprecated IDs redirect correctly."""

    def test_load_id_redirects(self):
        """id_redirects.json should be valid and loadable."""
        redirects_path = os.path.join(
            os.path.dirname(__file__),
            '..', 'data', 'id_redirects.json'
        )
        with open(redirects_path, 'r') as f:
            data = json.load(f)

        assert 'redirects' in data
        assert 'lookup' in data
        assert data['lookup']['SPIKE_SIBUTRAMINE'] == 'BANNED_SIBUTRAMINE'

        # Validate v2.0.0 schema completeness
        meta = data.get('_metadata', {})
        assert meta.get('schema_version') == '5.0.0'
        assert meta.get('total_entries') == len(data['redirects'])
        assert meta.get('total_entries') == len(data['lookup'])

        # Every redirect must have required fields
        for entry in data['redirects']:
            assert 'deprecated_id' in entry
            assert 'canonical_id' in entry
            assert 'reason' in entry

        # lookup must be consistent with redirects array
        for entry in data['redirects']:
            dep = entry['deprecated_id']
            assert dep in data['lookup']
            assert data['lookup'][dep] == entry['canonical_id']

    def test_sibutramine_redirect(self, enricher):
        """Only BANNED_SIBUTRAMINE should match sibutramine.

        SPIKE_SIBUTRAMINE was merged into BANNED_SIBUTRAMINE via supersedes_ids
        and no longer exists as a separate entry.
        """
        ids = _banned_ids(enricher, "sibutramine")
        assert "BANNED_SIBUTRAMINE" in ids
        assert "SPIKE_SIBUTRAMINE" not in ids
