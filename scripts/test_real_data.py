#!/usr/bin/env python3
"""
Test disambiguation with real DSLD data
"""

import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_normalizer import EnhancedDSLDNormalizer

def test_with_real_data():
    """Test disambiguation with real DSLD data"""
    
    print("=== Testing Disambiguation with Real DSLD Data ===\n")
    
    # Initialize normalizer
    normalizer = EnhancedDSLDNormalizer()
    
    # Test file path
    test_file = "./output_Lozenges/cleaned/cleaned_batch_1.json"
    
    try:
        with open(test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"Loaded {len(data)} products from {test_file}")
        
        # Find products with DHA, ALA, DHEA, or MSM in their ingredients
        target_aliases = ['dha', 'ala', 'dhea', 'msm']
        
        found_products = []
        
        for product in data:
            product_name = product.get('productName', '')
            active_ingredients = product.get('activeIngredients', [])
            inactive_ingredients = product.get('inactiveIngredients', [])
            
            all_ingredients = active_ingredients + inactive_ingredients
            
            for ingredient in all_ingredients:
                ing_name = ingredient.get('standardName', '').lower()
                
                for alias in target_aliases:
                    if alias in ing_name:
                        found_products.append({
                            'product_name': product_name,
                            'ingredient_name': ing_name,
                            'alias_found': alias,
                            'is_active': ingredient in active_ingredients
                        })
                        break
        
        print(f"\nFound {len(found_products)} ingredients containing target aliases:")
        
        for match in found_products[:10]:  # Show first 10
            print(f"- Product: {match['product_name'][:50]}...")
            print(f"  Ingredient: {match['ingredient_name']}")
            print(f"  Alias: {match['alias_found']}")
            print(f"  Active: {match['is_active']}")
            print()
        
        if len(found_products) > 10:
            print(f"... and {len(found_products) - 10} more")
        
        # Test ingredient mapping on some raw ingredients
        print("\n=== Testing Raw Ingredient Processing ===\n")
        
        test_ingredients = [
            "Fish Oil (DHA 200mg, EPA 300mg)",
            "DHA from Algae",
            "DHEA 25mg",
            "Alpha-Lipoic Acid (ALA)",
            "MSM 1000mg",
            "Vitamin C (with dehydroascorbic acid)",
            "Flaxseed Oil (ALA source)"
        ]
        
        for ingredient in test_ingredients:
            print(f"Testing: '{ingredient}'")
            standard_name, mapped, mapped_forms = normalizer._enhanced_ingredient_mapping(ingredient, [])
            print(f"Result: '{standard_name}', mapped: {mapped}")
            print("-" * 50)
            
    except FileNotFoundError:
        print(f"File not found: {test_file}")
        print("This is normal if no data has been processed yet.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_with_real_data()