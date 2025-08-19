#!/usr/bin/env python3
"""Test the enhanced schema with enrichment fields and nutritional warnings"""
import json
from enhanced_normalizer import EnhancedDSLDNormalizer

# Create test data with nutritional facts
test_data = {
    "productId": "TEST123",
    "productName": "Test Supplement with Nutritionals",
    "brandName": "Test Brand",
    "servingSize": {
        "value": 2,
        "unit": "capsules"
    },
    "dailyServings": 1,
    "ingredientRows": [
        {
            "order": 1,
            "name": "Vitamin C",
            "quantity": [{"amount": 500, "unit": "mg"}],
            "forms": [{"name": "ascorbic acid"}]
        },
        {
            "order": 2,
            "name": "Alpha-Lipoic Acid",
            "quantity": [{"amount": 300, "unit": "mg"}],
            "forms": []
        }
    ],
    "otheringredients": {
        "ingredients": [
            {
                "name": "Vegetable Capsule (HPMC)",
                "forms": []
            },
            {
                "name": "Total Sugars",
                "quantity": [{"amount": 2, "unit": "g"}],
                "forms": []
            },
            {
                "name": "Sodium", 
                "quantity": [{"amount": 200, "unit": "mg"}],
                "forms": []
            },
            {
                "name": "Saturated Fat",
                "quantity": [{"amount": 3, "unit": "g"}],
                "forms": []
            }
        ]
    },
    "servingSize": {
        "value": 2,
        "unit": "capsules"
    }
}

# Initialize normalizer
normalizer = EnhancedDSLDNormalizer()

# Process the test data
result = normalizer.normalize_product(test_data)

# Debug: Print the raw result
print("Raw result keys:", list(result.keys()))
if 'ingredientRows' in test_data:
    print(f"Input had {len(test_data['ingredientRows'])} ingredients in ingredientRows")

# Check active ingredients for enrichment fields
print("\n=== Active Ingredients Schema Test ===")
print(f"Total active ingredients: {len(result['activeIngredients'])}")

for i, ing in enumerate(result['activeIngredients']):
    print(f"\nIngredient {i+1}: {ing['name']}")
    print(f"  Standard Name: {ing['standardName']}")
    print(f"  Mapped: {ing['mapped']}")
    
    # Check enrichment placeholders
    print("  Enrichment placeholders:")
    print(f"    - clinicalEvidence: {ing.get('clinicalEvidence')}")
    print(f"    - synergyClusters: {ing.get('synergyClusters')}")
    print(f"    - enhancedDelivery: {ing.get('enhancedDelivery')}")
    print(f"    - brandedForm: {ing.get('brandedForm')}")

# Check nutritional warnings
print("\n=== Nutritional Warnings Test ===")
warnings = result.get('nutritionalWarnings', {})
print(f"Nutritional warnings structure: {json.dumps(warnings, indent=2)}")

# Verify the schema
print("\n=== Schema Validation ===")
expected_warning_keys = ['excessiveDoses', 'sugarContent', 'sodiumContent', 'fatContent']
for key in expected_warning_keys:
    if key in warnings:
        print(f"✅ {key}: {warnings[key]}")
    else:
        print(f"❌ Missing key: {key}")

print("\n=== Test Complete ===")
print("Schema is ready for enrichment phase!")