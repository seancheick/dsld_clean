#!/usr/bin/env python3
"""
Specifically fix strontium and any other standalone ingredients missing dosage_importance
"""

import json

def fix_remaining_ingredients(file_path: str):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    updated = 0
    
    for ingredient_name, ingredient_data in data.items():
        # Skip if it has forms (those should already be handled)
        if 'forms' in ingredient_data:
            continue
            
        # Check if it's missing dosage_importance
        if 'dosage_importance' not in ingredient_data:
            category = ingredient_data.get('category', '').lower()
            
            # Assign dosage importance based on category and name
            if 'strontium' in ingredient_name.lower():
                dosage_importance = 0.5  # Trace mineral
            elif category == 'minerals':
                if any(keyword in ingredient_name.lower() for keyword in ['calcium', 'magnesium', 'iron', 'zinc', 'potassium']):
                    dosage_importance = 1.5
                else:
                    dosage_importance = 0.5  # Other minerals
            elif category == 'vitamins':
                dosage_importance = 1.5
            elif category == 'standardization_marker':
                dosage_importance = 0.1
            else:
                dosage_importance = 1.0
            
            ingredient_data['dosage_importance'] = dosage_importance
            updated += 1
            print(f"Added dosage_importance={dosage_importance} to {ingredient_name} (category: {category})")
    
    print(f"Updated {updated} remaining ingredients")
    
    # Save the updated data
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("Successfully fixed remaining ingredients!")

if __name__ == "__main__":
    file_path = "/Users/seancheick/Downloads/dsld_clean/scripts/data/ingredient_quality_map.json"
    fix_remaining_ingredients(file_path)