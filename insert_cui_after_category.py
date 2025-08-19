#!/usr/bin/env python3
"""
Insert CUI and RXCUI codes right after the 'category' field for main ingredients
"""

import json
from pathlib import Path
from collections import OrderedDict

def insert_cui_after_category():
    """Insert CUI/RXCUI codes in the correct position"""
    
    file_path = Path("scripts/data/ingredient_quality_map.json")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Main vitamins and minerals with their CUI/RXCUI codes
    main_codes = {
        "vitamin_a": {"cui": "C0042839", "rxcui": "11149"},
        "vitamin_b1_thiamine": {"cui": "C0039840", "rxcui": "10405"},
        "vitamin_b2_riboflavin": {"cui": "C0035527", "rxcui": "9220"},
        "vitamin_b3_niacin": {"cui": "C0027996", "rxcui": "7454"},
        "vitamin_b5_pantothenic": {"cui": "C0030342", "rxcui": "7896"},
        "vitamin_b6_pyridoxine": {"cui": "C0034274", "rxcui": "8696"},
        "vitamin_b7_biotin": {"cui": "C0005575", "rxcui": "1116"},
        "vitamin_b9_folate": {"cui": "C0016448", "rxcui": "4492"},
        "vitamin_b12_cobalamin": {"cui": "C0042845", "rxcui": "11256"},
        "vitamin_c": {"cui": "C0003968", "rxcui": "1151"},
        "vitamin_d": {"cui": "C0042866", "rxcui": "11148"},
        "vitamin_e": {"cui": "C0042874", "rxcui": "11256"},
        "vitamin_k": {"cui": "C0042878", "rxcui": "11256"},
        "calcium": {"cui": "C0006675", "rxcui": "1898"},
        "phosphorus": {"cui": "C0031705", "rxcui": "8134"},
        "magnesium": {"cui": "C0024467", "rxcui": "6917"},
        "iron": {"cui": "C0021776", "rxcui": "none"},
        "zinc": {"cui": "C0043539", "rxcui": "2078"},
        "selenium": {"cui": "C0036581", "rxcui": "9786"},
        "copper": {"cui": "C0009968", "rxcui": "3008"},
        "chromium": {"cui": "C0008574", "rxcui": "2599"},
        "manganese": {"cui": "C0024706", "rxcui": "6951"},
        "molybdenum": {"cui": "C0026982", "rxcui": "7455"},
        "boron": {"cui": "C0006029", "rxcui": "1374"},
        "potassium": {"cui": "C0032821", "rxcui": "8588"},
        "choline": {"cui": "C0008405", "rxcui": "2650"},
        "inositol": {"cui": "C0021547", "rxcui": "6038"},
        "alpha_lipoic_acid": {"cui": "C0023791", "rxcui": "6809"},
        "glutathione": {"cui": "C0017817", "rxcui": "4411"},
        "omega_3": {"cui": "C0015689", "rxcui": "none"},
        "coq10": {"cui": "C0056077", "rxcui": "2623"},
        "turmeric": {"cui": "C0209960", "rxcui": "11178"},
        "probiotics": {"cui": "C0525033", "rxcui": "none"},
        "spirulina": {"cui": "C0246293", "rxcui": "none"},
        "nmn": {"cui": "C0068719", "rxcui": "none"}
    }
    
    updated_data = OrderedDict()
    added_count = 0
    
    print("🔧 Inserting CUI/RXCUI codes after 'category' field...")
    print("-" * 60)
    
    for ingredient_key, ingredient_data in data.items():
        # Create ordered dict for proper field order
        new_ingredient = OrderedDict()
        
        # Copy fields in the correct order
        for key, value in ingredient_data.items():
            new_ingredient[key] = value
            
            # After adding 'category', insert cui and rxcui if this ingredient needs them
            if key == "category" and ingredient_key in main_codes:
                codes = main_codes[ingredient_key]
                
                # Only add if not already present
                if "cui" not in ingredient_data:
                    new_ingredient["cui"] = codes["cui"]
                    print(f"✅ Added CUI {codes['cui']} to {ingredient_key}")
                    added_count += 1
                
                if "rxcui" not in ingredient_data:
                    new_ingredient["rxcui"] = codes["rxcui"]
                    print(f"✅ Added RXCUI {codes['rxcui']} to {ingredient_key}")
        
        updated_data[ingredient_key] = new_ingredient
    
    print(f"\n📊 Added CUI/RXCUI codes to {added_count} ingredients")
    
    # Save the properly ordered data
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(updated_data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Updated: {file_path}")
    
    # Verify the structure
    print("\n🔍 Verification - checking field order for key vitamins:")
    key_vitamins = ["vitamin_a", "vitamin_c", "vitamin_d"]
    
    for vitamin in key_vitamins:
        if vitamin in updated_data:
            ing = updated_data[vitamin]
            fields = list(ing.keys())
            print(f"  {vitamin}: {fields[:6]}...")  # Show first 6 fields

if __name__ == "__main__":
    insert_cui_after_category()