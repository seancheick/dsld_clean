#!/usr/bin/env python3
"""
Script to add dosage_importance field to all forms in ingredient_quality_map.json
"""

import json
import re
from typing import Dict, Any

def get_dosage_importance(ingredient_name: str, form_name: str, category: str) -> float:
    """
    Determine dosage importance based on ingredient name, form, and category.
    
    Returns:
    - 1.5 (Primary): Essential vitamins/minerals 
    - 1.0 (Secondary): Botanicals, fatty acids, antioxidants
    - 0.5 (Trace): Minor minerals, specialized compounds
    """
    
    ingredient_lower = ingredient_name.lower()
    form_lower = form_name.lower()
    category_lower = category.lower()
    
    # Primary importance (1.5) - Essential vitamins and major minerals
    primary_keywords = [
        # Essential vitamins
        'vitamin_a', 'vitamin_d', 'vitamin_c', 'vitamin_e', 'vitamin_k',
        'thiamine', 'riboflavin', 'niacin', 'pantothenic', 'biotin', 
        'vitamin_b6', 'folate', 'vitamin_b12', 'cobalamin',
        # Major minerals
        'calcium', 'magnesium', 'iron', 'zinc', 'potassium', 'phosphorus',
        'sodium', 'chloride', 'iodine'
    ]
    
    # Trace importance (0.5) - Minor minerals and specialized compounds
    trace_keywords = [
        'selenium', 'manganese', 'chromium', 'molybdenum', 'copper',
        'fluoride', 'cobalt', 'vanadium', 'nickel', 'tin', 'silicon',
        'boron', 'lithium', 'rubidium', 'strontium'
    ]
    
    # Check for primary importance
    for keyword in primary_keywords:
        if keyword in ingredient_lower:
            return 1.5
    
    # Check for trace importance
    for keyword in trace_keywords:
        if keyword in ingredient_lower:
            return 0.5
    
    # Category-based classification
    if category_lower in ['vitamins', 'minerals']:
        # If it's a vitamin or mineral but not in our lists, it's likely primary
        return 1.5
    
    # Secondary importance (1.0) - Default for botanicals, antioxidants, etc.
    return 1.0

def add_dosage_importance_to_file(file_path: str):
    """Add dosage_importance field to all forms in the ingredient quality map."""
    
    print(f"Loading {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total_forms = 0
    updated_forms = 0
    
    for ingredient_name, ingredient_data in data.items():
        if 'forms' in ingredient_data:
            category = ingredient_data.get('category', '')
            
            for form_name, form_data in ingredient_data['forms'].items():
                total_forms += 1
                
                # Only add if not already present
                if 'dosage_importance' not in form_data:
                    dosage_importance = get_dosage_importance(ingredient_name, form_name, category)
                    form_data['dosage_importance'] = dosage_importance
                    updated_forms += 1
                    print(f"Added dosage_importance={dosage_importance} to {ingredient_name} -> {form_name}")
    
    print(f"\nProcessed {total_forms} forms, updated {updated_forms} forms")
    
    # Save the updated data
    print(f"Saving updated data to {file_path}...")
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("Successfully added dosage_importance to all forms!")

if __name__ == "__main__":
    file_path = "/Users/seancheick/Downloads/dsld_clean/scripts/data/ingredient_quality_map.json"
    add_dosage_importance_to_file(file_path)