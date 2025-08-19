#!/usr/bin/env python3
"""
Clean up additive architecture:
- Remove additive items from passive_inactive_ingredients.json that are now in non_harmful_additives.json
- Keep only true passive ingredients (excipients, carriers, etc.)
"""

import json
from pathlib import Path

def clean_additive_architecture():
    data_dir = Path("scripts/data")
    passive_file = data_dir / "passive_inactive_ingredients.json"
    non_harmful_file = data_dir / "non_harmful_additives.json"
    
    # Load data
    with open(passive_file, 'r') as f:
        passive_data = json.load(f)
    
    with open(non_harmful_file, 'r') as f:
        non_harmful_data = json.load(f)
    
    # Get list of standard names from non_harmful_additives
    non_harmful_names = {item["standard_name"].lower() for item in non_harmful_data["non_harmful_additives"]}
    
    # Also get aliases for matching
    non_harmful_aliases = set()
    for item in non_harmful_data["non_harmful_additives"]:
        for alias in item.get("aliases", []):
            non_harmful_aliases.add(alias.lower())
    
    # Items to remove from passive (they're now additive items)
    additive_ids_to_remove = [
        "PII_STEVIA", "PII_MONK_FRUIT", "PII_VEGETABLE_GLYCERIN", 
        "PII_CITRIC_ACID", "PII_NATURAL_PRESERVATIVES", "PII_NATURAL_GUMS",
        "PII_AGAR", "PII_FRUIT_VEG_POWDERS", "PII_VANILLIN", 
        "PII_SODIUM_BICARBONATE", "PII_SODIUM_CARBONATE", "PII_NATURAL_FLAVORS"
    ]
    
    # Filter out additive items from passive list
    original_count = len(passive_data["passive_inactive_ingredients"])
    filtered_passive = []
    removed_items = []
    
    for item in passive_data["passive_inactive_ingredients"]:
        item_id = item.get("id", "")
        item_name = item.get("standard_name", "").lower()
        
        # Check if this item should be removed (is now an additive)
        should_remove = (
            item_id in additive_ids_to_remove or
            item_name in non_harmful_names or
            any(alias.lower() in non_harmful_aliases for alias in item.get("aliases", []))
        )
        
        if should_remove:
            removed_items.append(item["standard_name"])
            print(f"Removing additive from passive: {item['standard_name']}")
        else:
            filtered_passive.append(item)
    
    # Update passive data
    passive_data["passive_inactive_ingredients"] = filtered_passive
    
    # Save updated passive file
    with open(passive_file, 'w') as f:
        json.dump(passive_data, f, indent=2)
    
    print(f"\n✅ Architecture cleanup complete!")
    print(f"Original passive ingredients: {original_count}")
    print(f"Removed additives: {len(removed_items)}")
    print(f"Remaining true passive ingredients: {len(filtered_passive)}")
    print(f"Non-harmful additives: {len(non_harmful_data['non_harmful_additives'])}")
    
    print(f"\nRemoved items: {removed_items}")

if __name__ == "__main__":
    clean_additive_architecture()