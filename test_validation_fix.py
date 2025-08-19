#!/usr/bin/env python3
"""Test script to verify validation logic fixes"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / "scripts"))

from dsld_validator import DSLDValidator
from constants import STATUS_SUCCESS, STATUS_NEEDS_REVIEW, STATUS_INCOMPLETE

def test_upc_validation():
    """Test improved UPC/SKU validation"""
    print("Testing UPC/SKU validation improvements...")
    
    validator = DSLDValidator()
    
    test_cases = [
        # (upc_sku, should_be_valid)
        ("123456789012", True),  # Valid UPC-A
        ("123456", True),         # Valid UPC-E
        ("#15585", True),         # SKU with # prefix (now valid)
        ("#1569", True),          # Another SKU
        ("Rev. 04", True),        # Version code (now valid)
        ("SKU: ABC123", True),    # SKU with prefix
        ("Item: 12345", True),    # Item code
        ("v1.2", True),           # Version number
        ("ABC-123", True),        # Standard SKU
        ("", False),              # Empty
        ("!@#$%", False),         # Invalid characters
    ]
    
    for upc_sku, expected in test_cases:
        is_valid = validator.validate_upc_sku(upc_sku)
        status = "✓" if is_valid == expected else "✗"
        print(f"  {status} '{upc_sku}': {'Valid' if is_valid else 'Invalid'}")
    
    print()

def test_status_determination():
    """Test that products with only invalid UPC don't go to needs_review"""
    print("Testing status determination logic...")
    
    validator = DSLDValidator()
    
    # Test case 1: Complete product with invalid UPC format (should be SUCCESS now)
    product1 = {
        "id": "12345",
        "fullName": "Test Product",
        "brandName": "Test Brand",
        "ingredientRows": [{"name": "Vitamin C"}],
        "upcSku": "#15585",  # Invalid format that would have triggered review
        "productType": "Vitamin",
        "physicalState": "Tablet"
    }
    
    status1, missing1, details1 = validator.validate_product(product1)
    print(f"  Product with invalid UPC only: {status1} {'✓' if status1 == STATUS_SUCCESS else '✗ (Should be SUCCESS)'}")
    
    # Test case 2: Product missing UPC entirely (should still be SUCCESS)
    product2 = {
        "id": "12346",
        "fullName": "Test Product 2",
        "brandName": "Test Brand",
        "ingredientRows": [{"name": "Vitamin D"}],
        "productType": "Vitamin",
        "physicalState": "Tablet"
    }
    
    status2, missing2, details2 = validator.validate_product(product2)
    print(f"  Product missing UPC: {status2} {'✓' if status2 == STATUS_SUCCESS else '✗ (Should be SUCCESS)'}")
    
    # Test case 3: Product with invalid UPC AND other issues (should be NEEDS_REVIEW)
    product3 = {
        "id": "12347",
        "fullName": "Test Product 3",
        "brandName": "Test Brand",
        "ingredientRows": [],  # No ingredients - quality issue
        "upcSku": "#15585",
        "productType": "Vitamin",
        "physicalState": "Tablet"
    }
    
    status3, missing3, details3 = validator.validate_product(product3)
    print(f"  Product with invalid UPC + no ingredients: {status3} {'✓' if status3 == STATUS_NEEDS_REVIEW else '✗ (Should be NEEDS_REVIEW)'}")
    
    # Test case 4: Product missing critical field (should be INCOMPLETE)
    product4 = {
        "fullName": "Test Product 4",
        "brandName": "Test Brand",
        "ingredientRows": [{"name": "Vitamin E"}],
        "upcSku": "123456789012",
        "productType": "Vitamin",
        "physicalState": "Tablet"
    }
    
    status4, missing4, details4 = validator.validate_product(product4)
    print(f"  Product missing ID (critical): {status4} {'✓' if status4 == STATUS_INCOMPLETE else '✗ (Should be INCOMPLETE)'}")
    
    print()

def test_real_world_examples():
    """Test with real examples that were incorrectly sent to needs_review"""
    print("Testing real-world examples...")
    
    validator = DSLDValidator()
    
    # Example from actual data
    examples = [
        {
            "name": "Calcium Complex",
            "data": {
                "id": "200743",
                "fullName": "Calcium Complex",
                "brandName": "Nikken Wellness Kenzen",
                "upcSku": "#15585",
                "ingredientRows": [{"name": "Vitamin D3"}, {"name": "Calcium"}],
                "productType": "Other Combinations",
                "physicalState": "Tablet or Pill"
            }
        },
        {
            "name": "Mega Daily 4 for Men",
            "data": {
                "id": "200768",
                "fullName": "Mega Daily 4 for Men",
                "brandName": "Nikken Wellness Kenzen",
                "upcSku": "#1569",
                "ingredientRows": [{"name": "Vitamin A"}, {"name": "Vitamin C"}],
                "productType": "Other Combinations",
                "physicalState": "Tablet or Pill"
            }
        },
        {
            "name": "Gokshuradi Guggulu",
            "data": {
                "id": "199546",
                "fullName": "Gokshuradi Guggulu",
                "brandName": "Banyan Botanicals",
                "upcSku": "Rev. 04",
                "ingredientRows": [{"name": "Tribulus"}, {"name": "Guggul"}],
                "productType": "Botanical",
                "physicalState": "Tablet or Pill"
            }
        }
    ]
    
    for example in examples:
        status, missing, details = validator.validate_product(example["data"])
        expected = STATUS_SUCCESS
        result = "✓" if status == expected else f"✗ (Got {status}, expected {expected})"
        print(f"  {example['name']}: {result}")
    
    print()

def main():
    print("=" * 60)
    print("TESTING VALIDATION FIXES")
    print("=" * 60)
    print()
    
    test_upc_validation()
    test_status_determination()
    test_real_world_examples()
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("\nFixed issues:")
    print("• UPC/SKU validation now accepts common formats (#123, Rev. 04, etc.)")
    print("• Products with only invalid UPC format no longer sent to needs_review")
    print("• Real-world examples should now go to 'cleaned' instead of 'needs_review'")
    print()

if __name__ == "__main__":
    main()