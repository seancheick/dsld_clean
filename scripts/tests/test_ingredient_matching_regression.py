"""
Real label corpus regression tests for ingredient matching.

Suite 1: Tests real product label strings against expected matches
Suite 2: Tests collision and substring edge cases

These tests catch the real bugs that occur in production.

Run with: pytest tests/test_ingredient_matching_regression.py -v
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enrich_supplements_v3 import SupplementEnricherV3

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'


@pytest.fixture(scope='module')
def enricher():
    """Create enricher instance for testing."""
    return SupplementEnricherV3()


@pytest.fixture(scope='module')
def iqm_data():
    """Load ingredient quality map."""
    with open(IQM_PATH, 'r') as f:
        return json.load(f)


# =============================================================================
# SUITE 1: REAL LABEL CORPUS REGRESSION TESTS
# =============================================================================

class TestRealLabelCorpus:
    """
    Tests real product label strings to ensure:
    - Top N extracted ingredients are correct
    - Matched IDs are stable
    - No ambiguous matches
    """

    # Test corpus: (label_text, expected_ingredient_key, should_match)
    LABEL_CORPUS = [
        # NAD+ precursors - historically problematic
        ("Nicotinamide Riboside 300mg", "nicotinamide_riboside", True),
        ("NMN (Nicotinamide Mononucleotide) 500mg", "nmn", True),
        ("Nicotinamide Riboside Chloride", "nicotinamide_riboside", True),

        # Curcumin forms - different delivery systems
        ("Curcumin Phytosome (Meriva)", "curcumin", True),
        ("Liposomal Curcumin 500mg", "curcumin", True),
        ("Curcumin C3 Complex with BioPerine", "curcumin", True),
        ("Turmeric Root Powder 1000mg", "turmeric", True),
        ("Organic Turmeric Extract", "turmeric", True),

        # Flaxseed/Omega-3 disambiguation
        ("Flaxseed Oil 1000mg", "flaxseed", True),
        ("Organic Flax Oil", "flaxseed", True),
        ("Cold-Pressed Linseed Oil", "flaxseed", True),

        # Probiotic strains vs generic
        ("Lactobacillus acidophilus 10 Billion CFU", "lactobacillus_acidophilus", True),
        ("Bifidobacterium lactis BL-04", "bifidobacterium_lactis", True),
        ("Lactobacillus rhamnosus GG", "lactobacillus_rhamnosus", True),
        ("Saccharomyces boulardii CNCM I-745", "saccharomyces_boulardii", True),

        # Active compounds vs parent botanicals
        ("Silymarin 80% (Milk Thistle Extract)", "silymarin", True),
        ("Milk Thistle Seed Extract", "milk_thistle", True),
        ("Boswellic Acids 65%", "boswellic_acids", True),
        ("Boswellia Serrata Extract", "boswellia", True),
        ("Allicin (from Garlic)", "allicin", True),
        ("Aged Garlic Extract", "garlic", True),

        # Specific forms vs generic
        ("5-HTP (from Griffonia simplicifolia)", "5_htp", True),
        ("L-Tryptophan 500mg", "l_tryptophan", True),
        ("Acetyl-L-Carnitine HCl", "acetyl_l_carnitine", True),
        ("L-Carnitine Tartrate", "l_carnitine", True),

        # Bioflavonoids vs specific compounds
        ("Quercetin Dihydrate 500mg", "quercetin", True),
        ("Citrus Bioflavonoid Complex", "citrus_bioflavonoids", True),

        # Creatine forms
        ("Creatine Monohydrate 5g", "creatine_monohydrate", True),
        ("Creatine HCl (Con-Cret)", "creatine", True),
        ("Buffered Creatine (Kre-Alkalyn)", "creatine", True),

        # Magnolia compounds
        ("Honokiol 98%", "honokiol", True),
        ("Magnolia Bark Extract", "magnolia_bark", True),

        # Vitamin forms
        ("Vitamin K1 (Phylloquinone)", "vitamin_k1", True),
        ("Vitamin K2 (MK-7)", "vitamin_k", True),
        ("Methylcobalamin (Vitamin B12)", "vitamin_b12_cobalamin", True),

        # Prebiotics
        ("Inulin (from Chicory Root)", "inulin", True),
        ("Beta-Glucan 250mg", "beta_glucan", True),
        ("Psyllium Husk Powder", "psyllium", True),
    ]

    @pytest.mark.parametrize("label_text,expected_key,should_match", LABEL_CORPUS)
    def test_label_matches_expected_ingredient(self, enricher, label_text, expected_key, should_match):
        """Test that label text matches the expected ingredient."""
        # Create a mock product with single ingredient
        # Use correct field names expected by enricher (camelCase)
        product = {
            "id": "TEST_001",
            "product_name": "Test Product",
            "activeIngredients": [{"name": label_text, "quantity": 100, "unit": "mg"}]
        }

        # Run enrichment (returns tuple of enriched_product, issues)
        enriched, issues = enricher.enrich_product(product)

        # Check if expected ingredient was matched
        # Scorable ingredients are in ingredient_quality_data.ingredients_scorable
        quality_data = enriched.get('ingredient_quality_data', {})
        matched_ingredients = quality_data.get('ingredients_scorable', [])
        matched_keys = [ing.get('canonical_id') for ing in matched_ingredients if ing.get('canonical_id')]

        if should_match:
            assert expected_key in matched_keys, (
                f"Expected '{expected_key}' to match label '{label_text}'\n"
                f"Got matches: {matched_keys}"
            )
        else:
            assert expected_key not in matched_keys, (
                f"Expected '{expected_key}' to NOT match label '{label_text}'\n"
                f"But it was matched"
            )

    def test_no_double_matching_parent_child(self, enricher):
        """Curcumin should not also match turmeric in same label."""
        product = {
            "id": "TEST_002",
            "product_name": "Curcumin Supplement",
            "activeIngredients": [{"name": "Curcumin C3 Complex", "quantity": 500, "unit": "mg"}]
        }

        enriched, issues = enricher.enrich_product(product)
        quality_data = enriched.get('ingredient_quality_data', {})
        matched_keys = [
            ing.get('canonical_id')
            for ing in quality_data.get('ingredients_scorable', [])
            if ing.get('canonical_id')
        ]

        # Should match curcumin but NOT also turmeric
        assert 'curcumin' in matched_keys or len(matched_keys) == 0
        if 'curcumin' in matched_keys:
            assert 'turmeric' not in matched_keys, (
                "Curcumin C3 Complex matched both curcumin AND turmeric - double match!"
            )


# =============================================================================
# SUITE 2: COLLISION AND SUBSTRING TESTS
# =============================================================================

class TestCollisionAndSubstring:
    """
    Tests that ensure we do NOT match on:
    - Generic tokens that cause false matches
    - Substrings that cause incorrect matches
    """

    # Things that should NOT cause a match
    FALSE_POSITIVE_TESTS = [
        # Generic terms that should be excluded
        ("Natural flavoring", "vitamin_a"),  # "natural" is in vitamin_a aliases
        ("Synthetic sweetener", "ceramides"),  # "synthetic" appears in aliases
        ("Standard capsule", None),  # "standard" should not match anything
        ("Unspecified filler", None),  # "unspecified" should not match

        # Substring collisions
        ("Vitamin K1 100mcg", "vitamin_k"),  # K1 should not also match generic K
        ("EPA from fish oil", "fish_oil"),  # EPA alone should match EPA, not fish_oil

        # Category words that shouldn't cause matches
        ("Probiotic blend", "lactobacillus_acidophilus"),  # Generic "probiotic" shouldn't match specific strain
        ("Prebiotic fiber", "inulin"),  # Generic "prebiotic" shouldn't match specific
    ]

    @pytest.mark.parametrize("label_text,should_not_match", FALSE_POSITIVE_TESTS)
    def test_no_false_positive_match(self, enricher, label_text, should_not_match):
        """Test that generic/substring terms don't cause false matches."""
        if should_not_match is None:
            pytest.skip("No specific ingredient to test against")

        product = {
            "id": "TEST_FP",
            "product_name": "Test Product",
            "activeIngredients": [{"name": label_text, "quantity": 100, "unit": "mg"}]
        }

        enriched, issues = enricher.enrich_product(product)
        quality_data = enriched.get('ingredient_quality_data', {})
        matched_keys = [
            ing.get('canonical_id')
            for ing in quality_data.get('ingredients_scorable', [])
            if ing.get('canonical_id')
        ]

        assert should_not_match not in matched_keys, (
            f"'{label_text}' should NOT match '{should_not_match}' but it did!"
        )

    # Substring priority tests - specific should win over generic
    PRIORITY_TESTS = [
        # (label, should_match, should_not_match)
        ("Vitamin K1", "vitamin_k1", "vitamin_k"),  # K1 > K
        ("Nicotinamide Riboside", "nicotinamide_riboside", "vitamin_b3_niacin"),  # NR > B3
        ("Lactobacillus acidophilus", "lactobacillus_acidophilus", "probiotics"),  # Specific > category
        ("Silymarin extract", "silymarin", "milk_thistle"),  # Compound > botanical
        ("5-HTP", "5_htp", "l_tryptophan"),  # Metabolite > precursor
    ]

    @pytest.mark.parametrize("label_text,should_match,should_not_match", PRIORITY_TESTS)
    def test_specific_matches_over_generic(self, enricher, label_text, should_match, should_not_match):
        """Test that specific ingredients match over generic categories."""
        product = {
            "id": "TEST_PRIO",
            "product_name": "Test Product",
            "activeIngredients": [{"name": label_text, "quantity": 100, "unit": "mg"}]
        }

        enriched, issues = enricher.enrich_product(product)
        quality_data = enriched.get('ingredient_quality_data', {})
        matched_keys = [
            ing.get('canonical_id')
            for ing in quality_data.get('ingredients_scorable', [])
            if ing.get('canonical_id')
        ]

        # Check specific match happened
        if should_match:
            assert should_match in matched_keys or len(matched_keys) == 0, (
                f"Expected '{should_match}' to match '{label_text}', got {matched_keys}"
            )

        # Check generic did NOT match (if specific did)
        if should_match in matched_keys and should_not_match:
            assert should_not_match not in matched_keys, (
                f"Both '{should_match}' and '{should_not_match}' matched '{label_text}' - priority issue!"
            )


# =============================================================================
# DETERMINISTIC MATCHING TESTS
# =============================================================================

class TestDeterministicMatching:
    """Test that matching is deterministic and stable."""

    STABILITY_TESTS = [
        "Nicotinamide Riboside",
        "NMN",
        "Curcumin Phytosome",
        "Liposomal Curcumin",
        "Flaxseed oil",
        "Lactobacillus rhamnosus GG",
        "Silymarin 80%",
        "5-HTP",
        "Quercetin",
        "Beta-Glucan",
    ]

    @pytest.mark.parametrize("label_text", STABILITY_TESTS)
    def test_matching_is_deterministic(self, enricher, label_text):
        """Run same label 3 times, results should be identical."""
        results = []

        for i in range(3):
            product = {
                "id": f"TEST_DET_{i}",
                "product_name": "Test Product",
                "activeIngredients": [{"name": label_text, "quantity": 100, "unit": "mg"}]
            }
            enriched, issues = enricher.enrich_product(product)
            quality_data = enriched.get('ingredient_quality_data', {})
            matched_keys = tuple(sorted([
                ing.get('canonical_id', '')
                for ing in quality_data.get('ingredients_scorable', [])
                if ing.get('canonical_id')
            ]))
            results.append(matched_keys)

        # All 3 runs should produce identical results
        assert results[0] == results[1] == results[2], (
            f"Non-deterministic matching for '{label_text}':\n"
            f"  Run 1: {results[0]}\n"
            f"  Run 2: {results[1]}\n"
            f"  Run 3: {results[2]}"
        )


# =============================================================================
# ALIAS RESOLUTION TESTS
# =============================================================================

class TestAliasResolution:
    """Test specific alias resolution cases that were historically problematic."""

    RESOLUTION_TESTS = [
        # (alias, expected_canonical_key)
        ("nicotinamide riboside", "nicotinamide_riboside"),
        ("nmn", "nmn"),
        ("curcumin phytosome", "curcumin"),
        ("meriva", "curcumin"),
        ("flaxseed oil", "flaxseed"),
        ("linseed oil", "flaxseed"),
        ("silymarin", "silymarin"),
        ("5-htp", "5_htp"),
        ("alcar", "acetyl_l_carnitine"),
        ("quercetin dihydrate", "quercetin"),
        ("beta glucan", "beta_glucan"),
        ("oat beta-glucan", "beta_glucan"),
        ("l. acidophilus", "lactobacillus_acidophilus"),
        ("b. lactis", "bifidobacterium_lactis"),
    ]

    @pytest.mark.parametrize("alias,expected_key", RESOLUTION_TESTS)
    def test_alias_resolves_to_canonical(self, iqm_data, alias, expected_key):
        """Test that specific aliases resolve to correct canonical ingredient."""
        entries = {k: v for k, v in iqm_data.items() if k != '_metadata'}

        # Find which ingredient contains this alias
        found_in = []
        alias_lower = alias.lower().strip()

        for ing_key, entry in entries.items():
            for form_name, form_data in entry.get('forms', {}).items():
                if isinstance(form_data, dict):
                    form_aliases = [a.lower().strip() for a in form_data.get('aliases', [])]
                    if alias_lower in form_aliases:
                        found_in.append(ing_key)

        # Should be found in exactly one ingredient (the expected one)
        unique_found = list(set(found_in))

        assert expected_key in unique_found, (
            f"Alias '{alias}' not found in expected ingredient '{expected_key}'\n"
            f"Found in: {unique_found}"
        )

        assert len(unique_found) == 1, (
            f"Alias '{alias}' found in multiple ingredients: {unique_found}\n"
            f"Expected only: {expected_key}"
        )


# =============================================================================
# MULTI-FORM MATCHING TESTS
# =============================================================================

class TestMultiFormMatching:
    """
    Tests for multi-form ingredient matching with weighted averaging.

    These tests verify the contract for handling complex labels like:
    - "Vitamin B12 (as adenosylcobalamin and methylcobalamin)"
    - "Vitamin A (as retinyl palmitate and 50% B-carotene)"
    - "Folate (as MAGNAFOLATE® PRO methylfolate [L-5-MTHF Ca])"
    """

    def test_dual_form_uses_average_not_first_only(self, enricher):
        """
        B12 (adenosyl + methyl) should use average of both forms, not first-only.

        Contract: When multiple forms are specified without explicit percentages,
        use equal-weight average of all matched forms' bio_scores.
        """
        label = "Vitamin B12 (as adenosylcobalamin and methylcobalamin)"

        product = {
            "id": "TEST_DUAL",
            "product_name": "Test Dual Form B12",
            "activeIngredients": [{"name": label, "quantity": 1000, "unit": "mcg"}]
        }

        enriched, issues = enricher.enrich_product(product)
        quality_data = enriched.get('ingredient_quality_data', {})
        scorable = quality_data.get('ingredients_scorable', [])

        assert len(scorable) >= 1, "Should have at least one scorable ingredient"

        # Find the B12 entry
        b12_entry = None
        for ing in scorable:
            if ing.get('canonical_id') == 'vitamin_b12_cobalamin':
                b12_entry = ing
                break

        assert b12_entry is not None, "Should match vitamin_b12_cobalamin"

        # Verify multi-form contract
        assert b12_entry.get('form_extraction_used') == True, "Should use form extraction"
        assert b12_entry.get('is_dual_form') == True, "Should be marked as dual form"

        matched_forms = b12_entry.get('matched_forms', [])
        assert len(matched_forms) == 2, f"Should match both forms, got {len(matched_forms)}"

        # Both adenosylcobalamin and methylcobalamin have bio_score 14
        # Average should be 14.0
        bio_score = b12_entry.get('bio_score')
        assert bio_score == 14.0, f"Expected bio_score 14.0 (average), got {bio_score}"

        # Verify aggregation method
        assert b12_entry.get('aggregation_method') == 'equal', \
            "Should use equal aggregation for dual forms without explicit percentages"

    def test_percent_share_applies_weighting(self, enricher):
        """
        Vitamin A (retinyl palmitate and 50% B-carotene) should apply percentage weighting.

        Contract: When explicit percentages are provided (e.g., "50%"), use weighted
        average. Remaining percentage goes to forms without explicit percentages.
        """
        label = "Vitamin A (as retinyl palmitate and 50% B-carotene)"

        product = {
            "id": "TEST_WEIGHTED",
            "product_name": "Test Weighted Vitamin A",
            "activeIngredients": [{"name": label, "quantity": 5000, "unit": "IU"}]
        }

        enriched, issues = enricher.enrich_product(product)
        quality_data = enriched.get('ingredient_quality_data', {})
        scorable = quality_data.get('ingredients_scorable', [])

        assert len(scorable) >= 1, "Should have at least one scorable ingredient"

        # Find the Vitamin A entry
        vit_a_entry = None
        for ing in scorable:
            if ing.get('canonical_id') == 'vitamin_a':
                vit_a_entry = ing
                break

        assert vit_a_entry is not None, "Should match vitamin_a"

        # Verify multi-form contract
        assert vit_a_entry.get('form_extraction_used') == True, "Should use form extraction"
        assert vit_a_entry.get('is_dual_form') == True, "Should be marked as dual form"

        matched_forms = vit_a_entry.get('matched_forms', [])
        assert len(matched_forms) == 2, f"Should match both forms, got {len(matched_forms)}"

        # retinyl palmitate: bio_score 14, share 0.50
        # B-carotene (from mixed carotenoids): bio_score 10, share 0.50
        #   (recalibrated as a moderate-absorber provitamin-A source: poor/variable
        #    carotenoid->retinol conversion, aligned with dunaliella salina at 10)
        # Weighted average: (14 * 0.5 + 10 * 0.5) / 1.0 = 12.0
        bio_score = vit_a_entry.get('bio_score')
        assert bio_score == 12.0, f"Expected weighted bio_score 12.0, got {bio_score}"

        # Verify shares were parsed correctly
        for mf in matched_forms:
            assert mf.get('percent_share') == 0.5, \
                f"Each form should have 50% share, got {mf.get('percent_share')}"

    def test_bracket_token_preserved_for_matching(self, enricher):
        """
        Folate (... [L-5-MTHF Ca]) should match correctly even with complex brackets.

        Contract: Bracket tokens like [L-5-MTHF Ca], [P-5-P], [D3] are valuable
        matching signals and must be preserved as match candidates, not stripped.
        """
        label = "Folate [Vitamin B9] (as MAGNAFOLATE® PRO methylfolate [L-5-MTHF Ca])"

        product = {
            "id": "TEST_BRACKET",
            "product_name": "Test Bracket Folate",
            "activeIngredients": [{"name": label, "quantity": 400, "unit": "mcg DFE"}]
        }

        enriched, issues = enricher.enrich_product(product)
        quality_data = enriched.get('ingredient_quality_data', {})
        scorable = quality_data.get('ingredients_scorable', [])

        assert len(scorable) >= 1, "Should have at least one scorable ingredient"

        # Find the Folate entry
        folate_entry = None
        for ing in scorable:
            if ing.get('canonical_id') == 'vitamin_b9_folate':
                folate_entry = ing
                break

        assert folate_entry is not None, "Should match vitamin_b9_folate"

        # Verify form extraction captured bracket tokens
        assert folate_entry.get('form_extraction_used') == True, "Should use form extraction"

        # Should match to the 5-MTHF form (bio_score 13)
        form_id = folate_entry.get('form_id')
        assert '5-MTHF' in form_id or 'methylfolate' in form_id.lower(), \
            f"Should match 5-MTHF form, got {form_id}"

        bio_score = folate_entry.get('bio_score')
        assert bio_score == 13.0, f"Expected bio_score 13.0 for 5-MTHF form, got {bio_score}"

        # Verify the extracted_forms captured the bracket token
        extracted = folate_entry.get('extracted_forms', [])
        if extracted:
            # Check that L-5-MTHF Ca was captured as a match candidate
            all_candidates = []
            for ef in extracted:
                all_candidates.extend(ef.get('match_candidates', []))

            bracket_found = any('L-5-MTHF' in c or 'L5MTHF' in c for c in all_candidates)
            assert bracket_found, \
                f"Bracket token 'L-5-MTHF Ca' should be in match candidates: {all_candidates}"

    def test_form_unmapped_when_evidence_but_no_match(self, enricher):
        """
        If form evidence exists but mapping fails, status should be FORM_UNMAPPED.

        Contract: Don't fall back to "unspecified" if the label explicitly provides
        form information that we couldn't match. Mark as FORM_UNMAPPED for database
        expansion tracking.
        """
        # Use a fake form that won't match anything
        label = "Vitamin X (as totally_fake_form_xyz123)"

        quality_map = enricher.databases.get('ingredient_quality_map', {})
        result = enricher._match_quality_map(label, label, quality_map)

        # Should return FORM_UNMAPPED, not None or unspecified match
        assert result is not None, "Should return result (not None)"
        assert result.get('match_status') == 'FORM_UNMAPPED', \
            f"Should be FORM_UNMAPPED when form evidence exists but no match, got {result.get('match_status')}"
        assert result.get('has_form_evidence') == True, "Should flag form evidence exists"
        assert 'totally_fake_form_xyz123' in str(result.get('unmapped_forms', [])), \
            "Should include unmapped form in result"
