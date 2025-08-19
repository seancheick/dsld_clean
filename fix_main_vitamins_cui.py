#!/usr/bin/env python3
"""
Fix missing CUI/RXCUI codes specifically for main vitamins and minerals
"""

import json
from pathlib import Path

def add_main_cui_codes():
    """Add CUI/RXCUI codes to main vitamins and minerals"""
    
    file_path = Path("scripts/data/ingredient_quality_map.json")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Define the exact ingredients that need CUI/RXCUI codes
    main_codes = [
        ("vitamin_a", "C0042839", "11149"),
        ("vitamin_b1_thiamine", "C0039840", "10405"),
        ("vitamin_b2_riboflavin", "C0035527", "9220"), 
        ("vitamin_b3_niacin", "C0027996", "7454"),
        ("vitamin_b5_pantothenic", "C0030342", "7896"),
        ("vitamin_b6_pyridoxine", "C0034274", "8696"),
        ("vitamin_b7_biotin", "C0005575", "1116"),
        ("vitamin_b9_folate", "C0016448", "4492"),
        ("vitamin_b12_cobalamin", "C0042845", "11256"),
        ("vitamin_c", "C0003968", "982"),
        ("vitamin_d", "C0042866", "11256"),
        ("vitamin_e", "C0042874", "11256"),
        ("vitamin_k", "C0042878", "11256"),
        ("calcium", "C0006675", "1924"),
        ("phosphorus", "C0031705", "8134"),
        ("magnesium", "C0024467", "6917"),
        ("iron", "C0302583", "6048"),
        ("zinc", "C0043481", "11741"),
        ("selenium", "C0036581", "9786"),
        ("copper", "C0009968", "3008"),
        ("chromium", "C0008574", "2599"),
        ("manganese", "C0024706", "6951"),
        ("molybdenum", "C0026982", "7455"),
        ("boron", "C0006029", "1374"),
        ("potassium", "C0032821", "8588"),
        ("choline", "C0008405", "2650"),
        ("inositol", "C0021547", "6038"),
        ("alpha_lipoic_acid", "C0023791", "6809"),
        ("glutathione", "C0017817", "4411"),
        ("omega_3", "C0015689", "none"),
        ("coq10", "C0056077", "2623"),
        ("turmeric", "C0209960", "11178"),
        ("probiotics", "C0525033", "none"),
        ("spirulina", "C0246293", "none"),
        ("nmn", "C0068719", "none")
    ]
    
    added_count = 0
    
    print("🔧 Adding CUI/RXCUI codes to main vitamins and minerals...")
    print("-" * 60)
    
    for ingredient_key, cui_code, rxcui_code in main_codes:
        if ingredient_key in data:
            ingredient = data[ingredient_key]
            
            # Add CUI code if missing
            if "cui" not in ingredient:
                ingredient["cui"] = cui_code
                print(f"✅ Added CUI {cui_code} to {ingredient_key}")
                added_count += 1
            
            # Add RXCUI code if missing  
            if "rxcui" not in ingredient:
                ingredient["rxcui"] = rxcui_code
                print(f"✅ Added RXCUI {rxcui_code} to {ingredient_key}")
        else:
            print(f"⚠️  Ingredient '{ingredient_key}' not found in data")
    
    print(f"\n📊 Added CUI/RXCUI codes to {added_count} main ingredients")
    
    # Save the updated data
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Updated: {file_path}")
    
    # Verify the additions
    print("\n🔍 Verification - checking key vitamins:")
    key_vitamins = ["vitamin_a", "vitamin_c", "vitamin_d", "calcium", "iron", "zinc"]
    
    for vitamin in key_vitamins:
        if vitamin in data:
            ing = data[vitamin]
            cui = ing.get("cui", "MISSING")
            rxcui = ing.get("rxcui", "MISSING")
            print(f"  {vitamin}: CUI={cui}, RXCUI={rxcui}")

if __name__ == "__main__":
    add_main_cui_codes()