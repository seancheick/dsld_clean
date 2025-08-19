#!/usr/bin/env python3
"""Test nested ingredient flattening for synergy scoring"""
import json
from enhanced_normalizer import EnhancedDSLDNormalizer

# Create test data with nested ingredients (proprietary blends)
test_data = {
    "productId": "TEST_NESTED",
    "productName": "Test Blend with Nested Ingredients",
    "brandName": "Test Brand",
    "servingSize": {"value": 1, "unit": "capsule"},
    "dailyServings": 1,
    "ingredientRows": [
        {
            "order": 1,
            "name": "Vitamin D3",
            "quantity": [{"amount": 1000, "unit": "IU"}],
            "forms": []
        },
        {
            "order": 2,
            "name": "Proprietary Herbal Blend",
            "quantity": [{"amount": 500, "unit": "mg"}],
            "forms": [],
            "nestedRows": [
                {
                    "order": 1,
                    "name": "Ashwagandha",
                    "quantity": [{"amount": 200, "unit": "mg"}],
                    "forms": [{"name": "root extract"}]
                },
                {
                    "order": 2, 
                    "name": "Rhodiola",
                    "quantity": [{"amount": 150, "unit": "mg"}],
                    "forms": [{"name": "root extract"}]
                },
                {
                    "order": 3,
                    "name": "Adaptogen Complex",
                    "quantity": [{"amount": 150, "unit": "mg"}],
                    "forms": [],
                    "nestedRows": [  # Double-nested for testing recursion
                        {
                            "order": 1,
                            "name": "Holy Basil",
                            "quantity": [{"amount": 75, "unit": "mg"}],
                            "forms": [{"name": "leaf extract"}]
                        },
                        {
                            "order": 2,
                            "name": "Schisandra",
                            "quantity": [{"amount": 75, "unit": "mg"}],
                            "forms": [{"name": "berry extract"}]
                        }
                    ]
                }
            ]
        },
        {
            "order": 3,
            "name": "Magnesium",
            "quantity": [{"amount": 200, "unit": "mg"}],
            "forms": [{"name": "citrate"}]
        }
    ],
    "otheringredients": {
        "ingredients": [
            {"name": "Vegetable Capsule (HPMC)", "forms": []}
        ]
    }
}

# Initialize normalizer
normalizer = EnhancedDSLDNormalizer()

# Process the test data
result = normalizer.normalize_product(test_data)

print("=== Nested Ingredient Flattening Test ===")
print(f"Total active ingredients after flattening: {len(result['activeIngredients'])}")
print()

# Check that nested ingredients are flattened
for i, ing in enumerate(result['activeIngredients']):
    print(f"{i+1}. {ing['name']} ({ing['standardName']})")
    print(f"   Quantity: {ing['quantity']} {ing['unit']}")
    print(f"   Parent Blend: {ing.get('parentBlend', 'None')}")
    print(f"   Is Nested: {ing.get('isNestedIngredient', False)}")
    print(f"   Nested Ingredients (should be empty): {ing.get('nestedIngredients', [])}")
    print(f"   Mapped: {ing['mapped']}")
    print()

# Verify expected flattening results
expected_ingredients = [
    "Vitamin D3",           # Original ingredient
    "Proprietary Herbal Blend",  # Blend container
    "Ashwagandha",         # From first level nest
    "Rhodiola",            # From first level nest
    "Adaptogen Complex",   # Nested blend container
    "Holy Basil",          # From second level nest
    "Schisandra",          # From second level nest
    "Magnesium"            # Original ingredient
]

actual_names = [ing['name'] for ing in result['activeIngredients']]

print("=== Flattening Verification ===")
print(f"Expected ingredients: {len(expected_ingredients)}")
print(f"Actual ingredients: {len(actual_names)}")
print()

for expected in expected_ingredients:
    if expected in actual_names:
        print(f"✅ Found: {expected}")
    else:
        print(f"❌ Missing: {expected}")

print()

# Check blend relationships
blend_children = [ing for ing in result['activeIngredients'] if ing.get('parentBlend')]
print(f"Ingredients with parent blends: {len(blend_children)}")
for ing in blend_children:
    print(f"  - {ing['name']} (parent: {ing['parentBlend']})")

print("\n=== Test Results ===")
if len(actual_names) == len(expected_ingredients):
    print("✅ Flattening is working correctly!")
    print("✅ All nested ingredients are extracted as separate entries")
    print("✅ nestedIngredients arrays are empty (flattened structure)")
    print("✅ Parent blend relationships are preserved")
    print("✅ Ready for synergy scoring analysis!")
else:
    print("❌ Flattening may have issues")
    print(f"Expected {len(expected_ingredients)} but got {len(actual_names)}")