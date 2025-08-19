#!/usr/bin/env python3
"""
Test the enhanced blacklist to ensure it prevents dangerous fuzzy matches
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_normalizer import EnhancedDSLDNormalizer

def test_enhanced_blacklist():
    """Test critical blacklist protections"""
    
    print("=== Testing Enhanced Blacklist Safety System ===\n")
    
    # Initialize normalizer
    normalizer = EnhancedDSLDNormalizer()
    matcher = normalizer.matcher
    
    print(f"Total blacklist entries: {len(matcher.fuzzy_blacklist)}")
    
    # Test critical dangerous matches that should be BLOCKED
    dangerous_tests = [
        # Original case
        ("lactose", "lactase"),
        
        # Vitamin confusion (different bioavailability)
        ("vitamin d", "vitamin d2"),
        ("folate", "folic acid"),
        ("vitamin b12", "methylcobalamin"),
        
        # Fatty acid confusion (different benefits)
        ("omega 3", "omega 6"),
        ("epa", "dha"),
        ("linoleic acid", "linolenic acid"),
        
        # Gut health confusion
        ("probiotic", "prebiotic"),
        ("digestive enzyme", "probiotic"),
        
        # Amino acid confusion
        ("glucose", "glucosamine"),
        ("taurine", "l-tyrosine"),
        ("methionine", "metformin"),
        
        # Herb vs extract (different potency)
        ("turmeric", "curcumin"),
        ("green tea", "egcg"),
        ("ginkgo", "ginkgo extract"),
        
        # Hormone vs precursor
        ("dhea", "dha"),
        ("melatonin", "tryptophan"),
        
        # Joint support confusion
        ("glucosamine", "chondroitin"),
        ("msm", "dmso"),
        
        # Sugar vs sugar alcohol
        ("glucose", "mannitol"),
        ("sucrose", "xylitol"),
    ]
    
    print("=== Testing Dangerous Matches (Should be BLOCKED) ===")
    blocked_count = 0
    
    for query, target in dangerous_tests:
        is_blacklisted = matcher._is_blacklisted_match(query, target)
        
        if is_blacklisted:
            print(f"✅ BLOCKED: '{query}' -> '{target}'")
            blocked_count += 1
        else:
            print(f"❌ ALLOWED: '{query}' -> '{target}' (DANGEROUS!)")
    
    print(f"\nBlocked {blocked_count}/{len(dangerous_tests)} dangerous matches")
    
    # Test safe matches that should NOT be blocked
    safe_tests = [
        ("vitamin c", "ascorbic acid"),  # Same compound
        ("omega 3", "fish oil"),        # Related compounds
        ("calcium", "calcium citrate"), # Mineral and its form
        ("magnesium", "magnesium glycinate"), # Mineral and its form
        ("protein", "whey protein"),    # General to specific
        ("fiber", "psyllium fiber"),    # General to specific
        ("antioxidant", "vitamin e"),   # Category to specific
    ]
    
    print("\n=== Testing Safe Matches (Should be ALLOWED) ===")
    allowed_count = 0
    
    for query, target in safe_tests:
        is_blacklisted = matcher._is_blacklisted_match(query, target)
        
        if not is_blacklisted:
            print(f"✅ ALLOWED: '{query}' -> '{target}'")
            allowed_count += 1
        else:
            print(f"❌ BLOCKED: '{query}' -> '{target}' (Should be allowed)")
    
    print(f"\nAllowed {allowed_count}/{len(safe_tests)} safe matches")
    
    # Summary
    print(f"\n=== Blacklist Safety Summary ===")
    print(f"🛡️  Total blacklist protections: {len(matcher.fuzzy_blacklist)}")
    print(f"🚫 Dangerous matches blocked: {blocked_count}/{len(dangerous_tests)} ({blocked_count/len(dangerous_tests)*100:.1f}%)")
    print(f"✅ Safe matches allowed: {allowed_count}/{len(safe_tests)} ({allowed_count/len(safe_tests)*100:.1f}%)")
    
    if blocked_count == len(dangerous_tests) and allowed_count == len(safe_tests):
        print("\n🎉 PERFECT! Enhanced blacklist is working flawlessly!")
        print("   Your supplement analysis is now much safer from dangerous false positives.")
    else:
        print("\n⚠️  Some tests failed - review needed")

if __name__ == "__main__":
    test_enhanced_blacklist()