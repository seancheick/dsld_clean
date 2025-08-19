#!/usr/bin/env python3
"""
Test script for context-aware ingredient disambiguation
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_normalizer import EnhancedDSLDNormalizer

def test_disambiguation():
    """Test the disambiguation logic with various test cases"""
    
    print("=== Testing Context-Aware Ingredient Disambiguation ===\n")
    
    # Initialize normalizer
    normalizer = EnhancedDSLDNormalizer()
    
    # Test cases based on the disambiguation guide
    # Using more realistic ingredient name formats
    test_cases = [
        {
            "name": "DHA (Fish Oil)",
            "context": "fish oil containing 300mg EPA and 200mg DHA for heart health",
            "expected": "dha (docosahexaenoic acid)",
            "description": "DHA in omega-3 context"
        },
        {
            "name": "DHEA",
            "context": "DHEA supplement for hormone support", 
            "expected": "dhea supplement",
            "description": "DHEA hormone context"
        },
        {
            "name": "ALA",
            "context": "R-ALA 300mg for mitochondrial antioxidant support",
            "expected": "r-alpha-lipoic acid", 
            "description": "Alpha lipoic acid context"
        },
        {
            "name": "ALA",
            "context": "Flaxseed oil rich in ALA omega-3 fatty acids",
            "expected": "flaxseed oil",
            "description": "ALA as alpha linolenic acid"
        },
        {
            "name": "MSM",
            "context": "MSM 1000mg for joint support",
            "expected": "msm (methylsulfonylmethane)",
            "description": "MSM context"
        },
        {
            "name": "DHA",  # Ambiguous case with vitamin C context
            "context": "Vitamin C with dehydroascorbic acid",
            "expected": None,
            "description": "DHA should be excluded in vitamin C context"
        },
        {
            "name": "DHA",  # Ambiguous case
            "context": "",
            "expected": None,
            "description": "Ambiguous DHA with no context"
        },
        {
            "name": "ALA",  # Ambiguous case
            "context": "",
            "expected": None,
            "description": "Ambiguous ALA with no context"
        }
    ]
    
    # Test each case
    for i, test_case in enumerate(test_cases, 1):
        name = test_case["name"]
        context = test_case["context"]
        expected = test_case["expected"]
        description = test_case["description"]
        
        print(f"Test {i}: {description}")
        print(f"Ingredient: '{name}'")
        print(f"Context: '{context}'")
        
        # Test with context by temporarily modifying the ingredient name
        test_name = f"{name} {context}" if context else name
        
        # Test the enhanced ingredient mapping
        standard_name, mapped, mapped_forms = normalizer._enhanced_ingredient_mapping(test_name, [])
        
        print(f"Mapped: {mapped}")
        print(f"Standard name: '{standard_name}'")
        
        if expected:
            # Check if the result matches expected
            success = standard_name.lower() == expected.lower() or expected.lower() in standard_name.lower()
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"Expected: '{expected}'")
        else:
            # For ambiguous cases, we expect no clear mapping
            status = "✅ PASS (ambiguous handled)" if not mapped else "❌ FAIL (should be ambiguous)"
        
        print(f"Result: {status}")
        print("-" * 60)
    
    print("\n=== Testing Alias Detection ===\n")
    
    # Test if DHA is in the ingredient alias lookup
    normalizer.matcher.preprocess_text("dha")
    processed_dha = normalizer.matcher.preprocess_text("dha")
    print(f"Processed 'dha': '{processed_dha}'")
    print(f"'dha' in alias lookup: {processed_dha in normalizer.ingredient_alias_lookup}")
    print(f"'dha' in context lookup: {processed_dha in normalizer.ingredient_context_lookup}")
    
    if processed_dha in normalizer.ingredient_context_lookup:
        context_data = normalizer.ingredient_context_lookup[processed_dha]
        print(f"Context data for 'dha': {context_data}")
    
    # Test a simple DHA match
    print(f"\nTesting simple 'DHA' match:")
    standard_name, mapped, mapped_forms = normalizer._enhanced_ingredient_mapping("DHA", [])
    print(f"Result: '{standard_name}', mapped: {mapped}")
    
    print("\n=== Testing Direct Disambiguation Function ===\n")
    
    # Test the disambiguation function directly
    matcher = normalizer.matcher
    
    # Test DHA omega-3 context
    context_text = "fish oil containing 300mg epa and 200mg dha for heart health"
    form_data = {
        "context_include": ["omega", "epa", "fish", "oil", "marine", "triglyceride", "22:6", "fatty", "acid"],
        "context_exclude": ["dehydroascorbic", "dehydroepiandrosterone", "vitamin", "c", "hormone"]
    }
    
    print(f"Context text: '{context_text}'")
    print(f"Include words: {form_data['context_include']}")
    print(f"Exclude words: {form_data['context_exclude']}")
    
    # Check which include words are found
    include_found = [word for word in form_data['context_include'] if word.lower() in context_text]
    exclude_found = [word for word in form_data['context_exclude'] if word.lower() in context_text]
    
    print(f"Include words found: {include_found}")
    print(f"Exclude words found: {exclude_found}")
    
    result = matcher.disambiguate_ingredient_match(context_text, form_data)
    print(f"DHA omega-3 context test: {result} (expected: True)")
    
    # Test DHEA hormone context  
    context_text = "dhea supplement for hormone support and energy"
    form_data = {
        "context_include": ["hormone", "precursor", "prasterone", "steroid"],
        "context_exclude": ["omega", "epa", "fish", "oil", "fatty", "acid", "vitamin", "c"]
    }
    
    result = matcher.disambiguate_ingredient_match(context_text, form_data)
    print(f"DHEA hormone context test: {result} (expected: True)")
    
    # Test exclusion (DHA in vitamin C context)
    context_text = "vitamin c with dehydroascorbic acid"
    form_data = {
        "context_include": ["omega", "epa", "fish", "oil", "marine", "triglyceride", "22:6", "fatty", "acid"],
        "context_exclude": ["dehydroascorbic", "dehydroepiandrosterone", "vitamin", "c", "hormone"]
    }
    
    result = matcher.disambiguate_ingredient_match(context_text, form_data)
    print(f"DHA exclusion test: {result} (expected: False)")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_disambiguation()