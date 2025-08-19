#!/usr/bin/env python3
"""Comprehensive test script for all detection systems in the DSLD cleaning pipeline"""

import sys
import json
import re
from pathlib import Path
sys.path.append(str(Path(__file__).parent / "scripts"))

from enhanced_normalizer import EnhancedDSLDNormalizer
from constants import (
    EXCLUDED_LABEL_PHRASES, 
    PROPRIETARY_BLEND_INDICATORS,
    CERTIFICATION_PATTERNS,
    ALLERGEN_FREE_PATTERNS
)

def test_proprietary_blend_detection():
    """Test proprietary blend detection from both reference file and name indicators"""
    print("=" * 60)
    print("TESTING PROPRIETARY BLEND DETECTION")
    print("=" * 60)
    
    normalizer = EnhancedDSLDNormalizer()
    
    # Test 1: Check if proprietary_blends_penalty.json is loaded
    print("\n1. Checking proprietary_blends_penalty.json loading:")
    if hasattr(normalizer, 'proprietary_blends') and normalizer.proprietary_blends:
        concerns = normalizer.proprietary_blends.get("proprietary_blend_concerns", [])
        print(f"   ✓ Loaded {len(concerns)} proprietary blend concerns from JSON")
        
        # Test a known blend from the file
        test_blend = "Proprietary Digestive Enzyme Blend"
        is_in_db = normalizer._check_proprietary_blends(test_blend)
        print(f"   Testing '{test_blend}': {'✓ Found in database' if is_in_db else '✗ Not found'}")
    else:
        print("   ✗ proprietary_blends_penalty.json not loaded!")
    
    # Test 2: Name-based detection
    print("\n2. Testing name-based proprietary blend detection:")
    test_cases = [
        ("Energy Matrix", True),
        ("Digestive Blend", True),
        ("Immune Complex", True),
        ("Super Greens Formula", True),
        ("Vitamin C", False),
        ("Magnesium Oxide", False),
        ("Proprietary Herbal Stack", True),
        ("Amino Acid Compound", True)
    ]
    
    for name, expected in test_cases:
        is_proprietary = normalizer._is_proprietary_blend_name(name)
        status = "✓" if is_proprietary == expected else "✗"
        print(f"   {status} '{name}': {'Proprietary' if is_proprietary else 'Not proprietary'}")
    
    # Test 3: Full ingredient processing with proprietary detection
    print("\n3. Testing full ingredient processing:")
    test_ing = {
        "name": "Digestive Support Matrix",
        "quantity": [{"value": 500, "unit": "mg"}],
        "forms": [],
        "notes": ""
    }
    
    result = normalizer._process_single_ingredient_enhanced(test_ing, is_active=True)
    if result:
        is_prop = result.get("isProprietaryBlend", False)
        print(f"   'Digestive Support Matrix' with quantity: {'✓ Marked as proprietary' if is_prop else '✗ NOT proprietary'}")
    
    print()

def test_certification_detection():
    """Test certification pattern detection including newly added ones"""
    print("=" * 60)
    print("TESTING CERTIFICATION DETECTION")
    print("=" * 60)
    
    # Test certification patterns
    test_statements = [
        ("NSF Certified for Sport", ["NSF"]),
        ("NSF Contents Certified", ["NSF"]),
        ("NSF/ANSI 173 certified", ["NSF"]),
        ("USP Verified product", ["USP"]),
        ("ConsumerLab Approved", ["ConsumerLab"]),
        ("Informed Sport certified", ["Informed-Sport"]),
        ("Informed Choice tested", ["Informed-Choice"]),
        ("BSCG Certified Drug Free", ["BSCG"]),
        ("IFOS 5-Star rated omega-3", ["IFOS"]),
        ("GMP facility manufactured", ["GMP"]),
        ("USDA Organic certified", ["Organic"]),
        ("Non-GMO Project Verified", ["Non-GMO"]),
        ("Third-Party Tested for purity", ["Third-Party"]),
        ("NSF Sport and USP Verified", ["NSF", "USP"])
    ]
    
    print("\nTesting certification pattern matching:")
    for statement, expected_certs in test_statements:
        found_certs = []
        for cert_name, pattern in CERTIFICATION_PATTERNS.items():
            if re.search(pattern, statement, re.IGNORECASE):
                found_certs.append(cert_name)
        
        matches = set(found_certs) == set(expected_certs)
        status = "✓" if matches else "✗"
        print(f"   {status} '{statement}' -> {found_certs}")
    
    print()

def test_allergen_detection():
    """Test allergen detection from reference file"""
    print("=" * 60)
    print("TESTING ALLERGEN DETECTION")
    print("=" * 60)
    
    normalizer = EnhancedDSLDNormalizer()
    
    # Test if allergens database is loaded
    print("\n1. Checking allergens.json loading:")
    if hasattr(normalizer, 'allergens_db') and normalizer.allergens_db:
        allergens = normalizer.allergens_db.get("common_allergens", [])
        print(f"   ✓ Loaded {len(allergens)} allergens from database")
    else:
        print("   ✗ allergens.json not loaded!")
    
    # Test allergen detection
    print("\n2. Testing allergen detection:")
    test_allergens = [
        ("Milk Protein", True),
        ("Whey", True),
        ("Soy Lecithin", True),
        ("Wheat", True),
        ("Peanut Oil", True),
        ("Shellfish", True),
        ("Vitamin C", False),
        ("Magnesium", False)
    ]
    
    for ingredient, should_be_allergen in test_allergens:
        result = normalizer._enhanced_allergen_check(ingredient)
        is_allergen = result["is_allergen"]
        matches = is_allergen == should_be_allergen
        status = "✓" if matches else "✗"
        
        if is_allergen:
            print(f"   {status} '{ingredient}': Allergen ({result['type']}, severity: {result['severity']})")
        else:
            print(f"   {status} '{ingredient}': Not an allergen")
    
    # Test allergen-free patterns
    print("\n3. Testing allergen-free claim detection:")
    test_claims = [
        "Gluten-Free certified",
        "Dairy Free product",
        "Soy-Free formula",
        "Nut Free facility"
    ]
    
    for claim in test_claims:
        found_free = []
        for allergen, pattern in ALLERGEN_FREE_PATTERNS.items():
            if re.search(pattern, claim, re.IGNORECASE):
                found_free.append(allergen)
        print(f"   '{claim}' -> Free from: {found_free}")
    
    print()

def test_harmful_additives_detection():
    """Test harmful additives detection"""
    print("=" * 60)
    print("TESTING HARMFUL ADDITIVES DETECTION")
    print("=" * 60)
    
    normalizer = EnhancedDSLDNormalizer()
    
    # Test if harmful additives database is loaded
    print("\n1. Checking harmful_additives.json loading:")
    if hasattr(normalizer, 'harmful_additives') and normalizer.harmful_additives:
        categories = normalizer.harmful_additives.keys()
        total_additives = sum(len(normalizer.harmful_additives[cat]) for cat in categories)
        print(f"   ✓ Loaded {total_additives} harmful additives across {len(categories)} categories")
    else:
        print("   ✗ harmful_additives.json not loaded!")
    
    # Test harmful detection
    print("\n2. Testing harmful additives detection:")
    test_additives = [
        ("Titanium Dioxide", "dye"),
        ("Red 40", "dye"),
        ("Aspartame", "sweetener"),
        ("BHA", "preservative"),
        ("Natural Flavor", "flavor"),
        ("Vitamin C", "none"),
        ("Calcium", "none")
    ]
    
    for additive, expected_category in test_additives:
        result = normalizer._enhanced_harmful_check(additive)
        category = result["category"]
        matches = category == expected_category
        status = "✓" if matches else "✗"
        
        if category != "none":
            print(f"   {status} '{additive}': {category} (risk: {result['risk_level']})")
        else:
            print(f"   {status} '{additive}': Not harmful")
    
    print()

def test_label_phrase_exclusions():
    """Test that label phrases are properly excluded"""
    print("=" * 60)
    print("TESTING LABEL PHRASE EXCLUSIONS")
    print("=" * 60)
    
    normalizer = EnhancedDSLDNormalizer()
    
    print("\n1. Testing 'Contains <2% of' variations:")
    test_phrases = [
        "Contains <2% of",
        "Contains <2% of:",
        "contains less than 2% of",
        "Contains 2% or less of",
        "less than 2%",
        "<2% of"
    ]
    
    all_excluded = True
    for phrase in test_phrases:
        is_excluded = normalizer._is_nutrition_fact(phrase)
        status = "✓" if is_excluded else "✗"
        print(f"   {status} '{phrase}': {'Excluded' if is_excluded else 'NOT excluded (ERROR)'}")
        if not is_excluded:
            all_excluded = False
    
    print("\n2. Testing other common exclusions:")
    other_phrases = [
        "Other Ingredients",
        "Inactive Ingredients", 
        "May contain",
        "Calories from fat"
    ]
    
    for phrase in other_phrases:
        is_excluded = normalizer._is_nutrition_fact(phrase)
        status = "✓" if is_excluded else "✗"
        print(f"   {status} '{phrase}': {'Excluded' if is_excluded else 'NOT excluded'}")
    
    print()
    return all_excluded

def test_integrated_mapping():
    """Test that all detection systems work together for ingredient mapping"""
    print("=" * 60)
    print("TESTING INTEGRATED INGREDIENT MAPPING")
    print("=" * 60)
    
    normalizer = EnhancedDSLDNormalizer()
    
    print("\nTesting that ingredients are marked as 'mapped' when found in ANY database:")
    
    test_ingredients = [
        ("Vitamin C", "ingredient_quality_map", True),
        ("Milk Protein", "allergens", True),
        ("Red 40", "harmful_additives", True),
        ("Proprietary Enzyme Blend", "proprietary_blends or name", True),
        ("CompletelyUnknownIngredient123", "none", False)
    ]
    
    for name, expected_db, should_be_mapped in test_ingredients:
        ing = {
            "name": name,
            "quantity": [{"value": 100, "unit": "mg"}],
            "forms": [],
            "notes": ""
        }
        
        result = normalizer._process_single_ingredient_enhanced(ing, is_active=True)
        if result:
            is_mapped = result.get("mapped", False)
            matches = is_mapped == should_be_mapped
            status = "✓" if matches else "✗"
            print(f"   {status} '{name}' -> Mapped: {is_mapped} (via {expected_db})")
    
    print()

def main():
    print("\n" + "=" * 60)
    print("COMPREHENSIVE DETECTION SYSTEMS TEST")
    print("=" * 60)
    
    # Run all tests
    test_proprietary_blend_detection()
    test_certification_detection()
    test_allergen_detection()
    test_harmful_additives_detection()
    label_ok = test_label_phrase_exclusions()
    test_integrated_mapping()
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("\n✅ All detection systems tested:")
    print("   • Proprietary blend detection (JSON file + name indicators)")
    print("   • Certification patterns (including new: NSF Sport, BSCG, IFOS, etc.)")
    print("   • Allergen detection")
    print("   • Harmful additives detection")
    print("   • Label phrase exclusions" + (" ✓" if label_ok else " - NEEDS ATTENTION"))
    print("   • Integrated mapping (checks all databases)")
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()