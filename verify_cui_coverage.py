#!/usr/bin/env python3
"""
Verify CUI/RXCUI coverage and create a summary report
"""

import json
from pathlib import Path

def verify_cui_coverage():
    """Check which ingredients have CUI/RXCUI codes and generate a report"""
    
    file_path = Path("scripts/data/ingredient_quality_map.json")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Expected main vitamins and minerals that should have codes
    expected_ingredients = [
        "vitamin_a", "vitamin_b1_thiamine", "vitamin_b2_riboflavin", 
        "vitamin_b3_niacin", "vitamin_b5_pantothenic", "vitamin_b6_pyridoxine",
        "vitamin_b7_biotin", "vitamin_b9_folate", "vitamin_b12_cobalamin",
        "vitamin_c", "vitamin_d", "vitamin_e", "vitamin_k",
        "calcium", "phosphorus", "magnesium", "iron", "zinc", 
        "selenium", "copper", "chromium", "manganese", "molybdenum", 
        "boron", "potassium"
    ]
    
    print("🔍 CUI/RXCUI COVERAGE REPORT")
    print("=" * 60)
    
    # Check main vitamins and minerals
    print("\n📊 Main Vitamins & Minerals:")
    print("-" * 40)
    
    main_with_codes = 0
    main_missing_codes = 0
    
    for ingredient in expected_ingredients:
        if ingredient in data:
            ing_data = data[ingredient]
            has_cui = "cui" in ing_data
            has_rxcui = "rxcui" in ing_data
            
            if has_cui and has_rxcui:
                status = "✅"
                main_with_codes += 1
                cui_val = ing_data["cui"]
                rxcui_val = ing_data["rxcui"]
                print(f"{status} {ingredient}: CUI={cui_val}, RXCUI={rxcui_val}")
            else:
                status = "❌"
                main_missing_codes += 1
                missing = []
                if not has_cui: missing.append("CUI")
                if not has_rxcui: missing.append("RXCUI") 
                print(f"{status} {ingredient}: Missing {', '.join(missing)}")
        else:
            print(f"⚠️  {ingredient}: Not found in data")
            main_missing_codes += 1
    
    # Check all ingredients
    print(f"\n📈 Overall Statistics:")
    print("-" * 30)
    
    total_ingredients = len(data)
    total_with_cui = sum(1 for ing in data.values() if "cui" in ing)
    total_with_rxcui = sum(1 for ing in data.values() if "rxcui" in ing)
    
    print(f"Total ingredients: {total_ingredients}")
    print(f"Ingredients with CUI: {total_with_cui} ({total_with_cui/total_ingredients*100:.1f}%)")
    print(f"Ingredients with RXCUI: {total_with_rxcui} ({total_with_rxcui/total_ingredients*100:.1f}%)")
    
    print(f"\nMain vitamins/minerals with codes: {main_with_codes}/{len(expected_ingredients)}")
    print(f"Main vitamins/minerals missing codes: {main_missing_codes}/{len(expected_ingredients)}")
    
    # Show some examples of ingredients with codes
    print(f"\n🔬 Sample Ingredients with CUI/RXCUI:")
    print("-" * 40)
    
    count = 0
    for ing_key, ing_data in data.items():
        if "cui" in ing_data and "rxcui" in ing_data and count < 5:
            cui = ing_data["cui"]
            rxcui = ing_data["rxcui"]
            name = ing_data.get("standard_name", "N/A")
            print(f"  {ing_key}: {name}")
            print(f"    CUI: {cui}, RXCUI: {rxcui}")
            count += 1
    
    # Overall assessment
    print(f"\n🎯 ASSESSMENT:")
    print("-" * 20)
    
    if main_missing_codes == 0:
        print("🎉 EXCELLENT: All main vitamins and minerals have CUI/RXCUI codes!")
    elif main_missing_codes <= 2:
        print("✅ GOOD: Most main vitamins and minerals have codes")
    else:
        print("⚠️  NEEDS WORK: Several main ingredients missing codes")
    
    coverage_rate = (main_with_codes / len(expected_ingredients)) * 100
    print(f"📊 Main ingredient coverage: {coverage_rate:.1f}%")
    
    return coverage_rate

if __name__ == "__main__":
    verify_cui_coverage()