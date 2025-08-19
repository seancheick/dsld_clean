#!/usr/bin/env python3
"""
Analyze current accuracy safeguards and suggest enhancements
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_normalizer import EnhancedDSLDNormalizer

def analyze_current_accuracy():
    """Analyze current accuracy safeguards"""
    
    print("=== Current Accuracy Safeguards Analysis ===\n")
    
    normalizer = EnhancedDSLDNormalizer()
    matcher = normalizer.matcher
    
    print("✅ CURRENT SAFEGUARDS:")
    print(f"   • Fuzzy threshold: {matcher.fuzzy_threshold}% (Conservative)")
    print(f"   • Partial threshold: {matcher.partial_threshold}% (Very Conservative)")
    print(f"   • Blacklist protections: {len(matcher.fuzzy_blacklist)} critical pairs")
    print(f"   • Context disambiguation: {len(normalizer.ingredient_context_lookup)} entries")
    print(f"   • Caching system: Multiple levels (fuzzy, exact, ingredient)")
    print(f"   • Preprocessing: Comprehensive text normalization")
    
    print("\n🎯 POTENTIAL ENHANCEMENT AREAS:")
    
    # Test some edge cases that could cause issues
    edge_cases = [
        # Dosage confusion
        ("vitamin d 1000 iu", "vitamin d 5000 iu"),  # Different dosages
        ("calcium 500mg", "calcium 1000mg"),         # Different dosages
        
        # Form confusion  
        ("magnesium", "magnesium chelate"),          # Generic vs specific form
        ("zinc", "zinc bisglycinate"),               # Generic vs specific form
        
        # Brand vs generic
        ("coq10", "ubiquinol"),                      # Different CoQ10 forms
        ("vitamin e", "mixed tocopherols"),          # Generic vs specific
        
        # Measurement unit confusion
        ("vitamin d 1000 iu", "vitamin d 25 mcg"),   # Same amount, different units
        ("vitamin b12 1000 mcg", "vitamin b12 1 mg"), # Same amount, different units
        
        # Concentration confusion
        ("ginkgo extract 120mg", "ginkgo 24% extract"), # Different ways to express potency
        ("turmeric extract", "turmeric 95% curcumin"),  # Different concentrations
    ]
    
    print("   1. DOSAGE PRESERVATION - Prevent dosage mixing")
    print("   2. FORM SPECIFICITY - Distinguish supplement forms") 
    print("   3. UNIT NORMALIZATION - Handle measurement conversions")
    print("   4. CONCENTRATION TRACKING - Track extract potencies")
    print("   5. VALIDATION LAYERS - Multi-step verification")
    print("   6. CONFIDENCE SCORING - Rate match certainty")
    
    print("\n📊 EDGE CASE ANALYSIS:")
    for query, target in edge_cases:
        is_blacklisted = matcher._is_blacklisted_match(query, target)
        # Simulate fuzzy matching
        from fuzzywuzzy import fuzz
        similarity = fuzz.ratio(query.lower(), target.lower())
        
        risk_level = "🔴 HIGH RISK" if similarity > 80 and not is_blacklisted else "🟡 MEDIUM" if similarity > 70 else "🟢 LOW RISK"
        print(f"   • '{query}' vs '{target}': {similarity}% similarity - {risk_level}")
    
    return True

def suggest_enhancements():
    """Suggest specific enhancements"""
    
    print("\n=== RECOMMENDED ACCURACY ENHANCEMENTS ===\n")
    
    print("🛡️  ENHANCEMENT 1: DOSAGE PROTECTION")
    print("   • Add dosage extraction regex")
    print("   • Prevent matching ingredients with different dosages")
    print("   • Preserve original dosage information")
    
    print("\n🛡️  ENHANCEMENT 2: FORM SPECIFICITY BLACKLIST")
    print("   • Add generic vs specific form protections")
    print("   • Prevent 'magnesium' matching 'magnesium oxide' vs 'magnesium glycinate'")
    print("   • Each form has different bioavailability")
    
    print("\n🛡️  ENHANCEMENT 3: UNIT STANDARDIZATION")
    print("   • Add unit conversion validation")
    print("   • Prevent IU vs mcg confusion")
    print("   • Standardize measurement units")
    
    print("\n🛡️  ENHANCEMENT 4: CONCENTRATION VALIDATION")
    print("   • Track extract concentrations (24%, 95%, etc.)")
    print("   • Prevent low-potency matching high-potency")
    print("   • Add standardization percentages")
    
    print("\n🛡️  ENHANCEMENT 5: CONFIDENCE SCORING")
    print("   • Rate each match confidence (0-100%)")
    print("   • Flag low-confidence matches for review")
    print("   • Add manual review threshold")
    
    print("\n🛡️  ENHANCEMENT 6: MULTI-STEP VALIDATION")
    print("   • Step 1: Exact match")
    print("   • Step 2: Blacklist check") 
    print("   • Step 3: Context disambiguation")
    print("   • Step 4: Confidence scoring")
    print("   • Step 5: Final validation")
    
    print("\n🛡️  ENHANCEMENT 7: STRICT MODE OPTION")
    print("   • Ultra-conservative matching for critical applications")
    print("   • Higher thresholds (90%+ fuzzy matching)")
    print("   • More extensive blacklists")
    print("   • Mandatory manual review for edge cases")

if __name__ == "__main__":
    analyze_current_accuracy()
    suggest_enhancements()