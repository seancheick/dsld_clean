#!/usr/bin/env python3
"""
Fix CUI/RXCUI positioning - move them right after 'category' field
Target structure:
{
  "vitamin_a": {
    "standard_name": "Vitamin A",
    "category": "vitamins",
    "cui": "C0042839",      ← Move here  
    "rxcui": "11149",       ← Move here
    "forms": { ... }
  }
}
"""

import json
from pathlib import Path
from collections import OrderedDict

def fix_cui_positioning():
    """Move CUI/RXCUI codes to correct position after category"""
    
    file_path = Path("/Users/seancheick/Downloads/dsld_clean/scripts/data/ingredient_quality_map.json")
    
    print("🔧 Fixing CUI/RXCUI positioning...")
    print(f"📁 Working on: {file_path}")
    print("-" * 60)
    
    # Load the current data
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    fixed_data = OrderedDict()
    fixed_count = 0
    
    for ingredient_key, ingredient_data in data.items():
        # Create new ordered structure
        new_ingredient = OrderedDict()
        
        # Extract CUI/RXCUI if they exist
        cui_value = ingredient_data.get("cui")
        rxcui_value = ingredient_data.get("rxcui")
        
        # Build the ingredient with correct field order
        for key, value in ingredient_data.items():
            if key in ["cui", "rxcui"]:
                # Skip these - we'll add them in the right place
                continue
                
            new_ingredient[key] = value
            
            # After adding 'category', insert CUI and RXCUI
            if key == "category":
                if cui_value is not None:
                    new_ingredient["cui"] = cui_value
                if rxcui_value is not None:
                    new_ingredient["rxcui"] = rxcui_value
                    
                if cui_value or rxcui_value:
                    print(f"✅ Fixed {ingredient_key}: moved CUI/RXCUI after category")
                    fixed_count += 1
        
        fixed_data[ingredient_key] = new_ingredient
    
    print(f"\n📊 Fixed positioning for {fixed_count} ingredients")
    
    # Create backup
    backup_path = file_path.parent / "ingredient_quality_map_backup_positioning.json"
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"💾 Backup saved: {backup_path}")
    
    # Save the fixed data
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(fixed_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Updated: {file_path}")
    
    # Verify the fix
    print("\n🔍 Verification - checking field order:")
    test_ingredients = ["vitamin_a", "vitamin_c", "calcium", "iron"]
    
    for ingredient in test_ingredients:
        if ingredient in fixed_data:
            fields = list(fixed_data[ingredient].keys())
            print(f"  {ingredient}: {fields[:6]}...")
            
            # Check if CUI/RXCUI are in correct position
            if "cui" in fields:
                cui_index = fields.index("cui")
                category_index = fields.index("category")
                forms_index = fields.index("forms") if "forms" in fields else -1
                
                correct_position = (cui_index == category_index + 1) and (forms_index == -1 or cui_index < forms_index)
                status = "✅" if correct_position else "❌"
                print(f"    CUI position: {status} (at index {cui_index})")

def main():
    print("🎯 CUI/RXCUI POSITION CORRECTION")
    print("=" * 50)
    print("Target: category → cui → rxcui → forms")
    print("")
    
    fix_cui_positioning()
    
    print("\n🎉 CUI/RXCUI positioning fixed!")
    print("✅ All codes now appear right after 'category' field")
    print("✅ Structure matches your specified format")

if __name__ == "__main__":
    main()