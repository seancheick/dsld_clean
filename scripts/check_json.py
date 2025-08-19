#!/usr/bin/env python3
import json
import sys

def find_json_error(filename):
    with open(filename, 'r') as f:
        content = f.read()
    
    # Try to parse the entire file
    try:
        data = json.loads(content)
        print(f"✅ JSON is valid! Found {len(data)} top-level entries")
        
        # Check if our target ingredients are there
        targets = ['alpha_lipoic_acid', 'molybdenum', 'choline']
        for target in targets:
            if target in data:
                print(f"✅ Found: {target}")
            else:
                print(f"❌ Missing: {target}")
                
    except json.JSONDecodeError as e:
        print(f"❌ JSON Error: {e}")
        print(f"Error at line {e.lineno}, column {e.colno}")
        
        # Show context around the error
        lines = content.split('\n')
        error_line = e.lineno - 1
        
        print("\nContext around error:")
        for i in range(max(0, error_line - 5), min(len(lines), error_line + 5)):
            marker = ">>>" if i == error_line else "   "
            print(f"{marker} {i+1:5d}: {lines[i][:80]}")

if __name__ == "__main__":
    find_json_error("data/ingredient_quality_map.json")