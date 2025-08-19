#!/usr/bin/env python3
"""
Test the critical dosage protection system
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_normalizer import EnhancedDSLDNormalizer

def test_dosage_protection():
    """Test dosage confusion protection"""
    
    print("=== CRITICAL: Testing Dosage Protection System ===\n")
    
    normalizer = EnhancedDSLDNormalizer()
    matcher = normalizer.matcher
    
    # CRITICAL TEST CASES: These should be BLOCKED
    dangerous_dosage_cases = [
        ("vitamin d 1000 iu", "vitamin d 5000 iu"),   # 5x difference
        ("calcium 500mg", "calcium 1000mg"),          # 2x difference  
        ("vitamin b12 1000 mcg", "vitamin b12 1 mg"),  # Same amount, different units
        ("magnesium 200mg", "magnesium 400mg"),       # 2x difference
        ("vitamin c 500mg", "vitamin c 1000mg"),      # 2x difference
        ("zinc 15mg", "zinc 50mg"),                   # 3.3x difference
        ("iron 18mg", "iron 65mg"),                   # 3.6x difference
        ("probiotics 10 billion", "probiotics 50 billion"), # 5x difference
    ]
    
    # SAFE TEST CASES: These should be ALLOWED
    safe_dosage_cases = [
        ("vitamin d", "vitamin d3"),                   # No dosage conflict
        ("calcium", "calcium citrate"),               # Generic to specific form
        ("magnesium", "magnesium glycinate"),         # Generic to specific form
        ("vitamin c 500mg", "vitamin c 600mg"),       # <20% difference (safe)
        ("zinc 15mg", "zinc 16mg"),                   # <20% difference (safe)
        ("omega 3", "fish oil"),                      # Related but no dosage
    ]
    
    # UNIT CONFUSION CASES: These should be BLOCKED
    unit_confusion_cases = [
        ("vitamin d 1000 iu", "vitamin d 25 mcg"),    # IU vs mcg
        ("vitamin b12 1000 mcg", "vitamin b12 1 mg"), # mcg vs mg (1000x diff)
        ("calcium 500mg", "calcium 0.5g"),           # mg vs g  
        ("probiotics 10 billion", "probiotics 10000 million"), # billion vs million
    ]
    
    print("🔴 TESTING DANGEROUS DOSAGE CASES (Should be BLOCKED)")
    blocked_dosage = 0
    for query, target in dangerous_dosage_cases:
        is_blocked = matcher._is_blacklisted_match(query, target)
        if is_blocked:
            print(f"✅ BLOCKED: '{query}' vs '{target}'")
            blocked_dosage += 1
        else:
            print(f"❌ ALLOWED: '{query}' vs '{target}' (DANGEROUS!)")
    
    print(f"\n🔴 TESTING UNIT CONFUSION CASES (Should be BLOCKED)")
    blocked_units = 0
    for query, target in unit_confusion_cases:
        is_blocked = matcher._is_blacklisted_match(query, target)
        if is_blocked:
            print(f"✅ BLOCKED: '{query}' vs '{target}'")
            blocked_units += 1
        else:
            print(f"❌ ALLOWED: '{query}' vs '{target}' (DANGEROUS!)")
    
    print(f"\n🟢 TESTING SAFE CASES (Should be ALLOWED)")
    allowed_safe = 0
    for query, target in safe_dosage_cases:
        is_blocked = matcher._is_blacklisted_match(query, target)
        if not is_blocked:
            print(f"✅ ALLOWED: '{query}' vs '{target}'")
            allowed_safe += 1
        else:
            print(f"❌ BLOCKED: '{query}' vs '{target}' (Should be allowed)")
    
    # Summary
    total_dangerous = len(dangerous_dosage_cases) + len(unit_confusion_cases)
    total_blocked = blocked_dosage + blocked_units
    
    print(f"\n=== DOSAGE PROTECTION RESULTS ===")
    print(f"🛡️  Dangerous dosage cases blocked: {blocked_dosage}/{len(dangerous_dosage_cases)}")
    print(f"🛡️  Unit confusion cases blocked: {blocked_units}/{len(unit_confusion_cases)}")
    print(f"🛡️  Total dangerous cases blocked: {total_blocked}/{total_dangerous} ({total_blocked/total_dangerous*100:.1f}%)")
    print(f"✅ Safe cases allowed: {allowed_safe}/{len(safe_dosage_cases)} ({allowed_safe/len(safe_dosage_cases)*100:.1f}%)")
    
    if total_blocked == total_dangerous and allowed_safe == len(safe_dosage_cases):
        print("\n🎉 PERFECT! Dosage protection working flawlessly!")
        print("   Your supplement scoring is now protected from dosage confusion!")
    else:
        print("\n⚠️  Some protection tests failed - review needed")
    
    # Test specific dosage detection
    print(f"\n=== TESTING DOSAGE DETECTION ===")
    test_dosages = [
        "vitamin d 1000 iu",
        "calcium 500mg", 
        "vitamin b12 1000 mcg",
        "probiotics 50 billion cfu",
        "omega 3 1000mg",
    ]
    
    import re
    dosage_pattern = r'(\d+(?:\.\d+)?)\s*(mg|mcg|iu|g|units?|billion|million)'
    
    for test in test_dosages:
        dosages = re.findall(dosage_pattern, test, re.IGNORECASE)
        print(f"'{test}' -> Detected dosages: {dosages}")

if __name__ == "__main__":
    test_dosage_protection()