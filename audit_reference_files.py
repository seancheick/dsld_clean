#!/usr/bin/env python3
"""
Reference Files Audit Script
Checks all reference JSON files and verifies they're being used properly in ingredient mapping
"""

import sys
import json
from pathlib import Path
from collections import Counter

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent / "scripts"))

from enhanced_normalizer import EnhancedDSLDNormalizer
from constants import *

def audit_reference_files():
    """Audit all reference files and their usage"""
    print("=== DSLD Reference Files Audit ===\n")
    
    # Define all reference files that should be checked
    reference_files = {
        "ingredient_quality_map.json": INGREDIENT_QUALITY_MAP,
        "harmful_additives.json": HARMFUL_ADDITIVES,
        "allergens.json": ALLERGENS,
        "top_manufacturers_data.json": TOP_MANUFACTURERS,
        "proprietary_blends_penalty.json": PROPRIETARY_BLENDS,
        "standardized_botanicals.json": STANDARDIZED_BOTANICALS,
        "banned_recalled_ingredients.json": BANNED_RECALLED,
        "passive_inactive_ingredients.json": PASSIVE_INACTIVE_INGREDIENTS,
        "botanical_ingredients.json": BOTANICAL_INGREDIENTS,
        # Additional files that might contain ingredient data
        "absorption_enhancers.json": ABSORPTION_ENHANCERS,
        "backed_clinical_studies.json": CLINICAL_STUDIES,
        "enhanced_delivery.json": ENHANCED_DELIVERY,
        "synergy_cluster.json": SYNERGY_CLUSTER,
        "rda_optimal_uls.json": RDA_OPTIMAL_ULS,
        "ingredient_weights.json": INGREDIENT_WEIGHTS,
        "unit_mappings.json": UNIT_MAPPINGS,
    }
    
    print("📁 Reference Files Status:")
    print("-" * 60)
    
    loaded_files = []
    missing_files = []
    
    for name, path in reference_files.items():
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Count entries
                if isinstance(data, dict):
                    if name == "ingredient_quality_map.json":
                        count = len(data)
                    elif "ingredients" in data:
                        count = len(data["ingredients"])
                    elif any(key.endswith("_ingredients") for key in data.keys()):
                        # Find the main ingredients key
                        ingredients_key = next(key for key in data.keys() if key.endswith("_ingredients"))
                        count = len(data[ingredients_key])
                    elif any(key.endswith("_additives") for key in data.keys()):
                        additives_key = next(key for key in data.keys() if key.endswith("_additives"))
                        count = len(data[additives_key])
                    elif "common_allergens" in data:
                        count = len(data["common_allergens"])
                    else:
                        count = len(data)
                elif isinstance(data, list):
                    count = len(data)
                else:
                    count = 1
                
                print(f"✅ {name:<35} {count:>6} entries")
                loaded_files.append((name, path, count))
                
            except Exception as e:
                print(f"❌ {name:<35} ERROR: {e}")
                missing_files.append((name, f"Load error: {e}"))
        else:
            print(f"❌ {name:<35} MISSING")
            missing_files.append((name, "File not found"))
    
    print(f"\n📊 Summary: {len(loaded_files)} loaded, {len(missing_files)} missing/error")
    
    return loaded_files, missing_files

def check_normalizer_usage():
    """Check which files are actually being used by the normalizer"""
    print("\n🔍 Normalizer Usage Analysis:")
    print("-" * 60)
    
    try:
        normalizer = EnhancedDSLDNormalizer()
        
        # Check loaded databases
        databases = {
            "ingredient_map": normalizer.ingredient_map,
            "harmful_additives": normalizer.harmful_additives,
            "allergens_db": normalizer.allergens_db,
            "manufacturers_db": normalizer.manufacturers_db,
            "proprietary_blends": normalizer.proprietary_blends,
            "standardized_botanicals": normalizer.standardized_botanicals,
            "banned_recalled": normalizer.banned_recalled,
            "passive_inactive_ingredients": normalizer.passive_inactive_ingredients,
            "botanical_ingredients": normalizer.botanical_ingredients,
            "absorption_enhancers": normalizer.absorption_enhancers,
            "clinical_studies": normalizer.clinical_studies,
            "enhanced_delivery": normalizer.enhanced_delivery,
        }
        
        print("Loaded databases in normalizer:")
        for name, db in databases.items():
            if db:
                if isinstance(db, dict):
                    if name == "ingredient_map":
                        count = len(db)
                    elif any(key.endswith("_ingredients") for key in db.keys()):
                        ingredients_key = next(key for key in db.keys() if key.endswith("_ingredients"))
                        count = len(db[ingredients_key])
                    elif any(key.endswith("_additives") for key in db.keys()):
                        additives_key = next(key for key in db.keys() if key.endswith("_additives"))
                        count = len(db[additives_key])
                    elif "common_allergens" in db:
                        count = len(db["common_allergens"])
                    else:
                        count = len(db)
                else:
                    count = len(db) if hasattr(db, '__len__') else 1
                print(f"✅ {name:<30} {count:>6} entries")
            else:
                print(f"❌ {name:<30} EMPTY/NULL")
        
        # Check lookup indices
        print(f"\n🔍 Lookup Indices:")
        print(f"✅ ingredient_alias_lookup     {len(normalizer.ingredient_alias_lookup):>6} entries")
        print(f"✅ ingredient_forms_lookup     {len(normalizer.ingredient_forms_lookup):>6} entries")
        print(f"✅ harmful_lookup              {len(normalizer.harmful_lookup):>6} entries")
        print(f"✅ allergen_lookup             {len(normalizer.allergen_lookup):>6} entries")
        print(f"✅ fast_exact_lookup           {len(normalizer._fast_exact_lookup):>6} entries")
        
        return normalizer
        
    except Exception as e:
        print(f"❌ Error initializing normalizer: {e}")
        return None

def test_ingredient_coverage(normalizer):
    """Test coverage of common ingredients"""
    print("\n🧪 Ingredient Coverage Test:")
    print("-" * 60)
    
    # Test common ingredients that should be mapped
    test_ingredients = [
        # Vitamins
        "Vitamin C", "Ascorbic Acid", "Vitamin D3", "Cholecalciferol",
        "Vitamin B12", "Cyanocobalamin", "Folic Acid", "Folate",
        "Vitamin E", "Alpha-Tocopherol", "Biotin", "Thiamine",
        
        # Minerals
        "Calcium", "Calcium Carbonate", "Magnesium", "Magnesium Oxide",
        "Iron", "Ferrous Sulfate", "Zinc", "Zinc Gluconate",
        "Potassium", "Selenium", "Chromium", "Molybdenum",
        
        # Harmful additives
        "Sorbitol", "Aspartame", "Sucralose", "Titanium Dioxide",
        "Red Dye 40", "Yellow 6", "BHT", "BHA",
        
        # Allergens
        "Milk", "Soy", "Wheat", "Eggs", "Fish", "Shellfish",
        "Tree Nuts", "Peanuts", "Sesame",
        
        # Botanicals
        "Turmeric", "Ginkgo Biloba", "Echinacea", "Ginseng",
        "Green Tea Extract", "Garlic", "Saw Palmetto",
        
        # Common inactive ingredients
        "Microcrystalline Cellulose", "Magnesium Stearate", "Silicon Dioxide",
        "Gelatin", "Hypromellose", "Stearic Acid", "Croscarmellose Sodium"
    ]
    
    mapped_count = 0
    unmapped_ingredients = []
    
    for ingredient in test_ingredients:
        # Test fast lookup first
        fast_result = normalizer._fast_ingredient_lookup(ingredient)
        if fast_result["mapped"]:
            mapped_count += 1
            print(f"✅ {ingredient:<25} -> {fast_result['type']}")
        else:
            # Test full mapping
            standard_name, mapped, forms = normalizer._enhanced_ingredient_mapping(ingredient)
            if mapped:
                mapped_count += 1
                print(f"✅ {ingredient:<25} -> mapped")
            else:
                unmapped_ingredients.append(ingredient)
                print(f"❌ {ingredient:<25} -> UNMAPPED")
    
    print(f"\n📊 Coverage: {mapped_count}/{len(test_ingredients)} ({mapped_count/len(test_ingredients)*100:.1f}%)")
    
    if unmapped_ingredients:
        print(f"\n⚠️  Unmapped ingredients that should be reviewed:")
        for ingredient in unmapped_ingredients:
            print(f"   - {ingredient}")
    
    return unmapped_ingredients

def analyze_missing_databases(normalizer):
    """Analyze which databases might be missing from the checking process"""
    print("\n🔍 Missing Database Analysis:")
    print("-" * 60)
    
    # Files that exist but might not be checked
    all_data_files = list(Path("scripts/data").glob("*.json"))
    
    # Files currently being loaded
    loaded_files = {
        "ingredient_quality_map.json",
        "harmful_additives.json",
        "allergens.json",
        "top_manufacturers_data.json",
        "proprietary_blends_penalty.json",
        "standardized_botanicals.json",
        "banned_recalled_ingredients.json",
        "passive_inactive_ingredients.json",
        "botanical_ingredients.json",
        "absorption_enhancers.json",
        "backed_clinical_studies.json",
        "enhanced_delivery.json"
    }
    
    potentially_missing = []
    for file_path in all_data_files:
        if file_path.name not in loaded_files:
            potentially_missing.append(file_path.name)
    
    if potentially_missing:
        print("📋 Files that exist but are NOT being checked for ingredients:")
        for filename in potentially_missing:
            print(f"   - {filename}")
        
        print(f"\n💡 Recommendation: Review these files to see if they contain")
        print(f"   ingredient data that should be included in the mapping process.")
    else:
        print("✅ All data files are being loaded and checked!")

if __name__ == "__main__":
    print("DSLD Reference Files Audit")
    print("=" * 60)
    
    # Audit reference files
    loaded_files, missing_files = audit_reference_files()
    
    # Check normalizer usage
    normalizer = check_normalizer_usage()
    
    if normalizer:
        # Test ingredient coverage
        unmapped = test_ingredient_coverage(normalizer)
        
        # Analyze missing databases
        analyze_missing_databases(normalizer)
    
    print("\n" + "=" * 60)
    print("Audit complete!")
