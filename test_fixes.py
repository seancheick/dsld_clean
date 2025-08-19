#!/usr/bin/env python3
"""Test script to verify the fixes for unmapped ingredients and proprietary blend detection"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / "scripts"))

from enhanced_normalizer import EnhancedDSLDNormalizer
from constants import EXCLUDED_LABEL_PHRASES, PROPRIETARY_BLEND_INDICATORS

def test_exclusions():
    """Test that 'Contains <2% of' variations are properly excluded"""
    print("Testing label phrase exclusions...")
    
    normalizer = EnhancedDSLDNormalizer()
    
    test_cases = [
        "Contains <2% of",
        "Contains <2% of:",
        "contains less than 2% of",
        "Contains 2% or less of"
    ]
    
    for test_name in test_cases:
        is_excluded = normalizer._is_nutrition_fact(test_name)
        print(f"  '{test_name}': {'✓ Excluded' if is_excluded else '✗ NOT excluded (ERROR)'}")
    
    print()

def test_proprietary_blend_detection():
    """Test that proprietary blend detection works with name indicators"""
    print("Testing proprietary blend detection...")
    
    normalizer = EnhancedDSLDNormalizer()
    
    test_cases = [
        ("Immune Support Matrix", True),
        ("Energy Blend", True),
        ("Digestive Enzyme Complex", True),
        ("Vitamin C", False),
        ("Calcium Carbonate", False),
        ("Proprietary Herbal Formula", True)
    ]
    
    for test_name, expected in test_cases:
        is_proprietary = normalizer._is_proprietary_blend_name(test_name)
        status = "✓" if is_proprietary == expected else "✗"
        print(f"  '{test_name}': {status} {'Proprietary' if is_proprietary else 'Not proprietary'}")
    
    print()

def test_full_ingredient_processing():
    """Test full ingredient processing with our fixes"""
    print("Testing full ingredient processing...")
    
    normalizer = EnhancedDSLDNormalizer()
    
    # Test ingredient that should be excluded
    test_ing_1 = {
        "name": "Contains <2% of",
        "quantity": [],
        "forms": []
    }
    
    result_1 = normalizer._process_single_ingredient_enhanced(test_ing_1, is_active=True)
    print(f"  'Contains <2% of': {'✓ Excluded (None)' if result_1 is None else '✗ NOT excluded (ERROR)'}")
    
    # Test proprietary blend
    test_ing_2 = {
        "name": "Digestive Support Blend",
        "quantity": [{"value": 500, "unit": "mg"}],
        "forms": []
    }
    
    result_2 = normalizer._process_single_ingredient_enhanced(test_ing_2, is_active=True)
    if result_2:
        is_prop = result_2.get("isProprietaryBlend", False)
        print(f"  'Digestive Support Blend': {'✓ Marked as proprietary' if is_prop else '✗ NOT marked as proprietary (ERROR)'}")
    
    print()

def check_constants():
    """Verify constants are properly formatted"""
    print("Checking constants...")
    
    # Check that EXCLUDED_LABEL_PHRASES are all lowercase
    all_lowercase = all(phrase == phrase.lower() for phrase in EXCLUDED_LABEL_PHRASES)
    print(f"  EXCLUDED_LABEL_PHRASES all lowercase: {'✓' if all_lowercase else '✗ (ERROR)'}")
    
    # Check specific entries
    expected_phrases = ["contains <2% of", "contains <2% of:", "contains less than 2% of"]
    for phrase in expected_phrases:
        in_set = phrase in EXCLUDED_LABEL_PHRASES
        print(f"    '{phrase}' in set: {'✓' if in_set else '✗'}")
    
    print()

if __name__ == "__main__":
    print("=" * 60)
    print("Testing fixes for unmapped ingredients and proprietary blends")
    print("=" * 60)
    print()
    
    check_constants()
    test_exclusions()
    test_proprietary_blend_detection()
    test_full_ingredient_processing()
    
    print("=" * 60)
    print("Tests complete!")
    print("=" * 60)