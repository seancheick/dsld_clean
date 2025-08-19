#!/usr/bin/env python3
"""
Performance test for DSLD processing optimizations
"""

import sys
import time
import json
from pathlib import Path

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent / "scripts"))

from enhanced_normalizer import EnhancedDSLDNormalizer

def test_normalizer_performance():
    """Test the performance of the enhanced normalizer"""
    print("=== DSLD Enhanced Normalizer Performance Test ===")

    # Initialize normalizer
    print("Initializing normalizer...")
    start_time = time.time()
    normalizer = EnhancedDSLDNormalizer()
    init_time = time.time() - start_time
    print(f"✅ Initialization time: {init_time:.2f} seconds")

    # Test fast lookup performance
    print("\nTesting fast lookup performance...")
    test_ingredients = ["Vitamin C", "Sorbitol", "Milk", "Unknown Ingredient"]

    start_time = time.time()
    for ingredient in test_ingredients * 100:  # Test 400 lookups
        result = normalizer._fast_ingredient_lookup(ingredient)
    fast_lookup_time = time.time() - start_time
    print(f"✅ Fast lookup (400 lookups): {fast_lookup_time:.3f} seconds")
    print(f"✅ Average per lookup: {fast_lookup_time/400:.6f} seconds")
    
    # Test data
    test_product = {
        "id": "test123",
        "fullName": "Test Vitamin C with Zinc Lozenges",
        "brandName": "Test Brand",
        "upcSku": "123456789012",
        "ingredientRows": [
            {
                "name": "Vitamin C",
                "order": 1,
                "quantity": [{"quantity": 500, "unit": "mg"}]
            },
            {
                "name": "Zinc",
                "order": 2,
                "quantity": [{"quantity": 15, "unit": "mg"}]
            }
        ],
        "otheringredients": {
            "ingredients": [
                {"name": "Sorbitol"},
                {"name": "Mannitol"},
                {"name": "Natural Orange Flavor"},
                {"name": "Citric Acid"},
                {"name": "Magnesium Stearate"}
            ]
        }
    }
    
    # Test single product processing
    print("\nTesting single product processing...")
    start_time = time.time()
    cleaned_data = normalizer.normalize_product(test_product)
    single_time = time.time() - start_time
    print(f"✅ Single product processing: {single_time:.3f} seconds")
    
    # Test batch processing
    print("\nTesting batch processing (10 products)...")
    start_time = time.time()
    for i in range(10):
        test_product["id"] = f"test{i}"
        cleaned_data = normalizer.normalize_product(test_product)
    batch_time = time.time() - start_time
    avg_time = batch_time / 10
    print(f"✅ Batch processing (10 products): {batch_time:.3f} seconds")
    print(f"✅ Average per product: {avg_time:.3f} seconds")
    print(f"✅ Estimated throughput: {1/avg_time:.0f} products/second")
    
    # Test ingredient mapping performance
    print("\nTesting ingredient mapping performance...")
    test_ingredients = [
        "Vitamin C", "Ascorbic Acid", "Zinc", "Sorbitol", "Mannitol", 
        "Xylitol", "Sucralose", "Natural Flavor", "Unknown Ingredient XYZ"
    ]
    
    start_time = time.time()
    for ingredient in test_ingredients * 10:  # Test 90 ingredients
        standard_name, mapped, forms = normalizer._enhanced_ingredient_mapping(ingredient)
        harmful_info = normalizer._enhanced_harmful_check(ingredient)
    mapping_time = time.time() - start_time
    avg_mapping_time = mapping_time / 90
    print(f"✅ Ingredient mapping (90 ingredients): {mapping_time:.3f} seconds")
    print(f"✅ Average per ingredient: {avg_mapping_time:.4f} seconds")

    # Test parallel processing performance
    print("\nTesting parallel processing performance...")

    # Create a product with many ingredients to trigger parallel processing
    large_product = {
        "id": "large_test",
        "fullName": "Large Test Product",
        "brandName": "Test Brand",
        "ingredientRows": [],
        "otheringredients": {
            "ingredients": [
                {"name": f"Ingredient {i}", "order": i}
                for i in range(20)  # 20 ingredients to trigger parallel processing
            ]
        }
    }

    # Test with parallel processing
    start_time = time.time()
    cleaned_large = normalizer.normalize_product(large_product)
    parallel_time = time.time() - start_time
    print(f"✅ Large product (20 ingredients): {parallel_time:.3f} seconds")

    # Test cache effectiveness after processing
    print("\nTesting cache effectiveness after processing...")
    start_time = time.time()
    cleaned_large_2 = normalizer.normalize_product(large_product)
    cached_time = time.time() - start_time
    print(f"✅ Large product (cached): {cached_time:.3f} seconds")
    print(f"✅ Cache speedup: {parallel_time/cached_time:.1f}x faster")
    
    # Test cache effectiveness
    print("\nTesting cache effectiveness...")
    
    # First run (cache miss)
    start_time = time.time()
    variations1 = normalizer.ingredient_variations
    cache_miss_time = time.time() - start_time
    
    # Second run (cache hit)
    start_time = time.time()
    variations2 = normalizer.ingredient_variations
    cache_hit_time = time.time() - start_time
    
    print(f"✅ Cache miss time: {cache_miss_time:.4f} seconds")
    print(f"✅ Cache hit time: {cache_hit_time:.4f} seconds")
    if cache_hit_time > 0:
        print(f"✅ Cache speedup: {cache_miss_time/cache_hit_time:.0f}x faster")
    else:
        print("✅ Cache speedup: Instant (too fast to measure)")
    print(f"✅ Ingredient variations cached: {len(variations1):,} items")
    
    # Test memory usage
    print("\nTesting memory efficiency...")
    print(f"✅ Ingredient variations: {len(normalizer.ingredient_variations):,} items")
    print(f"✅ Form variations: {len(normalizer.form_variations):,} items")
    print(f"✅ Harmful variations: {len(normalizer.harmful_variations):,} items")
    
    # Summary
    print("\n" + "="*60)
    print("PERFORMANCE SUMMARY")
    print("="*60)
    print(f"Initialization time:     {init_time:.2f} seconds")
    print(f"Single product:          {single_time:.3f} seconds")
    print(f"Average per product:     {avg_time:.3f} seconds")
    print(f"Estimated throughput:    {1/avg_time:.0f} products/second")
    print(f"Ingredient mapping:      {avg_mapping_time:.4f} seconds/ingredient")
    if cache_hit_time > 0:
        print(f"Cache effectiveness:     {cache_miss_time/cache_hit_time:.0f}x speedup")
    else:
        print("Cache effectiveness:     Instant speedup")
    print("="*60)
    
    # Performance targets
    print("\nPERFORMANCE TARGETS:")
    if avg_time < 0.1:
        print("✅ EXCELLENT: < 0.1 seconds per product")
    elif avg_time < 0.5:
        print("✅ GOOD: < 0.5 seconds per product")
    elif avg_time < 1.0:
        print("⚠️  ACCEPTABLE: < 1.0 seconds per product")
    else:
        print("❌ SLOW: > 1.0 seconds per product - needs optimization")
    
    if 1/avg_time > 100:
        print("✅ EXCELLENT: > 100 products/second throughput")
    elif 1/avg_time > 50:
        print("✅ GOOD: > 50 products/second throughput")
    elif 1/avg_time > 10:
        print("⚠️  ACCEPTABLE: > 10 products/second throughput")
    else:
        print("❌ SLOW: < 10 products/second throughput")

def test_unmapped_tracking():
    """Test that unmapped tracking is working correctly"""
    print("\n=== Testing Unmapped Ingredient Tracking ===")
    
    normalizer = EnhancedDSLDNormalizer()
    
    # Test with known and unknown ingredients
    test_product = {
        "id": "test_unmapped",
        "fullName": "Test Product",
        "brandName": "Test",
        "ingredientRows": [],
        "otheringredients": {
            "ingredients": [
                {"name": "Sorbitol"},  # Should be mapped (harmful additive)
                {"name": "Unknown Chemical XYZ"},  # Should be unmapped
                {"name": "Another Unknown Ingredient"}  # Should be unmapped
            ]
        }
    }
    
    # Clear unmapped counters
    normalizer.unmapped_ingredients.clear()
    
    # Process product
    cleaned_data = normalizer.normalize_product(test_product)
    
    # Check results
    inactive_ingredients = cleaned_data.get("inactiveIngredients", [])
    
    print("Ingredient mapping results:")
    for ing in inactive_ingredients:
        name = ing.get("name")
        mapped = ing.get("mapped")
        is_harmful = ing.get("isHarmful")
        print(f"  {name}: mapped={mapped}, harmful={is_harmful}")
    
    print(f"\nUnmapped ingredients count: {len(normalizer.unmapped_ingredients)}")
    for name, count in normalizer.unmapped_ingredients.most_common():
        print(f"  {name}: {count} occurrences")
    
    # Verify results
    expected_unmapped = {"Unknown Chemical XYZ", "Another Unknown Ingredient"}
    actual_unmapped = set(normalizer.unmapped_ingredients.keys())
    
    if actual_unmapped == expected_unmapped:
        print("✅ Unmapped tracking working correctly")
    else:
        print(f"❌ Unmapped tracking issue:")
        print(f"   Expected: {expected_unmapped}")
        print(f"   Actual: {actual_unmapped}")

def test_real_data_performance():
    """Test performance with real DSLD data if available"""
    print("\n=== Testing with Real DSLD Data ===")

    # Look for real data files
    baseline_file = Path("products_baseline.json")
    if baseline_file.exists():
        print("Found products_baseline.json - testing with baseline data")
        json_files = [baseline_file]
    else:
        data_dir = Path("dsld_data")
        if not data_dir.exists():
            print("⚠️  No real data directory found (dsld_data)")
            return

        json_files = list(data_dir.glob("*.json"))
        if not json_files:
            print("⚠️  No JSON files found in dsld_data directory")
            return

    print(f"Found {len(json_files)} real data files")

    # Test with files
    normalizer = EnhancedDSLDNormalizer()

    total_time = 0
    total_ingredients = 0
    successful_products = 0

    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Handle baseline file (array of products) vs single product files
            if isinstance(data, list):
                products = data[:5]  # Test first 5 products from baseline
                print(f"Testing with {len(products)} products from {file_path.name}...")
            else:
                products = [data]  # Single product file
                print(f"Testing with 1 product from {file_path.name}...")

            for i, raw_data in enumerate(products):
                start_time = time.time()
                cleaned_data = normalizer.normalize_product(raw_data)
                process_time = time.time() - start_time

                total_time += process_time
                successful_products += 1

                # Count ingredients
                active_count = len(cleaned_data.get("activeIngredients", []))
                inactive_count = len(cleaned_data.get("inactiveIngredients", []))
                total_ingredients += active_count + inactive_count

                product_id = raw_data.get("id", f"product_{i}")
                print(f"  ✅ {product_id}: {process_time:.3f}s ({active_count}+{inactive_count} ingredients)")

        except Exception as e:
            print(f"  ❌ {file_path.name}: Error - {e}")

    if successful_products > 0:
        avg_time = total_time / successful_products
        avg_ingredients = total_ingredients / successful_products

        print(f"\n📊 Real Data Performance Summary:")
        print(f"  Products processed: {successful_products}")
        print(f"  Total processing time: {total_time:.3f} seconds")
        print(f"  Average per product: {avg_time:.3f} seconds")
        print(f"  Average ingredients per product: {avg_ingredients:.1f}")
        print(f"  Throughput: {successful_products/total_time:.1f} products/second")
        print(f"  Ingredient processing rate: {total_ingredients/total_time:.1f} ingredients/second")

if __name__ == "__main__":
    print("DSLD Performance Test Suite")
    print("=" * 60)

    test_normalizer_performance()
    test_unmapped_tracking()
    test_real_data_performance()

    print("\n" + "=" * 60)
    print("Performance test complete!")
