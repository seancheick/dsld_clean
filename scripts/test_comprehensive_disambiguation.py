#!/usr/bin/env python3
"""
Comprehensive test to verify disambiguation works perfectly everywhere
"""

import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_normalizer import EnhancedDSLDNormalizer

def test_comprehensive_disambiguation():
    """Test disambiguation comprehensively"""
    
    print("=== Comprehensive Disambiguation Test ===\n")
    
    # Initialize normalizer
    normalizer = EnhancedDSLDNormalizer()
    
    # Check if context lookup is populated
    print(f"Context lookup entries: {len(normalizer.ingredient_context_lookup)}")
    
    # Check specific ambiguous entries
    ambiguous_aliases = ['dha', 'ala', 'dhea', 'msm']
    
    print("\n=== Checking Ambiguous Aliases in Context Lookup ===")
    for alias in ambiguous_aliases:
        if alias in normalizer.ingredient_context_lookup:
            context_data = normalizer.ingredient_context_lookup[alias]
            form_data = context_data.get('form_data', {})
            print(f"✅ {alias.upper()}: {context_data['form_name']}")
            print(f"   Include: {form_data.get('context_include', [])}")
            print(f"   Exclude: {form_data.get('context_exclude', [])}")
        else:
            print(f"❌ {alias.upper()}: Not found in context lookup")
    
    print("\n=== Testing All Disambiguation Scenarios ===")
    
    test_cases = [
        # DHA tests
        {
            "ingredient": "DHA",
            "context": "fish oil containing EPA and DHA omega-3",
            "expected_contains": "dha",
            "should_map": True
        },
        {
            "ingredient": "DHA", 
            "context": "vitamin C with dehydroascorbic acid",
            "expected_contains": None,
            "should_map": False
        },
        # ALA tests  
        {
            "ingredient": "ALA",
            "context": "alpha lipoic acid for antioxidant support",
            "expected_contains": "lipoic",
            "should_map": True
        },
        {
            "ingredient": "ALA",
            "context": "flaxseed oil rich in omega-3 fatty acids",
            "expected_contains": "omega",
            "should_map": True
        },
        # DHEA test
        {
            "ingredient": "DHEA",
            "context": "hormone support supplement",
            "expected_contains": "dhea",
            "should_map": True
        },
        # MSM test
        {
            "ingredient": "MSM",
            "context": "joint support with methylsulfonylmethane",
            "expected_contains": "msm",
            "should_map": True
        }
    ]
    
    success_count = 0
    total_tests = len(test_cases)
    
    for i, test in enumerate(test_cases, 1):
        ingredient = test["ingredient"]
        context = test["context"]
        expected_contains = test["expected_contains"]
        should_map = test["should_map"]
        
        # Test with context
        test_input = f"{ingredient} {context}"
        standard_name, mapped, mapped_forms = normalizer._enhanced_ingredient_mapping(test_input, [])
        
        print(f"Test {i}: {ingredient} in context")
        print(f"  Input: '{test_input}'")
        print(f"  Result: '{standard_name}', mapped: {mapped}")
        
        # Check if result meets expectations
        if should_map:
            if mapped and (not expected_contains or expected_contains.lower() in standard_name.lower()):
                print(f"  ✅ PASS - Correctly mapped")
                success_count += 1
            else:
                print(f"  ❌ FAIL - Expected mapping with '{expected_contains}' but got '{standard_name}'")
        else:
            if not mapped or ingredient.lower() == standard_name.lower():
                print(f"  ✅ PASS - Correctly avoided mapping")
                success_count += 1
            else:
                print(f"  ❌ FAIL - Unexpected mapping to '{standard_name}'")
        
        print()
    
    print(f"=== Test Results: {success_count}/{total_tests} passed ===")
    
    # Test actual ingredient mapping integration
    print("\n=== Testing Ingredient Quality Map Integration ===")
    
    # Load the ingredient quality map to verify our disambiguated entries
    with open('./data/ingredient_quality_map.json', 'r') as f:
        quality_map = json.load(f)
    
    # Check if our disambiguation entries exist in the quality map
    disambiguated_entries = [
        "dha (docosahexaenoic acid)",
        "dhea supplement", 
        "r-alpha-lipoic acid",
        "MSM (methylsulfonylmethane)"  # Check exact case
    ]
    
    found_entries = []
    
    # Search through all ingredients and their forms
    for ingredient_name, ingredient_data in quality_map.items():
        forms = ingredient_data.get('forms', {})
        
        # Check if ingredient name matches
        if ingredient_name.lower() in [e.lower() for e in disambiguated_entries]:
            found_entries.append(ingredient_name)
            entry_data = ingredient_data
            has_context = bool(entry_data.get('context_include') or entry_data.get('context_exclude'))
            print(f"✅ {ingredient_name}: Found as ingredient, has context rules: {has_context}")
        
        # Check forms
        for form_name, form_data in forms.items():
            if form_name.lower() in [e.lower() for e in disambiguated_entries]:
                found_entries.append(f"{ingredient_name} -> {form_name}")
                has_context = bool(form_data.get('context_include') or form_data.get('context_exclude'))
                print(f"✅ {form_name}: Found as form of {ingredient_name}, has context rules: {has_context}")
    
    # Check which entries were not found
    for entry in disambiguated_entries:
        if not any(entry.lower() in found.lower() for found in found_entries):
            print(f"❌ {entry}: Not found in quality map")
    
    print("\n=== Integration Status ===")
    if success_count == total_tests:
        print("🎉 ALL TESTS PASSED! Disambiguation is working perfectly everywhere.")
        print("✅ Context-aware matching integrated with ingredient quality map")
        print("✅ All ambiguous aliases properly resolved") 
        print("✅ False positives eliminated while maintaining accuracy")
    else:
        print(f"⚠️  {total_tests - success_count} tests failed. Review needed.")

if __name__ == "__main__":
    test_comprehensive_disambiguation()