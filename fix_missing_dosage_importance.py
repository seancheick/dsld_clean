#!/usr/bin/env python3
"""
Script to add dosage_importance field to standalone ingredients and standardization markers
"""

import json
import re
from typing import Dict, Any

def get_dosage_importance_standalone(ingredient_name: str, category: str, standard_name: str = "") -> float:
    """
    Determine dosage importance for standalone ingredients (no forms structure)
    """
    
    ingredient_lower = ingredient_name.lower()
    category_lower = category.lower()
    standard_name_lower = standard_name.lower()
    
    # Standardization markers - these are quality control compounds, not therapeutic
    # They should have minimal dosage importance since they're used for standardization, not bioactivity
    if category_lower == "standardization_marker":
        return 0.1  # Very low importance as they're just quality markers
    
    # Primary importance (1.5) - Essential vitamins and major minerals
    primary_keywords = [
        'vitamin_a', 'vitamin_d', 'vitamin_c', 'vitamin_e', 'vitamin_k',
        'thiamine', 'riboflavin', 'niacin', 'pantothenic', 'biotin', 
        'vitamin_b6', 'folate', 'vitamin_b12', 'cobalamin',
        'calcium', 'magnesium', 'iron', 'zinc', 'potassium', 'phosphorus',
        'sodium', 'chloride', 'iodine'
    ]
    
    # Trace importance (0.5) - Minor minerals and specialized compounds
    trace_keywords = [
        'selenium', 'manganese', 'chromium', 'molybdenum', 'copper',
        'fluoride', 'cobalt', 'vanadium', 'nickel', 'tin', 'silicon',
        'boron', 'lithium', 'rubidium', 'strontium', 'creatine'
    ]
    
    # Check for primary importance
    for keyword in primary_keywords:
        if keyword in ingredient_lower or keyword in standard_name_lower:
            return 1.5
    
    # Check for trace importance
    for keyword in trace_keywords:
        if keyword in ingredient_lower or keyword in standard_name_lower:
            return 0.5
    
    # Category-based classification
    if category_lower in ['vitamins', 'minerals']:
        return 1.5
    elif category_lower in ['coenzyme', 'antioxidant']:
        return 1.0
    elif category_lower in ['amino_acid', 'botanical', 'fatty_acid']:
        return 1.0
    
    # Default for unknown categories
    return 1.0

def fix_missing_dosage_importance(file_path: str):
    """Fix missing dosage_importance fields in standalone ingredients"""
    
    print(f"Loading {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total_checked = 0
    updated_standalone = 0
    updated_forms = 0
    
    for ingredient_name, ingredient_data in data.items():
        total_checked += 1
        
        # Handle ingredients with forms structure
        if 'forms' in ingredient_data:
            category = ingredient_data.get('category', '')
            standard_name = ingredient_data.get('standard_name', '')
            
            for form_name, form_data in ingredient_data['forms'].items():
                if 'dosage_importance' not in form_data:
                    dosage_importance = get_dosage_importance_standalone(ingredient_name, category, standard_name)
                    form_data['dosage_importance'] = dosage_importance
                    updated_forms += 1
                    print(f"Added dosage_importance={dosage_importance} to {ingredient_name} -> {form_name}")
        
        # Handle standalone ingredients (no forms structure)
        else:
            if 'dosage_importance' not in ingredient_data:
                category = ingredient_data.get('category', '')
                standard_name = ingredient_data.get('standard_name', '')
                
                dosage_importance = get_dosage_importance_standalone(ingredient_name, category, standard_name)
                ingredient_data['dosage_importance'] = dosage_importance
                updated_standalone += 1
                
                print(f"Added dosage_importance={dosage_importance} to standalone ingredient: {ingredient_name} (category: {category})")
    
    print(f"\nProcessed {total_checked} ingredients")
    print(f"Updated {updated_standalone} standalone ingredients") 
    print(f"Updated {updated_forms} forms")
    
    # Save the updated data
    print(f"Saving updated data to {file_path}...")
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("Successfully fixed all missing dosage_importance fields!")

if __name__ == "__main__":
    file_path = "/Users/seancheick/Downloads/dsld_clean/scripts/data/ingredient_quality_map.json"
    fix_missing_dosage_importance(file_path)