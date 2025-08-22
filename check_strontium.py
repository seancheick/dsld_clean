#!/usr/bin/env python3
"""
Check strontium specifically
"""

import json

def check_strontium(file_path: str):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if 'strontium' in data:
        strontium = data['strontium']
        print(f"Strontium entry found:")
        print(f"Category: {strontium.get('category', 'N/A')}")
        print(f"Has forms: {'forms' in strontium}")
        print(f"Has dosage_importance: {'dosage_importance' in strontium}")
        
        if 'dosage_importance' in strontium:
            print(f"Dosage importance: {strontium['dosage_importance']}")
        else:
            print("MISSING dosage_importance field!")
    else:
        print("Strontium not found in data")

if __name__ == "__main__":
    file_path = "/Users/seancheick/Downloads/dsld_clean/scripts/data/ingredient_quality_map.json"
    check_strontium(file_path)