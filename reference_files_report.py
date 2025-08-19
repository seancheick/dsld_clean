#!/usr/bin/env python3
"""
DSLD Reference Files Analysis and Best Practices Report
"""

import sys
import json
from pathlib import Path
from collections import Counter

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent / "scripts"))

from enhanced_normalizer import EnhancedDSLDNormalizer

def analyze_reference_files():
    """Analyze all reference files used in the cleaning phase"""
    print("=" * 80)
    print("DSLD REFERENCE FILES ANALYSIS & BEST PRACTICES REPORT")
    print("=" * 80)
    
    print("\n📋 REFERENCE FILES USED IN CLEANING PHASE:")
    print("-" * 60)
    
    # Core mapping databases (used in cleaning)
    cleaning_databases = {
        "ingredient_quality_map.json": {
            "purpose": "Core vitamin/mineral/supplement mapping",
            "structure": "ingredient_name -> {standard_name, forms, aliases}",
            "used_for": "Primary ingredient standardization"
        },
        "harmful_additives.json": {
            "purpose": "Harmful additive identification",
            "structure": "harmful_additives -> [{standard_name, aliases, category, risk_level}]",
            "used_for": "Flagging harmful ingredients"
        },
        "allergens.json": {
            "purpose": "Common allergen identification",
            "structure": "common_allergens -> [{standard_name, aliases, severity_level}]",
            "used_for": "Allergen detection and warnings"
        },
        "proprietary_blends_penalty.json": {
            "purpose": "Proprietary blend detection",
            "structure": "proprietary_blend_concerns -> [{standard_name, red_flag_terms}]",
            "used_for": "Quality scoring penalties"
        },
        "standardized_botanicals.json": {
            "purpose": "Standardized botanical extracts",
            "structure": "standardized_botanicals -> [{standard_name, aliases}]",
            "used_for": "High-quality botanical identification"
        },
        "banned_recalled_ingredients.json": {
            "purpose": "Banned/recalled ingredients",
            "structure": "banned_ingredients -> [{standard_name, aliases, reason}]",
            "used_for": "Safety flagging"
        },
        "passive_inactive_ingredients.json": {
            "purpose": "Common inactive ingredients",
            "structure": "passive_inactive_ingredients -> [{standard_name, aliases}]",
            "used_for": "Inactive ingredient identification"
        },
        "botanical_ingredients.json": {
            "purpose": "General botanical ingredients",
            "structure": "botanical_ingredients -> [{standard_name, aliases}]",
            "used_for": "Botanical ingredient mapping"
        },
        "top_manufacturers_data.json": {
            "purpose": "Manufacturer information",
            "structure": "manufacturers -> [{name, aliases, quality_score}]",
            "used_for": "Manufacturer standardization"
        }
    }
    
    for filename, info in cleaning_databases.items():
        print(f"✅ {filename:<35}")
        print(f"   Purpose: {info['purpose']}")
        print(f"   Used for: {info['used_for']}")
        print()
    
    print("\n📋 FILES NOT USED IN CLEANING (Reserved for Enrichment/Scoring):")
    print("-" * 60)
    
    # Enrichment/scoring databases (NOT used in cleaning)
    enrichment_databases = {
        "absorption_enhancers.json": "Absorption enhancement scoring",
        "backed_clinical_studies.json": "Clinical evidence scoring", 
        "enhanced_delivery.json": "Delivery system scoring",
        "synergy_cluster.json": "Ingredient synergy analysis",
        "rda_optimal_uls.json": "RDA/UL reference values",
        "ingredient_weights.json": "Ingredient importance weighting",
        "unit_mappings.json": "Unit conversion tables"
    }
    
    for filename, purpose in enrichment_databases.items():
        print(f"⏳ {filename:<35} -> {purpose}")
    
    return cleaning_databases, enrichment_databases

def test_ingredient_coverage():
    """Test coverage with comprehensive ingredient list"""
    print("\n🧪 COMPREHENSIVE INGREDIENT COVERAGE TEST:")
    print("-" * 60)
    
    normalizer = EnhancedDSLDNormalizer()
    
    # Comprehensive test ingredients
    test_categories = {
        "Vitamins": [
            "Vitamin A", "Beta-Carotene", "Retinol", "Vitamin C", "Ascorbic Acid",
            "Vitamin D", "Vitamin D3", "Cholecalciferol", "Vitamin E", "Alpha-Tocopherol",
            "Vitamin K", "Vitamin K2", "Menaquinone", "Thiamine", "Riboflavin",
            "Niacin", "Pantothenic Acid", "Pyridoxine", "Biotin", "Folate", "Folic Acid",
            "Vitamin B12", "Cyanocobalamin", "Methylcobalamin"
        ],
        "Minerals": [
            "Calcium", "Calcium Carbonate", "Calcium Citrate", "Magnesium", "Magnesium Oxide",
            "Iron", "Ferrous Sulfate", "Ferrous Fumarate", "Zinc", "Zinc Gluconate",
            "Copper", "Manganese", "Chromium", "Selenium", "Iodine", "Potassium",
            "Phosphorus", "Molybdenum", "Boron", "Vanadium"
        ],
        "Harmful Additives": [
            "Aspartame", "Sucralose", "Acesulfame Potassium", "Sorbitol", "Mannitol",
            "Titanium Dioxide", "Red Dye 40", "Yellow 6", "Blue 1", "BHT", "BHA",
            "Sodium Benzoate", "Potassium Sorbate", "Carrageenan"
        ],
        "Allergens": [
            "Milk", "Casein", "Whey", "Soy", "Soy Lecithin", "Wheat", "Gluten",
            "Eggs", "Fish", "Shellfish", "Tree Nuts", "Almonds", "Peanuts", "Sesame"
        ],
        "Botanicals": [
            "Turmeric", "Curcumin", "Ginkgo Biloba", "Echinacea", "Ginseng",
            "Green Tea Extract", "EGCG", "Garlic", "Saw Palmetto", "Milk Thistle",
            "St. John's Wort", "Valerian", "Ashwagandha", "Rhodiola"
        ],
        "Inactive Ingredients": [
            "Microcrystalline Cellulose", "Magnesium Stearate", "Silicon Dioxide",
            "Gelatin", "Hypromellose", "Stearic Acid", "Croscarmellose Sodium",
            "Dicalcium Phosphate", "Maltodextrin", "Rice Flour"
        ]
    }
    
    total_tested = 0
    total_mapped = 0
    unmapped_by_category = {}
    
    for category, ingredients in test_categories.items():
        print(f"\n{category}:")
        mapped_count = 0
        unmapped_ingredients = []
        
        for ingredient in ingredients:
            # Test mapping
            standard_name, mapped, forms = normalizer._enhanced_ingredient_mapping(ingredient)
            if mapped:
                mapped_count += 1
                total_mapped += 1
                print(f"  ✅ {ingredient}")
            else:
                unmapped_ingredients.append(ingredient)
                print(f"  ❌ {ingredient}")
            
            total_tested += 1
        
        coverage = (mapped_count / len(ingredients)) * 100
        print(f"  📊 Coverage: {mapped_count}/{len(ingredients)} ({coverage:.1f}%)")
        
        if unmapped_ingredients:
            unmapped_by_category[category] = unmapped_ingredients
    
    overall_coverage = (total_mapped / total_tested) * 100
    print(f"\n📊 OVERALL COVERAGE: {total_mapped}/{total_tested} ({overall_coverage:.1f}%)")
    
    return unmapped_by_category, overall_coverage

def generate_unmapped_report(normalizer, sample_size=100):
    """Generate report of top unmapped ingredients for enrichment planning"""
    print(f"\n📈 TOP UNMAPPED INGREDIENTS REPORT (Sample: {sample_size}):")
    print("-" * 60)
    
    # Simulate processing some ingredients to populate unmapped counter
    test_ingredients = [
        "Unknown Ingredient A", "Proprietary Blend XYZ", "Natural Flavor Complex",
        "Artificial Color Mix", "Unspecified Extract", "Custom Formulation",
        "Trade Secret Ingredient", "Patented Compound", "Novel Ingredient"
    ]
    
    for ingredient in test_ingredients:
        normalizer._enhanced_ingredient_mapping(ingredient)
    
    if normalizer.unmapped_ingredients:
        print("Top unmapped ingredients by occurrence:")
        for ingredient, count in normalizer.unmapped_ingredients.most_common(10):
            print(f"  {count:>3}x {ingredient}")
        
        print(f"\nTotal unique unmapped ingredients: {len(normalizer.unmapped_ingredients)}")
        print("💡 These ingredients should be prioritized for enrichment database updates")
    else:
        print("No unmapped ingredients found in current test")
    
    return list(normalizer.unmapped_ingredients.keys())

def best_practices_recommendations():
    """Provide best practices recommendations"""
    print("\n🎯 BEST PRACTICES & RECOMMENDATIONS:")
    print("=" * 60)
    
    print("\n1. 📋 WORKFLOW PHASES:")
    print("   ✅ CLEANING: Use core mapping databases only")
    print("      - Focus on ingredient identification and standardization")
    print("      - Flag harmful additives and allergens")
    print("      - Track unmapped ingredients for enrichment")
    print()
    print("   ⏳ ENRICHMENT: Use specialized databases")
    print("      - Add clinical evidence, absorption enhancers")
    print("      - Enhance with delivery systems, synergies")
    print("      - Update core databases with new mappings")
    print()
    print("   🎯 SCORING: Calculate final quality scores")
    print("      - Apply RDA/UL comparisons")
    print("      - Weight ingredients by importance")
    print("      - Generate final supplement scores")
    
    print("\n2. 📊 UNMAPPED INGREDIENT REPORTING:")
    print("   ✅ RECOMMENDED: Include top 10 unmapped ingredients in reports")
    print("      - Helps prioritize enrichment efforts")
    print("      - Shows data quality improvement opportunities")
    print("      - Tracks coverage improvements over time")
    print()
    print("   ❌ AVOID: Including all unmapped ingredients")
    print("      - Can overwhelm reports with noise")
    print("      - Many may be typos or rare ingredients")
    
    print("\n3. 🔄 MAINTENANCE WORKFLOW:")
    print("   1. Run cleaning phase -> identify top unmapped ingredients")
    print("   2. Research and add mappings to appropriate reference files")
    print("   3. Run enrichment phase -> enhance with additional data")
    print("   4. Run scoring phase -> calculate final quality scores")
    print("   5. Deploy to supplements app and Supabase")
    
    print("\n4. 📈 PERFORMANCE MONITORING:")
    print("   ✅ Track mapping coverage percentage over time")
    print("   ✅ Monitor processing speed and cache effectiveness")
    print("   ✅ Log top unmapped ingredients for enrichment planning")
    print("   ✅ Validate data quality with spot checks")

if __name__ == "__main__":
    # Analyze reference files
    cleaning_dbs, enrichment_dbs = analyze_reference_files()
    
    # Test ingredient coverage
    unmapped_by_category, coverage = test_ingredient_coverage()
    
    # Generate unmapped report
    normalizer = EnhancedDSLDNormalizer()
    unmapped_list = generate_unmapped_report(normalizer)
    
    # Provide recommendations
    best_practices_recommendations()
    
    print(f"\n{'='*80}")
    print("ANALYSIS COMPLETE!")
    print(f"Overall ingredient coverage: {coverage:.1f}%")
    print(f"Reference databases: {len(cleaning_dbs)} cleaning + {len(enrichment_dbs)} enrichment")
    print(f"{'='*80}")
