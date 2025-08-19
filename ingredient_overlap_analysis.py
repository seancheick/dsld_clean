#!/usr/bin/env python3
"""
Ingredient Overlap Analysis Script
Finds overlapping ingredients between harmful_additives.json and passive_inactive_ingredients.json
"""

import json
import os
from collections import defaultdict

def load_json_file(filepath):
    """Load and return JSON data from file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {filepath}: {e}")
        return None

def extract_ingredient_names(data, data_key):
    """Extract all ingredient names and aliases from data"""
    ingredients = {}
    
    if data_key not in data:
        print(f"Warning: Key '{data_key}' not found in data")
        return ingredients
    
    for item in data[data_key]:
        item_id = item.get('id', 'unknown')
        standard_name = item.get('standard_name', '')
        aliases = item.get('aliases', [])
        
        # Collect all names (standard name + aliases)
        all_names = [standard_name] + aliases
        
        # Normalize names for comparison (lowercase, stripped)
        normalized_names = [name.lower().strip() for name in all_names if name]
        
        ingredients[item_id] = {
            'standard_name': standard_name,
            'all_names': all_names,
            'normalized_names': normalized_names,
            'risk_level': item.get('risk_level', 'unknown'),
            'category': item.get('category', 'unknown')
        }
    
    return ingredients

def find_overlaps(harmful_ingredients, passive_ingredients):
    """Find overlapping ingredient names between the two datasets"""
    overlaps = []
    
    # Create a mapping from normalized names to harmful ingredient IDs
    harmful_name_map = {}
    for harm_id, harm_data in harmful_ingredients.items():
        for norm_name in harm_data['normalized_names']:
            if norm_name not in harmful_name_map:
                harmful_name_map[norm_name] = []
            harmful_name_map[norm_name].append(harm_id)
    
    # Check each passive ingredient against harmful ingredients
    for passive_id, passive_data in passive_ingredients.items():
        for norm_name in passive_data['normalized_names']:
            if norm_name in harmful_name_map:
                for harm_id in harmful_name_map[norm_name]:
                    overlaps.append({
                        'ingredient_name': norm_name,
                        'harmful_id': harm_id,
                        'harmful_standard_name': harmful_ingredients[harm_id]['standard_name'],
                        'harmful_risk_level': harmful_ingredients[harm_id]['risk_level'],
                        'harmful_category': harmful_ingredients[harm_id]['category'],
                        'passive_id': passive_id,
                        'passive_standard_name': passive_data['standard_name'],
                        'passive_category': passive_data['category']
                    })
    
    return overlaps

def main():
    """Main analysis function"""
    # File paths
    base_dir = "/Users/seancheick/Downloads/dsld_clean/scripts/data"
    harmful_file = os.path.join(base_dir, "harmful_additives.json")
    passive_file = os.path.join(base_dir, "passive_inactive_ingredients.json")
    
    print("=== INGREDIENT OVERLAP ANALYSIS ===")
    print()
    
    # Load data files
    print("Loading data files...")
    harmful_data = load_json_file(harmful_file)
    passive_data = load_json_file(passive_file)
    
    if not harmful_data or not passive_data:
        print("Failed to load required data files.")
        return
    
    # Extract ingredient information
    print("Extracting ingredient names and aliases...")
    harmful_ingredients = extract_ingredient_names(harmful_data, "harmful_additives")
    passive_ingredients = extract_ingredient_names(passive_data, "passive_inactive_ingredients")
    
    print(f"Found {len(harmful_ingredients)} harmful additives")
    print(f"Found {len(passive_ingredients)} passive/inactive ingredients")
    print()
    
    # Find overlaps
    print("Analyzing overlaps...")
    overlaps = find_overlaps(harmful_ingredients, passive_ingredients)
    
    if not overlaps:
        print("✅ No overlapping ingredients found!")
        return
    
    print(f"🚨 Found {len(overlaps)} overlapping ingredient(s):")
    print()
    
    # Group overlaps by ingredient name for cleaner output
    grouped_overlaps = defaultdict(list)
    for overlap in overlaps:
        grouped_overlaps[overlap['ingredient_name']].append(overlap)
    
    # Display results
    for ingredient_name, overlap_list in grouped_overlaps.items():
        print(f"🔍 CONFLICT: '{ingredient_name}'")
        print("-" * 50)
        
        for overlap in overlap_list:
            print(f"  📋 HARMFUL LIST:")
            print(f"     Standard Name: {overlap['harmful_standard_name']}")
            print(f"     Risk Level: {overlap['harmful_risk_level']}")
            print(f"     Category: {overlap['harmful_category']}")
            print(f"     ID: {overlap['harmful_id']}")
            print()
            
            print(f"  ✅ PASSIVE LIST:")
            print(f"     Standard Name: {overlap['passive_standard_name']}")
            print(f"     Category: {overlap['passive_category']}")
            print(f"     ID: {overlap['passive_id']}")
            print()
        
        print("=" * 60)
        print()
    
    # Recommendations
    print("📝 RECOMMENDATIONS:")
    print()
    
    for ingredient_name, overlap_list in grouped_overlaps.items():
        overlap = overlap_list[0]  # Take first overlap for recommendation
        
        print(f"For '{ingredient_name}':")
        
        if overlap['harmful_risk_level'] in ['high', 'moderate']:
            print(f"  ❌ REMOVE from passive list - Risk level: {overlap['harmful_risk_level']}")
            print(f"     Keep in harmful additives list with current classification")
        elif overlap['harmful_risk_level'] == 'low':
            print(f"  ⚠️  REVIEW needed - Low risk but context matters")
            print(f"     Consider: Is this ingredient used passively or as an active component?")
        else:
            print(f"  ✅ MOVE to passive list - Risk level: {overlap['harmful_risk_level']}")
            print(f"     Remove from harmful additives list")
        
        print()

if __name__ == "__main__":
    main()