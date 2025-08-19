#!/usr/bin/env python3
"""
Script to reorganize ingredients by risk level:
- Move "risk_level": "none" from harmful_additives.json to passive_inactive_ingredients.json
- Keep only low/moderate/high risk levels in harmful_additives.json
"""

import json
from pathlib import Path
from datetime import datetime

def reorganize_ingredients():
    # File paths
    data_dir = Path("scripts/data")
    harmful_file = data_dir / "harmful_additives.json"
    passive_file = data_dir / "passive_inactive_ingredients.json"
    
    # Load current data
    with open(harmful_file, 'r') as f:
        harmful_data = json.load(f)
    
    with open(passive_file, 'r') as f:
        passive_data = json.load(f)
    
    # Find ingredients with "none" risk level
    none_risk_ingredients = []
    remaining_harmful = []
    
    for ingredient in harmful_data["harmful_additives"]:
        if ingredient.get("risk_level") == "none":
            none_risk_ingredients.append(ingredient)
            print(f"Moving to passive: {ingredient['standard_name']}")
        else:
            remaining_harmful.append(ingredient)
    
    print(f"\nFound {len(none_risk_ingredients)} ingredients with 'none' risk level to move")
    print(f"Remaining harmful ingredients: {len(remaining_harmful)}")
    
    # Convert harmful ingredients to passive format
    for ingredient in none_risk_ingredients:
        # Create passive ingredient entry
        passive_entry = {
            "id": ingredient["id"].replace("ADD_", "PII_"),
            "standard_name": ingredient["standard_name"],
            "aliases": ingredient.get("aliases", []),
            "category": ingredient.get("category", "general"),
            "notes": ingredient.get("notes", "Moved from harmful additives - risk level none"),
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        }
        
        # Add to passive ingredients
        passive_data["passive_inactive_ingredients"].append(passive_entry)
    
    # Update harmful additives (remove none risk level)
    harmful_data["harmful_additives"] = remaining_harmful
    
    # Save updated files
    with open(harmful_file, 'w') as f:
        json.dump(harmful_data, f, indent=2)
    
    with open(passive_file, 'w') as f:
        json.dump(passive_data, f, indent=2)
    
    print(f"\nReorganization complete!")
    print(f"Moved {len(none_risk_ingredients)} ingredients to passive list")
    print(f"Harmful additives now contains {len(remaining_harmful)} ingredients")
    print(f"Passive ingredients now contains {len(passive_data['passive_inactive_ingredients'])} ingredients")

if __name__ == "__main__":
    reorganize_ingredients()