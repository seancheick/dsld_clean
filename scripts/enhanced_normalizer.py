"""
Enhanced DSLD Data Normalizer Module
Improved ingredient mapping with fuzzy matching, better preprocessing, and expanded aliases
"""
import re
import json
import logging
import string
import os
import functools
from typing import Dict, List, Tuple, Optional, Any, Set, Union
from datetime import datetime
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Import fuzzy matching with fallback
try:
    from fuzzywuzzy import fuzz, process
    FUZZY_AVAILABLE = True
except ImportError:
    from difflib import SequenceMatcher
    FUZZY_AVAILABLE = False
    print("⚠️ fuzzywuzzy not found. Install for better matching: pip install fuzzywuzzy python-levenshtein")

from constants import (
    INGREDIENT_QUALITY_MAP,
    HARMFUL_ADDITIVES,
    OTHER_INGREDIENTS,  # Merged: non_harmful + passive_inactive
    ALLERGENS,
    TOP_MANUFACTURERS,
    PROPRIETARY_BLENDS,
    EXCLUDED_NUTRITION_FACTS,
    EXCLUDED_LABEL_PHRASES,
    STANDARDIZED_BOTANICALS,
    BANNED_RECALLED,
    BOTANICAL_INGREDIENTS,
    ABSORPTION_ENHANCERS,
    ENHANCED_DELIVERY,
    INGREDIENT_CLASSIFICATION,  # Hierarchical classification (source/summary/component)
    COLOR_INDICATORS,  # Natural vs artificial color classification
    FUZZY_MATCHING_THRESHOLDS,
    ENHANCED_EXCLUSION_PATTERNS,
    DSLD_IMAGE_URL_TEMPLATE,
    CERTIFICATION_PATTERNS,
    ALLERGEN_FREE_PATTERNS,
    UNSUBSTANTIATED_CLAIM_PATTERNS,
    NATURAL_SOURCE_PATTERNS,
    STANDARDIZATION_PATTERNS,
    PROPRIETARY_BLEND_INDICATORS,
    DELIVERY_ENHANCEMENT_PATTERNS,
    CLINICAL_EVIDENCE_PATTERNS,
    DEFAULT_SERVING_SIZE,
    DEFAULT_DAILY_SERVINGS,
    BRANDED_INGREDIENT_TOKENS,
    CLINICALLY_RELEVANT_STRAINS,
    BLEND_HEADER_EXACT_NAMES,
    BLEND_HEADER_PATTERNS_HIGH_CONFIDENCE,
)

# Import the UnmappedIngredientTracker
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unmapped_ingredient_tracker import UnmappedIngredientTracker
from functional_grouping_handler import FunctionalGroupingHandler
import normalization as norm_module  # Single-source normalization

logger = logging.getLogger(__name__)


class EnhancedIngredientMatcher:
    """Enhanced ingredient matching with fuzzy logic and comprehensive preprocessing"""

    def __init__(self):
        # SAFETY FIRST: Increased thresholds for critical ingredient matching
        self.fuzzy_threshold = FUZZY_MATCHING_THRESHOLDS["fuzzy_threshold"]
        self.partial_threshold = FUZZY_MATCHING_THRESHOLDS["partial_threshold"]
        self.minimum_fuzzy_length = FUZZY_MATCHING_THRESHOLDS["minimum_fuzzy_length"]

        # SAFETY: Whitelist of categories where fuzzy matching is safe
        self.safe_fuzzy_categories = {
            "botanical",  # Herb names often have spelling variations
            "flavor",     # Natural flavors, artificial flavors
            "color",      # Natural colors, artificial colors
            "inactive",   # Non-critical inactive ingredients
            "excipient"   # Manufacturing aids, generally safe to fuzzy match
        }

        # CRITICAL SAFETY: Comprehensive blacklist - pairs that should NEVER be matched
        self.fuzzy_blacklist = {
            # (query_pattern, target_pattern) - if query matches first and target matches second, reject
            
            # === CRITICAL SAFETY: Natural vs Synthetic ===
            ("natural", "artificial"),  # Natural vs Artificial anything
            ("organic", "synthetic"),   # Organic vs Synthetic
            ("whole", "isolated"),       # Whole food vs Isolated
            ("extract", "synthetic"),    # Natural extract vs Synthetic
            
            # === CRITICAL SAFETY: Different Food Sources ===
            ("corn starch", "corn syrup"),  # Different corn products
            ("corn flour", "corn syrup"),   # Different corn products
            ("wheat flour", "wheat protein"),  # Different wheat products
            ("soy oil", "soy protein"),     # Different soy products
            ("milk powder", "milk protein"), # Different milk products
            ("rice bran", "rice protein"),  # Different rice products
            ("pea fiber", "pea protein"),   # Different pea products
            
            # === CRITICAL SAFETY: Sugars vs Sugar Alcohols ===
            ("sugar", "sugar alcohol"),     # Sugar vs Sugar alcohols
            ("glucose", "mannitol"),        # Sugar vs Sugar alcohol
            ("glucose", "sorbitol"),        # Sugar vs Sugar alcohol
            ("fructose", "erythritol"),     # Sugar vs Sugar alcohol
            ("sucrose", "xylitol"),         # Sugar vs Sugar alcohol
            
            # === CRITICAL SAFETY: Vitamin Forms (Different Bioavailability) ===
            ("vitamin d", "vitamin d2"),    # D vs D2 (different forms)
            ("vitamin d", "vitamin d3"),    # D vs D3 (different forms)
            ("vitamin b12", "methylcobalamin"), # Different B12 forms
            ("vitamin b12", "cyanocobalamin"), # Different B12 forms
            ("vitamin k", "vitamin k2"),    # Different K forms
            ("vitamin e", "alpha tocopherol"), # Different E forms
            ("folate", "folic acid"),       # Natural vs synthetic
            ("beta carotene", "vitamin a"), # Precursor vs vitamin
            
            # === CRITICAL SAFETY: Fatty Acids (Different Benefits) ===
            ("omega 3", "omega 6"),         # Different omega fatty acids
            ("omega 3", "omega 9"),         # Different omega fatty acids
            ("epa", "dha"),                 # Different omega-3s
            ("linoleic acid", "linolenic acid"), # Omega-6 vs Omega-3
            
            # === CRITICAL SAFETY: Gut Health (Often Confused) ===
            ("probiotic", "prebiotic"),     # Different but often confused
            ("lactose", "lactase"),         # Sugar vs Enzyme
            ("digestive enzyme", "probiotic"), # Enzyme vs Bacteria
            ("fiber", "probiotic"),         # Prebiotic vs Probiotic
            
            # === CRITICAL SAFETY: Amino Acids vs Similar Compounds ===
            ("glucose", "glucosamine"),     # Sugar vs Amino sugar
            ("glycine", "glycerol"),        # Amino acid vs Alcohol
            ("taurine", "l-tyrosine"),      # Different amino acids
            ("arginine", "ornithine"),      # Related but different amino acids
            ("lysine", "glycine"),          # Different amino acids
            ("methionine", "metformin"),    # Amino acid vs Drug
            
            # === CRITICAL SAFETY: Minerals vs Compounds ===
            ("calcium", "calcium carbonate"), # Element vs Specific form
            ("magnesium", "magnesium oxide"), # Element vs Specific form
            ("magnesium", "magnesium stearate"), # Element vs Flow agent/lubricant
            ("magnesium stearate", "magnesium"), # Flow agent vs Element (reverse)
            ("iron", "iron sulfate"),       # Element vs Specific form
            ("zinc", "zinc oxide"),         # Element vs Specific form
            ("chromium", "chromium picolinate"), # Element vs Specific form
            
            # === CRITICAL SAFETY: Acids vs Salts (Different Absorption) ===
            ("folic acid", "folinic acid"), # Different folate forms
            ("citric acid", "citrate"),     # Acid vs Salt form
            ("lactic acid", "lactate"),     # Acid vs Salt form
            ("ascorbic acid", "ascorbate"), # Vitamin C acid vs salt
            ("malic acid", "malate"),       # Acid vs Salt form
            
            # === CRITICAL SAFETY: Herbs vs Extracts (Different Potency) ===
            ("ginkgo", "ginkgo extract"),   # Whole herb vs concentrated extract
            ("ginseng", "ginseng extract"), # Whole herb vs concentrated extract
            ("turmeric", "curcumin"),       # Whole herb vs active compound
            ("milk thistle", "silymarin"),  # Whole herb vs active compound
            ("green tea", "egcg"),          # Whole herb vs active compound
            ("grape seed", "resveratrol"),  # Different grape compounds
            
            # === CRITICAL SAFETY: Stimulants vs Non-Stimulants ===
            ("caffeine", "l-theanine"),     # Stimulant vs Calming amino acid
            ("guarana", "gaba"),            # Stimulant vs Calming neurotransmitter
            ("ephedra", "echinacea"),       # Banned stimulant vs Immune herb
            
            # === CRITICAL SAFETY: Hormones vs Precursors ===
            ("melatonin", "tryptophan"),    # Hormone vs Precursor amino acid
            ("testosterone", "tribulus"),   # Hormone vs Herb
            ("dhea", "dha"),                # Hormone vs Fatty acid
            ("growth hormone", "arginine"), # Hormone vs Amino acid
            
            # === CRITICAL SAFETY: Antioxidants (Different Mechanisms) ===
            ("vitamin c", "vitamin e"),     # Different antioxidants
            ("coq10", "alpha lipoic acid"), # Different antioxidants
            ("glutathione", "n-acetyl cysteine"), # Antioxidant vs precursor
            ("selenium", "sulfur"),         # Different minerals
            
            # === CRITICAL SAFETY: Joint Support (Different Mechanisms) ===
            ("glucosamine", "chondroitin"), # Different joint compounds
            ("msm", "dmso"),                # Different sulfur compounds
            ("collagen", "gelatin"),        # Different protein forms
            ("hyaluronic acid", "chondroitin"), # Different joint compounds
            
            # === CRITICAL SAFETY: Brain/Cognitive (Different Effects) ===
            ("ginkgo", "gaba"),             # Circulation vs Neurotransmitter
            ("phosphatidylserine", "phosphatidylcholine"), # Different phospholipids
            ("acetyl l-carnitine", "l-carnitine"), # Different carnitine forms
            ("dmae", "choline"),            # Different brain compounds
            
            # === CRITICAL SAFETY: Energy/Metabolism ===
            ("creatine", "carnitine"),      # Different energy compounds
            ("pyruvate", "citrate"),        # Different metabolic compounds
            ("ribose", "glucose"),          # Different sugars

            # === ULTRA CRITICAL: Vitamin/Mineral Number Protection ===
            # Prevent ANY cross-matching between numbered vitamins/minerals
            ("b1", "b2"), ("b1", "b3"), ("b1", "b5"), ("b1", "b6"), ("b1", "b7"), ("b1", "b8"), ("b1", "b9"), ("b1", "b12"),
            ("b2", "b1"), ("b2", "b3"), ("b2", "b5"), ("b2", "b6"), ("b2", "b7"), ("b2", "b8"), ("b2", "b9"), ("b2", "b12"),
            ("b3", "b1"), ("b3", "b2"), ("b3", "b5"), ("b3", "b6"), ("b3", "b7"), ("b3", "b8"), ("b3", "b9"), ("b3", "b12"),
            ("b5", "b1"), ("b5", "b2"), ("b5", "b3"), ("b5", "b6"), ("b5", "b7"), ("b5", "b8"), ("b5", "b9"), ("b5", "b12"),
            ("b6", "b1"), ("b6", "b2"), ("b6", "b3"), ("b6", "b5"), ("b6", "b7"), ("b6", "b8"), ("b6", "b9"), ("b6", "b12"),
            ("b7", "b1"), ("b7", "b2"), ("b7", "b3"), ("b7", "b5"), ("b7", "b6"), ("b7", "b8"), ("b7", "b9"), ("b7", "b12"),
            ("b8", "b1"), ("b8", "b2"), ("b8", "b3"), ("b8", "b5"), ("b8", "b6"), ("b8", "b7"), ("b8", "b9"), ("b8", "b12"),
            ("b9", "b1"), ("b9", "b2"), ("b9", "b3"), ("b9", "b5"), ("b9", "b6"), ("b9", "b7"), ("b9", "b8"), ("b9", "b12"),
            ("b12", "b1"), ("b12", "b2"), ("b12", "b3"), ("b12", "b5"), ("b12", "b6"), ("b12", "b7"), ("b12", "b8"), ("b12", "b9"),

            # Vitamin D protection (D2 vs D3 are VERY different)
            ("d2", "d3"), ("d3", "d2"),
            ("vitamin d2", "vitamin d3"), ("vitamin d3", "vitamin d2"),

            # Vitamin K protection (K1 vs K2 have different functions)
            ("k1", "k2"), ("k2", "k1"),
            ("vitamin k1", "vitamin k2"), ("vitamin k2", "vitamin k1"),

            # Additional mineral protection
            ("chromium", "vanadium"),       # Different trace minerals
        }
        
    @functools.lru_cache(maxsize=2000)  # PERFORMANCE: Reduced from 10000 to prevent memory bloat
    def preprocess_text(self, text: str) -> str:
        """
        Comprehensive text preprocessing with enhanced validation.

        Delegates to normalization module for consistent preprocessing across pipeline.
        """
        # SAFETY: Comprehensive input validation
        text = self.validate_input(text, "ingredient_name")
        if not text:
            return ""

        # Delegate to single-source normalization module
        return norm_module.preprocess_text(text)
    
    def generate_variations(self, text: str) -> List[str]:
        """
        Generate common variations of ingredient names
        """
        variations = [text]
        
        # Add version without spaces
        no_space = text.replace(' ', '')
        if no_space != text:
            variations.append(no_space)
        
        # Add version with hyphens instead of spaces
        hyphenated = text.replace(' ', '-')
        if hyphenated != text:
            variations.append(hyphenated)
        
        # Add common abbreviations
        abbreviations = {
            'vitamin': 'vit',
            'alpha': 'a',
            'beta': 'b',
            'gamma': 'g',
            'delta': 'd',
            'tocopherol': 'toco',
            'tocopheryl': 'toco',
            'ascorbic acid': 'ascorbate',
            'cholecalciferol': 'cholecal',
            'cyanocobalamin': 'cyano',
            'methylcobalamin': 'methyl',
            'pyridoxine': 'pyr',
            'riboflavin': 'ribo',
            'thiamine': 'thia',
            'phylloquinone': 'phyllo'
        }
        
        for full, abbrev in abbreviations.items():
            if full in text:
                variations.append(text.replace(full, abbrev))
            if abbrev in text:
                variations.append(text.replace(abbrev, full))
        
        # Add numeric variations (vitamin d3 -> vitamin d 3)
        if re.search(r'[a-z]\d+', text):
            spaced_num = re.sub(r'([a-z])(\d+)', r'\1 \2', text)
            variations.append(spaced_num)
        
        if re.search(r'[a-z]\s\d+', text):
            unspaced_num = re.sub(r'([a-z])\s(\d+)', r'\1\2', text)
            variations.append(unspaced_num)
        
        return list(set(variations))  # Remove duplicates

    def is_safe_for_fuzzy_matching(self, query: str, category: str = None) -> bool:
        """
        Determine if an ingredient is safe for fuzzy matching based on category and content
        """
        # Always allow exact matches
        if not query:
            return False

        query_lower = query.lower()

        # SAFETY: Block fuzzy matching for critical vitamins/minerals by content analysis
        critical_patterns = [
            r'\bb[1-9][\d]*\b',      # B1, B2, B3, etc.
            r'\bvitamin\s*[a-z]\d+\b',  # vitamin D3, vitamin K2, etc.
            r'\bd[23]\b',            # D2, D3
            r'\bk[12]\b',            # K1, K2
            r'\bomega\s*[369]\b',    # omega-3, omega-6, omega-9
        ]

        for pattern in critical_patterns:
            if re.search(pattern, query_lower):
                return False  # Never fuzzy match critical vitamins/minerals

        # SAFETY: Check if category is in safe list
        if category and category.lower() in self.safe_fuzzy_categories:
            return True

        # SAFETY: Default to EXACT MATCH ONLY for safety
        return False

    def exact_match_critical_aliases(self, query: str, targets: List[str]) -> Optional[str]:
        """
        SAFE exact matching for critical short aliases (B1, D3, K2, etc.)
        This ensures short critical vitamins/minerals get proper exact matches
        """
        if not query or not targets:
            return None

        query_lower = query.lower().strip()

        # Critical short patterns that must be matched exactly
        critical_short_patterns = [
            r'^b[1-9][\d]*$',      # B1, B2, B3, B12, etc.
            r'^d[23]$',            # D2, D3
            r'^k[12]$',            # K1, K2
            r'^vitamin\s*[a-z]\d*$', # vitamin D3, vitamin K2, etc.
        ]

        # Check if query is a critical short pattern
        is_critical = any(re.match(pattern, query_lower) for pattern in critical_short_patterns)

        if is_critical:
            # For critical patterns, only allow exact matches
            for target in targets:
                if query_lower == target.lower().strip():
                    logger.info(f"CRITICAL exact match: '{query}' -> '{target}'")
                    return target

        return None

    def validate_input(self, text: str, field_name: str = "input") -> str:
        """
        Comprehensive input validation with standardized empty handling
        """
        # Handle None
        if text is None:
            logger.debug(f"NULL {field_name} converted to empty string")
            return ""

        # Handle non-string types
        if not isinstance(text, str):
            try:
                text = str(text)
                logger.debug(f"Non-string {field_name} converted: {type(text)} -> str")
            except Exception:
                logger.warning(f"Failed to convert {field_name} to string, using empty")
                return ""

        # Handle whitespace-only strings
        stripped = text.strip()
        if not stripped:
            if text != "":  # Was whitespace-only
                logger.debug(f"Whitespace-only {field_name} converted to empty string")
            return ""

        # Handle common placeholder values
        placeholder_values = {
            "none", "null", "n/a", "na", "not applicable", "unknown",
            "unspecified", "not specified", "nil", "empty", "-", "--", "___"
        }

        if stripped.lower() in placeholder_values:
            logger.debug(f"Placeholder {field_name} '{stripped}' converted to empty string")
            return ""

        return stripped

    def fuzzy_match(self, query: str, targets: List[str], category: str = None) -> Tuple[Optional[str], int]:
        """
        SAFETY-FIRST fuzzy matching with whitelist approach and thread-safe caching
        """
        if not targets or not query:
            return None, 0

        # SAFETY FIRST: Check if fuzzy matching is safe for this ingredient
        if not self.is_safe_for_fuzzy_matching(query, category):
            return None, 0  # Block fuzzy matching for critical ingredients

        # Use thread-safe @lru_cache - convert list to tuple for hashability
        targets_tuple = tuple(targets)
        return self._safe_fuzzy_match_cached(query, targets_tuple, category)

    @functools.lru_cache(maxsize=1000)  # PERFORMANCE: Reduced from 5000 to prevent memory bloat
    def _safe_fuzzy_match_cached(self, query: str, targets_tuple: tuple, category: str = None) -> Tuple[Optional[str], int]:
        """Thread-safe cached version of fuzzy matching"""
        # Convert tuple back to list for processing
        targets = list(targets_tuple)
        return self._perform_safe_fuzzy_match(query, targets, category)

    def _perform_safe_fuzzy_match(self, query: str, targets: List[str], category: str = None) -> Tuple[Optional[str], int]:
        """
        SAFETY-ENHANCED fuzzy matching with comprehensive protection
        """
        # SAFETY: Enhanced minimum length check to prevent false positives
        if len(query) < self.minimum_fuzzy_length:
            return None, 0

        if FUZZY_AVAILABLE:
            # SAFETY: More aggressive filtering - prevent short critical aliases from matching
            # Restore critical vitamins (B1, D3, K2) but only for EXACT matching in other methods
            filtered_targets = [t for t in targets if len(t) >= self.minimum_fuzzy_length]

            # SAFETY: First try exact ratio matching with higher threshold
            match = process.extractOne(query, filtered_targets, scorer=fuzz.ratio)
            if match and match[1] >= self.fuzzy_threshold:
                # SAFETY: Enhanced blacklist checking
                if not self._is_blacklisted_match(query, match[0]):
                    logger.info(f"SAFE fuzzy match: '{query}' -> '{match[0]}' (score: {match[1]}, category: {category})")
                    return match[0], match[1]
                else:
                    logger.warning(f"BLOCKED dangerous fuzzy match: '{query}' -> '{match[0]}' (score: {match[1]})")
                    return None, 0

            # SAFETY: Conservative partial matching only for longer queries and safe categories
            if len(query) >= 8 and category in self.safe_fuzzy_categories:
                match = process.extractOne(query, filtered_targets, scorer=fuzz.partial_ratio)
                if match and match[1] >= self.partial_threshold:
                    if not self._is_blacklisted_match(query, match[0]):
                        logger.info(f"SAFE partial match: '{query}' -> '{match[0]}' (score: {match[1]}, category: {category})")
                        return match[0], match[1]
        else:
            # Fallback to difflib with same safety checks
            best_match = None
            best_score = 0

            filtered_targets = [t for t in targets if len(t) >= self.minimum_fuzzy_length]

            for target in filtered_targets:
                ratio = SequenceMatcher(None, query, target).ratio() * 100
                if ratio > best_score and ratio >= self.fuzzy_threshold:
                    if not self._is_blacklisted_match(query, target):
                        best_score = ratio
                        best_match = target

            if best_match:
                logger.info(f"SAFE difflib match: '{query}' -> '{best_match}' (score: {int(best_score)}, category: {category})")
                return best_match, int(best_score)

        return None, 0
    
    def _is_blacklisted_match(self, query: str, target: str) -> bool:
        """Check if a fuzzy match should be rejected based on blacklist"""
        query_lower = query.lower()
        target_lower = target.lower()
        
        # CRITICAL SAFETY: Check dosage confusion
        if self._has_dosage_confusion(query_lower, target_lower):
            return True
        
        # CRITICAL SAFETY: Check unit confusion  
        if self._has_unit_confusion(query_lower, target_lower):
            return True
        
        # Check standard blacklist
        for blacklisted_query, blacklisted_target in self.fuzzy_blacklist:
            # Check if query contains blacklisted pattern and target contains its counterpart
            if blacklisted_query in query_lower and blacklisted_target in target_lower:
                return True
            # Check reverse direction too
            if blacklisted_target in query_lower and blacklisted_query in target_lower:
                return True
        
        return False
    
    def _has_dosage_confusion(self, query: str, target: str) -> bool:
        """Check if two ingredients have different dosages - CRITICAL for scoring accuracy"""
        # Extract dosages from both strings
        dosage_pattern = r'(\d+(?:\.\d+)?)\s*(mg|mcg|iu|g|units?|billion|million)'
        
        query_dosages = re.findall(dosage_pattern, query, re.IGNORECASE)
        target_dosages = re.findall(dosage_pattern, target, re.IGNORECASE)
        
        # If both have dosages, check if they're different
        if query_dosages and target_dosages:
            # Normalize units for comparison
            query_normalized = self._normalize_dosage(query_dosages[0])
            target_normalized = self._normalize_dosage(target_dosages[0])
            
            # If dosages are significantly different (>20% difference), block the match
            if query_normalized and target_normalized:
                difference_ratio = abs(query_normalized - target_normalized) / max(query_normalized, target_normalized)
                if difference_ratio > 0.2:  # More than 20% difference
                    return True
        
        return False
    
    def _normalize_dosage(self, dosage_tuple) -> float:
        """Normalize dosage to mg for comparison"""
        amount, unit = dosage_tuple
        amount = float(amount)
        unit_lower = unit.lower()
        
        # Convert to mg
        if unit_lower in ['mcg', 'μg']:
            return amount / 1000  # mcg to mg
        elif unit_lower == 'g':
            return amount * 1000  # g to mg
        elif unit_lower == 'iu':
            # IU conversion is complex and vitamin-specific, so we'll be conservative
            # For vitamin D: 1 IU ≈ 0.025 mcg
            # For vitamin E: 1 IU ≈ 0.67 mg
            # Since we can't know the vitamin, we'll treat IU as a special case
            return amount  # Keep as-is for IU
        elif unit_lower in ['mg']:
            return amount
        elif unit_lower in ['billion', 'million']:
            # For probiotics - keep as-is since these are counts, not weights
            return amount
        else:
            return amount  # Default case
    
    def _has_unit_confusion(self, query: str, target: str) -> bool:
        """Check for dangerous unit confusions (IU vs mcg, etc.)"""
        # Dangerous unit pairs that should never be matched
        dangerous_unit_pairs = [
            ('iu', 'mcg'),    # International Units vs micrograms
            ('iu', 'mg'),     # International Units vs milligrams  
            ('mg', 'g'),      # Different magnitudes
            ('mcg', 'mg'),    # 1000x difference
            ('billion', 'million'),  # For probiotics
        ]
        
        unit_pattern = r'\d+\s*(mg|mcg|iu|g|units?|billion|million)'
        
        query_units = re.findall(unit_pattern, query, re.IGNORECASE)
        target_units = re.findall(unit_pattern, target, re.IGNORECASE)
        
        if query_units and target_units:
            query_unit = query_units[0].lower()
            target_unit = target_units[0].lower()
            
            # Check if this is a dangerous unit pairing
            for unit1, unit2 in dangerous_unit_pairs:
                if (query_unit == unit1 and target_unit == unit2) or \
                   (query_unit == unit2 and target_unit == unit1):
                    return True
        
        return False

    def disambiguate_ingredient_match(self, context_text: str, ingredient_data: Dict[str, Any]) -> bool:
        """
        Determine if an ingredient match is valid based on context disambiguation
        
        Args:
            context_text: Text context around the matched ingredient
            ingredient_data: Ingredient form data with context_include/context_exclude
            
        Returns:
            True if match is valid, False if should be rejected
        """
        context_include = ingredient_data.get('context_include', [])
        context_exclude = ingredient_data.get('context_exclude', [])
        
        context_lower = context_text.lower()
        
        # Check for exclusion words (negative confirmation) using word boundaries
        for word in context_exclude:
            # Use word boundaries to match whole words only
            pattern = rf'\b{re.escape(word.lower())}\b'
            if re.search(pattern, context_lower):
                return False  # Definitely not this ingredient
            
        # Check for inclusion words (positive confirmation) using word boundaries
        include_found = False
        for word in context_include:
            pattern = rf'\b{re.escape(word.lower())}\b'
            if re.search(pattern, context_lower):
                include_found = True
                break
                
        if include_found:
            return True   # Definitely this ingredient
            
        # If no disambiguation rules defined, accept the match
        if not context_include and not context_exclude:
            return True
            
        # If disambiguation rules exist but no include words found, be conservative
        if context_include and not include_found:
            return False  # Ambiguous - skip this match
            
        return True  # Default to accepting

    def clear_cache(self):
        """Clear fuzzy matching cache to free memory - now using @lru_cache"""
        # Clear the lru_cache decorators
        if hasattr(self.preprocess_text, 'cache_clear'):
            self.preprocess_text.cache_clear()
        if hasattr(self._safe_fuzzy_match_cached, 'cache_clear'):
            self._safe_fuzzy_match_cached.cache_clear()


class EnhancedDSLDNormalizer:
    """Enhanced DSLD normalizer with improved matching and preprocessing"""
    
    def __init__(self):
        # Load reference data
        self.ingredient_map = self._load_json(INGREDIENT_QUALITY_MAP)
        self.harmful_additives = self._load_json(HARMFUL_ADDITIVES)
        self.allergens_db = self._load_json(ALLERGENS)
        self.manufacturers_db = self._load_json(TOP_MANUFACTURERS)
        self.proprietary_blends = self._load_json(PROPRIETARY_BLENDS)
        self.standardized_botanicals = self._load_json(STANDARDIZED_BOTANICALS)
        self.banned_recalled = self._load_json(BANNED_RECALLED)
        self.other_ingredients = self._load_json(OTHER_INGREDIENTS)  # Merged: non_harmful + passive_inactive
        self.botanical_ingredients = self._load_json(BOTANICAL_INGREDIENTS)
        self.absorption_enhancers = self._load_json(ABSORPTION_ENHANCERS)
        self.enhanced_delivery = self._load_json(ENHANCED_DELIVERY)
        self.clinical_strains_db = self._load_json(
            CLINICALLY_RELEVANT_STRAINS
        )
        self.ingredient_classification = self._load_json(INGREDIENT_CLASSIFICATION)

        # Load color indicators for context-aware mapping (REQUIRED)
        color_indicators_db = self._load_json(COLOR_INDICATORS)
        if not color_indicators_db or not color_indicators_db.get("natural_indicators"):
            raise RuntimeError(
                f"CRITICAL: color_indicators.json missing or invalid at {COLOR_INDICATORS}. "
                f"Cannot classify colors without reference data."
            )

        self.NATURAL_COLOR_INDICATORS = color_indicators_db.get("natural_indicators", [])
        self.ARTIFICIAL_COLOR_INDICATORS = color_indicators_db.get("artificial_indicators", [])
        self.EXPLICIT_NATURAL_DYES = color_indicators_db.get("explicit_natural_dyes", [])
        self.EXPLICIT_ARTIFICIAL_DYES = color_indicators_db.get("explicit_artificial_dyes", [])

        # Track reference data versions for metadata
        self.reference_versions = {}
        db_info = color_indicators_db.get("_metadata", {})
        if db_info:
            version = db_info.get("schema_version", db_info.get("version", "unknown"))
            last_updated = db_info.get("last_updated", "unknown")
            self.reference_versions["color_indicators"] = {
                "version": version,
                "last_updated": last_updated
            }
            logger.info(f"Reference data: color_indicators v{version} (updated: {last_updated})")

        # Initialize enhanced matcher FIRST (needed by hierarchy lookup)
        self.matcher = EnhancedIngredientMatcher()

        # Build skip sets for ingredient classification enforcement
        self._skip_exact, self._skip_normalized = self._build_skip_sets()

        # Read skip matching config (Tier C case-insensitive toggle)
        skip_config = self.ingredient_classification.get("_metadata", {}).get(
            "skip_matching_config", {}
        )
        self._enable_case_insensitive_skip = skip_config.get("enable_case_insensitive", False)
        if self._enable_case_insensitive_skip:
            # Build case-insensitive sets for robust Tier C matching
            self._skip_exact_ci = {s.lower() for s in self._skip_exact}
            self._skip_normalized_ci = {s.lower() for s in self._skip_normalized}
            logger.info("Skip Tier C enabled: case-insensitive matching active for skip lists")
        else:
            self._skip_exact_ci = set()
            self._skip_normalized_ci = set()

        # Build hierarchy lookup for fast classification (uses self.matcher)
        self._hierarchy_lookup = self._build_hierarchy_lookup()

        # Initialize functional grouping handler for transparency scoring
        self.grouping_handler = FunctionalGroupingHandler()

        # Preprocess excluded phrases for fast matching
        self._preprocessed_excluded_labels = {
            self.matcher.preprocess_text(phrase) for phrase in EXCLUDED_LABEL_PHRASES
        }
        self._preprocessed_excluded_nutrition = {
            self.matcher.preprocess_text(fact) for fact in EXCLUDED_NUTRITION_FACTS
        }
        self._preprocessed_blend_header_exact = {
            self.matcher.preprocess_text(name) for name in BLEND_HEADER_EXACT_NAMES
        }
        self._blend_header_high_conf_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in BLEND_HEADER_PATTERNS_HIGH_CONFIDENCE
        ]
        # Strict spec-string filters: these are label descriptors, not ingredients.
        self._spec_string_patterns = [
            re.compile(r"^\s*min\.\s*\d", re.IGNORECASE),
            re.compile(r"^\s*providing\s+\d", re.IGNORECASE),
            re.compile(r"^\s*standardized\s+to\s+contain\s+\d", re.IGNORECASE),
        ]

        # Build enhanced lookup indices
        self._build_enhanced_indices()

        # Build probiotic strain lookup for strain-level matching
        self._probiotic_strain_lookup = self._build_strain_lookup()

        # PERFORMANCE OPTIMIZATION: Cache variation lists to avoid recreating them
        # These lists are created once and reused for all fuzzy matching operations
        self._ingredient_variations_cache = None
        self._form_variations_cache = None
        self._harmful_variations_cache = None
        self._non_harmful_variations_cache = None
        self._allergen_variations_cache = None
        self._banned_variations_cache = None
        self._inactive_variations_cache = None
        self._botanical_variations_cache = None

        # Track unmapped ingredients with more detail
        self.unmapped_ingredients = Counter()
        self.unmapped_details = {}  # Store more context about unmapped ingredients

        # Initialize the enhanced unmapped ingredient tracker for separate active/inactive files
        self.unmapped_tracker = None  # Will be initialized when output_dir is set

        # THREAD-SAFE OPTIMIZATION: Using @lru_cache decorators for thread safety
        # No more manual cache management - Python's lru_cache handles thread safety

        # OPTIMIZATION: Performance tracking for monitoring
        self._cache_stats = {
            "ingredient_calls": 0, "allergen_calls": 0, "harmful_calls": 0,
            "non_harmful_calls": 0, "accuracy_stats": {}
        }

        # OPTIMIZATION: Parallel processing configuration
        self._max_workers = min(8, (os.cpu_count() or 4))  # Adaptive worker count
        self._parallel_threshold = FUZZY_MATCHING_THRESHOLDS["parallel_threshold"]

        # OPTIMIZATION: Fast lookup indices for common operations
        self._fast_exact_lookup = {}  # Combined exact match lookup
        self._common_ingredients_cache = {}  # Cache for most common ingredients
        self._build_fast_lookups()

    def set_output_directory(self, output_dir: Path):
        """Set the output directory and initialize the unmapped tracker"""
        self.unmapped_tracker = UnmappedIngredientTracker(output_dir / "unmapped")
        
    def clear_caches(self):
        """Clear all thread-safe @lru_cache caches"""
        # Clear all @lru_cache decorated methods
        cache_methods = [
            '_enhanced_ingredient_mapping_cached',
            '_enhanced_allergen_check_cached',
            '_enhanced_harmful_check_cached',
            '_enhanced_non_harmful_check_cached'
        ]

        for method_name in cache_methods:
            if hasattr(self, method_name):
                method = getattr(self, method_name)
                if hasattr(method, 'cache_clear'):
                    method.cache_clear()

        # Clear matcher caches
        self.matcher.clear_cache()

        # Clear simple lookup caches
        self._fast_exact_lookup.clear()
        self._common_ingredients_cache.clear()

        logger.info("Cleared all thread-safe LRU caches")

    def validate_database_integrity(self) -> Dict[str, any]:
        """
        Comprehensive database integrity validation
        Returns detailed report of any issues found
        """
        integrity_report = {
            "timestamp": datetime.now().isoformat(),
            "status": "validating",
            "errors": [],
            "warnings": [],
            "statistics": {}
        }

        logger.info("🔍 Starting comprehensive database integrity validation...")

        try:
            # 1. Validate database cross-references
            self._validate_cross_references(integrity_report)

            # 2. Check for orphaned data
            self._check_orphaned_data(integrity_report)

            # 3. Validate required fields
            self._validate_required_fields(integrity_report)

            # 4. Check for data consistency
            self._validate_data_consistency(integrity_report)

            # 5. Generate summary statistics
            self._generate_integrity_statistics(integrity_report)

            # Determine overall status
            if integrity_report["errors"]:
                integrity_report["status"] = "failed"
                logger.error(f"❌ Database integrity validation FAILED with {len(integrity_report['errors'])} errors")
            elif integrity_report["warnings"]:
                integrity_report["status"] = "passed_with_warnings"
                logger.warning(f"⚠️ Database integrity validation PASSED with {len(integrity_report['warnings'])} warnings")
            else:
                integrity_report["status"] = "passed"
                logger.info("✅ Database integrity validation PASSED - all checks successful")

        except Exception as e:
            integrity_report["status"] = "error"
            integrity_report["errors"].append(f"Validation process failed: {str(e)}")
            logger.error(f"💥 Database integrity validation crashed: {e}")

        return integrity_report

    def _validate_cross_references(self, report: Dict):
        """Validate cross-references between databases"""
        logger.info("🔗 Validating database cross-references...")

        # Check if all ingredients in quality map have safety data
        quality_ingredients = set(self.ingredient_alias_lookup.keys())
        allergen_ingredients = set(self.allergen_lookup.keys())
        harmful_ingredients = set(self.harmful_lookup.keys())
        other_ingredients_set = set(self.other_ingredients_lookup.keys())

        # Find ingredients with no safety classification
        no_safety_data = quality_ingredients - (allergen_ingredients | harmful_ingredients | other_ingredients_set)

        if no_safety_data:
            if len(no_safety_data) > 50:  # If too many, this might be expected
                report["warnings"].append(f"{len(no_safety_data)} ingredients in quality database lack safety classification")
            else:
                for ingredient in list(no_safety_data)[:10]:  # Show first 10
                    report["warnings"].append(f"Ingredient '{ingredient}' has no safety classification")

    def _check_orphaned_data(self, report: Dict):
        """Check for orphaned data entries"""
        logger.info("🔍 Checking for orphaned data...")

        # Check for safety entries not in quality database
        quality_ingredients = set(self.ingredient_alias_lookup.keys())

        # Find orphaned allergen entries
        orphaned_allergens = set(self.allergen_lookup.keys()) - quality_ingredients
        if orphaned_allergens:
            report["warnings"].append(f"{len(orphaned_allergens)} allergen entries not found in quality database")

        # Find orphaned harmful entries
        orphaned_harmful = set(self.harmful_lookup.keys()) - quality_ingredients
        if orphaned_harmful:
            report["warnings"].append(f"{len(orphaned_harmful)} harmful additive entries not found in quality database")

    def _validate_required_fields(self, report: Dict):
        """Validate that all database entries have required fields"""
        logger.info("📋 Validating required fields...")

        # Check quality database entries
        for ingredient_name, standard_name in self.ingredient_alias_lookup.items():
            if not standard_name or not standard_name.strip():
                report["errors"].append(f"Quality ingredient '{ingredient_name}' missing standard_name")

        # Check allergen database entries
        for allergen_key, allergen_data in self.allergen_lookup.items():
            if not allergen_data.get("standard_name"):
                report["errors"].append(f"Allergen '{allergen_key}' missing standard_name")
            if not allergen_data.get("severity_level"):
                report["warnings"].append(f"Allergen '{allergen_key}' missing severity_level")

        # Check harmful additive entries
        for harmful_key, harmful_data in self.harmful_lookup.items():
            if not harmful_data.get("category"):
                report["errors"].append(f"Harmful additive '{harmful_key}' missing category")

    def _validate_data_consistency(self, report: Dict):
        """Validate data consistency across databases"""
        logger.info("🔄 Validating data consistency...")

        # Check for duplicate standard names in quality database
        standard_names = {}
        for alias, standard_name in self.ingredient_alias_lookup.items():
            if standard_name in standard_names:
                standard_names[standard_name].append(alias)
            else:
                standard_names[standard_name] = [alias]

        # Report standard names with many aliases (might be okay, but worth checking)
        for standard_name, aliases in standard_names.items():
            if len(aliases) > 20:  # Threshold for review
                report["warnings"].append(f"Standard name '{standard_name}' has {len(aliases)} aliases - verify correctness")

    def _generate_integrity_statistics(self, report: Dict):
        """Generate comprehensive statistics"""
        report["statistics"] = {
            "quality_database": len(self.ingredient_alias_lookup),
            "allergen_database": len(self.allergen_lookup),
            "harmful_database": len(self.harmful_lookup),
            "other_ingredients_database": len(self.other_ingredients_lookup),
            "botanical_database": len(getattr(self, 'botanical_lookup', {})),
            "total_errors": len(report["errors"]),
            "total_warnings": len(report["warnings"])
        }

    def get_cache_stats(self) -> Dict[str, any]:
        """Get performance statistics for thread-safe caching system"""
        cache_info = {}

        # Get cache info from @lru_cache decorated methods
        cache_methods = [
            ('ingredient_mapping', '_enhanced_ingredient_mapping_cached'),
            ('allergen_check', '_enhanced_allergen_check_cached'),
            ('harmful_check', '_enhanced_harmful_check_cached'),
            ('non_harmful_check', '_enhanced_non_harmful_check_cached'),
            ('fuzzy_matching', 'matcher._safe_fuzzy_match_cached'),
            ('text_preprocessing', 'matcher.preprocess_text')
        ]

        for name, method_path in cache_methods:
            try:
                if '.' in method_path:
                    obj, method_name = method_path.split('.', 1)
                    method = getattr(getattr(self, obj), method_name)
                else:
                    method = getattr(self, method_path)

                if hasattr(method, 'cache_info'):
                    info = method.cache_info()
                    cache_info[name] = {
                        "hits": info.hits,
                        "misses": info.misses,
                        "current_size": info.currsize,
                        "max_size": info.maxsize
                    }
            except AttributeError:
                cache_info[name] = {"status": "not_cached"}

        return {
            "cache_performance": cache_info,
            "processing_stats": self._cache_stats.copy()
        }

    def _build_fast_lookups(self):
        """Build optimized lookup indices for common operations"""
        # This will be called after the main indices are built
        self._build_fast_lookups_impl()

    def _build_fast_lookups_impl(self):
        """Build optimized fast lookup indices"""
        logger.info("Building fast lookup indices...")

        # Build combined exact match lookup for all databases
        self._fast_exact_lookup = {}

        # PRIORITY 1: Add BANNED/RECALLED lookups (HIGHEST PRIORITY - safety first)
        # Iterate through ALL sections in banned_recalled database dynamically
        for key, value in self.banned_recalled.items():
            if isinstance(value, list) and len(value) > 0:
                # Check if items have the expected structure for banned substances
                if any(isinstance(item, dict) and 'standard_name' in item for item in value):
                    banned_ingredients = value
                    for banned in banned_ingredients:
                        standard_name = banned.get("standard_name", "")
                        if standard_name:
                            processed_standard = self.matcher.preprocess_text(standard_name)
                            self._fast_exact_lookup[processed_standard] = {
                                "type": "banned",
                                "standard_name": standard_name,
                                "severity": banned.get("severity_level", "critical"),
                                "reason": banned.get("reason", banned.get("recall_reason", "banned")),
                                "mapped": True,
                                "priority": 1
                            }

                            # Add aliases
                            for alias in banned.get("aliases", []) or []:
                                processed_alias = self.matcher.preprocess_text(alias)
                                self._fast_exact_lookup[processed_alias] = {
                                    "type": "banned",
                                    "standard_name": standard_name,
                                    "severity": banned.get("severity_level", "critical"),
                                    "reason": banned.get("reason", banned.get("recall_reason", "banned")),
                                    "mapped": True,
                                    "priority": 1
                                }

        # PRIORITY 2: Add allergen lookups (safety-critical)
        for key, value in self.allergen_lookup.items():
            # Only add if not already present (banned takes priority)
            if key not in self._fast_exact_lookup:
                # SAFETY: Ensure standard_name exists before accessing
                standard_name = value.get("standard_name", "")
                if not standard_name:
                    logger.warning(f"Allergen missing standard_name: {key}")
                    continue
                self._fast_exact_lookup[key] = {
                    "type": "allergen",
                    "allergen_type": standard_name.lower(),
                    "severity": value.get("severity_level", "low"),
                    "mapped": True,
                    "priority": 2
                }

        # PRIORITY 3: Add harmful additive lookups (safety-critical)
        for key, value in self.harmful_lookup.items():
            # Only add if not already present (higher priorities take precedence)
            if key not in self._fast_exact_lookup:
                self._fast_exact_lookup[key] = {
                    "type": "harmful",
                    "category": value.get("category", "other"),
                    "severity_level": value.get("severity_level", "low"),
                    "mapped": True,
                    "priority": 3
                }

        # PRIORITY 4: Add ingredient lookups (active ingredients)
        for key, value in self.ingredient_alias_lookup.items():
            if key not in self._fast_exact_lookup:
                self._fast_exact_lookup[key] = {
                    "type": "ingredient",
                    "standard_name": value,
                    "mapped": True,
                    "priority": 4
                }

        # PRIORITY 5: Add STANDARDIZED BOTANICALS lookups
        standardized_botanicals = self.standardized_botanicals.get("standardized_botanicals", [])
        for std_botanical in standardized_botanicals:
            standard_name = std_botanical.get("standard_name", "")
            if standard_name:
                processed_standard = self.matcher.preprocess_text(standard_name)
                if processed_standard not in self._fast_exact_lookup:
                    self._fast_exact_lookup[processed_standard] = {
                        "type": "standardized_botanical",
                        "standard_name": standard_name,
                        "category": std_botanical.get("category", "botanical"),
                        "standardization": std_botanical.get("standardization", ""),
                        "mapped": True,
                        "priority": 5
                    }

                # Add aliases
                for alias in std_botanical.get("aliases", []) or []:
                    processed_alias = self.matcher.preprocess_text(alias)
                    if processed_alias not in self._fast_exact_lookup:
                        self._fast_exact_lookup[processed_alias] = {
                            "type": "standardized_botanical",
                            "standard_name": standard_name,
                            "category": std_botanical.get("category", "botanical"),
                            "standardization": std_botanical.get("standardization", ""),
                            "mapped": True,
                            "priority": 5
                        }

        # PRIORITY 6: Add BOTANICAL INGREDIENTS lookups
        botanical_ingredients = self.botanical_ingredients.get("botanical_ingredients", [])
        for botanical in botanical_ingredients:
            standard_name = botanical.get("standard_name", "")
            if standard_name:
                processed_standard = self.matcher.preprocess_text(standard_name)
                # Only add if not already present (standardized botanicals have higher priority)
                if processed_standard not in self._fast_exact_lookup:
                    self._fast_exact_lookup[processed_standard] = {
                        "type": "botanical",
                        "standard_name": standard_name,
                        "category": botanical.get("category", "botanical"),
                        "mapped": True,
                        "priority": 6
                    }

                # Add aliases
                for alias in botanical.get("aliases", []) or []:
                    processed_alias = self.matcher.preprocess_text(alias)
                    if processed_alias not in self._fast_exact_lookup:
                        self._fast_exact_lookup[processed_alias] = {
                            "type": "botanical",
                            "standard_name": standard_name,
                            "category": botanical.get("category", "botanical"),
                            "mapped": True,
                            "priority": 6
                        }

        # PRIORITY 7: Add OTHER INGREDIENTS lookups (safe additives/excipients)
        for key, value in self.other_ingredients_lookup.items():
            # Only add if not already present (higher priorities take precedence)
            if key not in self._fast_exact_lookup:
                self._fast_exact_lookup[key] = {
                    "type": "other_ingredient",
                    "standard_name": value.get("standard_name", key),
                    "category": value.get("category", "other"),
                    "additive_type": value.get("additive_type", "unknown"),
                    "clean_label_score": value.get("clean_label_score", 7),
                    "mapped": True,
                    "priority": 7
                }

        # PRIORITY 8: Add PROPRIETARY BLENDS lookups
        proprietary_blend_concerns = self.proprietary_blends.get("proprietary_blend_concerns", [])
        for concern in proprietary_blend_concerns:
            standard_name = concern.get("standard_name", "")
            if standard_name:
                processed_standard = self.matcher.preprocess_text(standard_name)
                if processed_standard not in self._fast_exact_lookup:
                    self._fast_exact_lookup[processed_standard] = {
                        "type": "proprietary_blend",
                        "standard_name": standard_name,
                        "category": concern.get("category", "blend"),
                        "mapped": True,
                        "priority": 8
                    }

                # Add red flag terms as aliases
                for red_flag_term in concern.get("red_flag_terms", []) or []:
                    processed_term = self.matcher.preprocess_text(red_flag_term)
                    if processed_term not in self._fast_exact_lookup:
                        self._fast_exact_lookup[processed_term] = {
                            "type": "proprietary_blend",
                            "standard_name": standard_name,
                            "category": concern.get("category", "blend"),
                            "mapped": True,
                            "priority": 8
                        }

        # PRIORITY 9: Add OTHER INGREDIENTS (FDA terminology) lookups (lowest priority - catch-all)
        other_ingredients_list = self.other_ingredients.get("other_ingredients", [])
        for other_ing in other_ingredients_list:
            standard_name = other_ing.get("standard_name", "")
            if standard_name:
                processed_standard = self.matcher.preprocess_text(standard_name)
                # Only add if not already present (all higher priorities take precedence)
                if processed_standard not in self._fast_exact_lookup:
                    self._fast_exact_lookup[processed_standard] = {
                        "type": "other_ingredient",
                        "standard_name": standard_name,
                        "category": other_ing.get("category", "other"),
                        "is_additive": other_ing.get("is_additive", False),
                        "mapped": True,
                        "priority": 9
                    }

                # Add aliases
                for alias in other_ing.get("aliases", []) or []:
                    processed_alias = self.matcher.preprocess_text(alias)
                    if processed_alias not in self._fast_exact_lookup:
                        self._fast_exact_lookup[processed_alias] = {
                            "type": "other_ingredient",
                            "standard_name": standard_name,
                            "category": other_ing.get("category", "other"),
                            "is_additive": other_ing.get("is_additive", False),
                            "mapped": True,
                            "priority": 9
                        }

        # PRIORITY 10: Add ABSORPTION ENHANCERS lookups
        absorption_enhancers_list = self.absorption_enhancers.get("absorption_enhancers", [])
        for enhancer in absorption_enhancers_list:
            enhancer_name = enhancer.get("standard_name", "")
            if enhancer_name:
                processed_name = self.matcher.preprocess_text(enhancer_name)
                if processed_name not in self._fast_exact_lookup:
                    self._fast_exact_lookup[processed_name] = {
                        "type": "absorption_enhancer",
                        "standard_name": enhancer_name,
                        "category": "absorption",
                        "mapped": True,
                        "priority": 10
                    }
                # Add aliases
                for alias in enhancer.get("aliases", []) or []:
                    processed_alias = self.matcher.preprocess_text(alias)
                    if processed_alias not in self._fast_exact_lookup:
                        self._fast_exact_lookup[processed_alias] = {
                            "type": "absorption_enhancer",
                            "standard_name": enhancer_name,
                            "category": "absorption",
                            "mapped": True,
                            "priority": 10
                        }

        # PRIORITY 11: Add ENHANCED DELIVERY lookups
        for delivery_key, delivery_data in self.enhanced_delivery.items():
            # Skip metadata keys (like _comment, _metadata, etc.)
            if delivery_key.startswith("_") or not isinstance(delivery_data, dict):
                continue
            delivery_name = delivery_key.replace("_", " ").title()  # Convert key to readable name
            processed_name = self.matcher.preprocess_text(delivery_key)
            if processed_name not in self._fast_exact_lookup:
                self._fast_exact_lookup[processed_name] = {
                    "type": "enhanced_delivery",
                    "standard_name": delivery_name,
                    "category": delivery_data.get("category", "delivery"),
                    "points": delivery_data.get("points", 0),
                    "mapped": True,
                    "priority": 11
                }

        logger.info(f"Built comprehensive fast lookup index with {len(self._fast_exact_lookup)} entries")

        # Log breakdown by type for debugging
        type_counts = {}
        for entry in self._fast_exact_lookup.values():
            entry_type = entry.get("type", "unknown")
            type_counts[entry_type] = type_counts.get(entry_type, 0) + 1

        for entry_type, count in sorted(type_counts.items()):
            logger.info(f"  - {entry_type}: {count} entries")

    def _fast_ingredient_lookup(self, name: str) -> Dict[str, Any]:
        """Fast combined lookup for ingredient, harmful, and allergen data"""
        processed_name = self.matcher.preprocess_text(name)

        # Check fast exact lookup first
        if processed_name in self._fast_exact_lookup:
            return self._fast_exact_lookup[processed_name]

        # Return default "not found" result
        return {
            "type": "none",
            "mapped": False
        }

    def _process_ingredient_parallel(self, ingredient_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single ingredient for parallel execution"""
        name = ingredient_data.get("name", "")

        # Extract forms with prefix for context-aware mapping (e.g., "from Fruits" for natural colors)
        forms_data = ingredient_data.get("forms", [])
        forms = []
        if forms_data and isinstance(forms_data, list):
            for form_dict in forms_data:
                if isinstance(form_dict, dict):
                    prefix = (form_dict.get("prefix", "") or "").strip()
                    form_name = (form_dict.get("name", "") or "").strip()
                    # Include prefix for context (e.g., "from Fruits" helps distinguish natural colors)
                    full_form = f"{prefix} {form_name}".strip() if prefix else form_name
                    if full_form:
                        forms.append(full_form)
                elif form_dict:
                    forms.append(str(form_dict))

        # Enhanced mapping
        standard_name, mapped, _ = self._enhanced_ingredient_mapping(name, forms)

        # Enhanced checks
        allergen_info = self._enhanced_allergen_check(name, forms)
        harmful_info = self._enhanced_harmful_check(name)

        # Check if proprietary blend
        is_proprietary = self._is_proprietary_blend_name(name)

        # Calculate final mapping status
        is_mapped = (mapped or
                    harmful_info["category"] != "none" or
                    allergen_info["is_allergen"] or
                    is_proprietary)

        # Track unmapped ingredients only if not found in any database
        # DATA INTEGRITY FIX: Filter out label phrases and nutrition facts
        # This prevents "None", "Contains < 2% of", etc. from appearing in unmapped list
        if not is_mapped and not self._is_nutrition_fact(name):
            processed_name = self.matcher.preprocess_text(name)
            # Thread-safe tracking (Counter is thread-safe for basic operations)
            self.unmapped_ingredients[name] += 1
            self.unmapped_details[name] = {
                "processed_name": processed_name,
                "forms": forms,
                "variations_tried": self.matcher.generate_variations(processed_name),
                "is_active": True  # This method is for active ingredients from the context
            }

        # Check if this ingredient is an additive (add metadata flag for enrichment phase)
        processed_name = self.matcher.preprocess_text(name)
        is_additive = False
        additive_type = None
        if processed_name in self.other_ingredients_lookup:
            additive_data = self.other_ingredients_lookup[processed_name]
            is_additive = additive_data.get("is_additive", False)
            if is_additive:
                additive_type = additive_data.get("additive_type")

        # CLEANING ONLY - NO ENRICHMENT FIELDS
        result = {
            "order": ingredient_data.get("order", 0),
            "name": name,
            "standardName": standard_name,
            "ingredientGroup": ingredient_data.get("ingredientGroup"),  # PRESERVE from DSLD (even if wrong)
            "mapped": is_mapped
        }

        # Add additive metadata flag (for enrichment phase to use)
        if is_additive:
            result["isAdditive"] = True
            if additive_type:
                result["additiveType"] = additive_type

        return result

    @property
    def ingredient_variations(self) -> List[str]:
        """Cached ingredient variations list for fuzzy matching"""
        if self._ingredient_variations_cache is None:
            self._ingredient_variations_cache = list(self.ingredient_alias_lookup.keys())
        return self._ingredient_variations_cache

    @property
    def form_variations(self) -> List[str]:
        """Cached form variations list for fuzzy matching"""
        if self._form_variations_cache is None:
            self._form_variations_cache = list(self.ingredient_forms_lookup.keys())
        return self._form_variations_cache

    @property
    def harmful_variations(self) -> List[str]:
        """Cached harmful variations list for fuzzy matching"""
        if self._harmful_variations_cache is None:
            self._harmful_variations_cache = list(self.harmful_lookup.keys())
        return self._harmful_variations_cache

    @property
    def non_harmful_variations(self) -> List[str]:
        """Cached non-harmful additive variations list for fuzzy matching"""
        if self._non_harmful_variations_cache is None:
            self._non_harmful_variations_cache = list(self.other_ingredients_lookup.keys())
        return self._non_harmful_variations_cache

    @property
    def allergen_variations(self) -> List[str]:
        """Cached allergen variations list for fuzzy matching"""
        if not hasattr(self, '_allergen_variations_cache'):
            self._allergen_variations_cache = None
        if self._allergen_variations_cache is None:
            self._allergen_variations_cache = list(self.allergen_lookup.keys())
        return self._allergen_variations_cache

    @property
    def banned_variations(self) -> List[str]:
        """Cached banned variations list for fuzzy matching"""
        if self._banned_variations_cache is None:
            all_banned_terms = []
            # Get all banned substances from all categories
            for category, items in self.banned_recalled.items():
                if isinstance(items, list):
                    for banned in items:
                        all_banned_terms.append(banned.get("standard_name", "").lower())
                        all_banned_terms.extend([alias.lower() for alias in banned.get("aliases", []) or []])
            self._banned_variations_cache = [term for term in all_banned_terms if term]
        return self._banned_variations_cache

    @property
    def inactive_variations(self) -> List[str]:
        """Cached inactive variations list for fuzzy matching"""
        if self._inactive_variations_cache is None:
            all_inactive_terms = []
            inactive_ingredients = self.other_ingredients.get("other_ingredients", [])
            for inactive in inactive_ingredients:
                all_inactive_terms.append(inactive.get("standard_name", "").lower())
                all_inactive_terms.extend([alias.lower() for alias in inactive.get("aliases", []) or []])
            self._inactive_variations_cache = [term for term in all_inactive_terms if term]
        return self._inactive_variations_cache

    @property
    def botanical_variations(self) -> List[str]:
        """Cached botanical variations list for fuzzy matching"""
        if self._botanical_variations_cache is None:
            all_botanical_terms = []
            botanical_ingredients = self.botanical_ingredients.get("botanical_ingredients", [])
            for botanical in botanical_ingredients:
                all_botanical_terms.append(botanical.get("standard_name", "").lower())
                all_botanical_terms.extend([alias.lower() for alias in botanical.get("aliases", []) or []])
            self._botanical_variations_cache = [term for term in all_botanical_terms if term]
        return self._botanical_variations_cache

    def _load_json(self, filepath: Path) -> Dict:
        """Load JSON reference file with error handling"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {filepath}: {str(e)}")
            return {}

    def _normalize_for_skip(self, name: str) -> str:
        """
        Tier B normalization for skip matching (locked down, no scope creep).

        Delegates to normalization module for consistent behavior across pipeline.

        Applies ONLY these operations:
        1. Unicode normalize to NFC
        2. Trim leading/trailing whitespace
        3. Collapse internal whitespace to single ASCII space

        Does NOT apply: punctuation stripping, lowercasing, qualifier removal.
        """
        return norm_module.normalize_for_skip_matching(name)

    def _build_skip_sets(self) -> Tuple[Set[str], Set[str]]:
        """
        Build skip sets from ingredient_classification.json.

        Returns:
            Tuple of (skip_exact, skip_normalized) sets

        Collects items to skip:
        - All items from categories with scoring_rule: "skip_all"
        - All "summaries" from ALL categories (summaries are aggregate lines, not real ingredients)
        """
        skip_exact = set()
        skip_normalized = set()

        # Add items from explicit skip_exact list
        for item in self.ingredient_classification.get("skip_exact", []):
            skip_exact.add(item)
            skip_normalized.add(self._normalize_for_skip(item))

        # Iterate over classifications dict (not top-level keys)
        classifications = self.ingredient_classification.get("classifications", {})
        for category, data in classifications.items():
            if category.startswith("_"):  # Skip metadata
                continue
            if not isinstance(data, dict):  # Safety check
                continue

            scoring_rule = data.get("scoring_rule", "score_components_only")

            # For skip_all categories, add ALL items (summaries, sources, etc.)
            if scoring_rule == "skip_all":
                for item in data.get("summaries", []):
                    skip_exact.add(item)
                    skip_normalized.add(self._normalize_for_skip(item))
                for item in data.get("sources", []):
                    skip_exact.add(item)
                    skip_normalized.add(self._normalize_for_skip(item))
            else:
                # For other categories, only add summaries (aggregate lines)
                for summary in data.get("summaries", []):
                    skip_exact.add(summary)
                    skip_normalized.add(self._normalize_for_skip(summary))

        logger.info(f"Built skip sets: {len(skip_exact)} exact, {len(skip_normalized)} normalized")
        return skip_exact, skip_normalized

    def _extract_branded_token(self, name: str) -> Optional[str]:
        """
        Extract branded ingredient token from compound names.

        For inputs like "KSM-66 Ashwagandha Root Extract", extracts "KSM-66"
        as the raw_source_text for quality map matching.

        This enables correct matching to branded forms (e.g., "KSM-66 ashwagandha")
        instead of generic forms (e.g., "ashwagandha (unspecified)").

        Returns:
            The canonical branded token if found, else None.
        """
        if not name:
            return None

        # Normalize for matching (lowercase, strip)
        name_lower = name.lower().strip()

        # Check for each branded token in the name
        for token_lower, canonical_form in BRANDED_INGREDIENT_TOKENS.items():
            # Use word boundary matching to avoid partial matches
            # e.g., "ksm-66" should match "KSM-66 Ashwagandha" but not "aksm-66z"
            pattern = r'\b' + re.escape(token_lower) + r'\b'
            if re.search(pattern, name_lower):
                logger.debug(f"Extracted branded token '{canonical_form}' from '{name}'")
                return canonical_form

        return None

    def _should_skip_ingredient(self, name: str) -> bool:
        """
        Check if an ingredient should be skipped entirely.

        Applies tiered matching (Tier C controlled by config):
        - Tier A: Strict exact match against skip_exact
        - Tier B: Normalized match (NFC, strip, collapse whitespace)
        - Tier C: Case-insensitive match (enabled via skip_matching_config)

        Returns True if ingredient should be dropped from output.
        """
        if not name:
            return True  # Empty/None names are always skipped

        # Tier A: Exact match
        if name in self._skip_exact:
            return True

        # Tier B: Normalized match (preserves case)
        normalized = self._normalize_for_skip(name)
        if normalized in self._skip_normalized:
            return True

        # Always skip known exact blend headers (normalized/preprocessed).
        processed_name = self.matcher.preprocess_text(name)
        if processed_name in self._preprocessed_blend_header_exact:
            return True

        # High-confidence blend header patterns (safe to skip even with dose present).
        for pattern in self._blend_header_high_conf_patterns:
            if pattern.search(name):
                return True

        # Skip dosage/specification fragments that are not ingredient identities.
        for pattern in self._spec_string_patterns:
            if pattern.search(name):
                return True

        # Tier C: Case-insensitive match (only if enabled in config)
        # Uses dedicated lowercased sets for robust matching regardless of JSON casing
        if self._enable_case_insensitive_skip:
            name_lower = name.lower()
            if name_lower in self._skip_exact_ci:
                return True

            normalized_lower = normalized.lower()
            if normalized_lower in self._skip_normalized_ci:
                return True

        return False

    def _build_hierarchy_lookup(self) -> Dict[str, Dict[str, str]]:
        """
        Build fast lookup dict for hierarchy classification.
        Returns: {normalized_name: {"type": "source"|"summary"|"component", "category": "omega_fatty_acids"|...}}

        INVARIANT: self.matcher must be initialized before this method is called.
        This is guaranteed by __init__ order (matcher created before hierarchy lookup).
        """
        # P1: Removed dead hasattr fallbacks - matcher is always initialized before this
        if self.matcher is None:
            raise RuntimeError("Matcher must be initialized before _build_hierarchy_lookup")

        lookup = {}

        # Iterate over classifications dict (not top-level keys)
        classifications = self.ingredient_classification.get("classifications", {})
        for category, data in classifications.items():
            if category.startswith("_"):  # Skip metadata
                continue
            if not isinstance(data, dict):  # Safety check
                continue

            scoring_rule = data.get("scoring_rule", "score_components_only")

            # Index sources
            for source in data.get("sources", []):
                normalized = self.matcher.preprocess_text(source)
                lookup[normalized] = {
                    "type": "source", "category": category, "scoring_rule": scoring_rule
                }

            # Index summaries
            for summary in data.get("summaries", []):
                normalized = self.matcher.preprocess_text(summary)
                lookup[normalized] = {
                    "type": "summary", "category": category, "scoring_rule": scoring_rule
                }

            # Index components (can be dict or list)
            components = data.get("components", {})
            if isinstance(components, dict):
                for sub_cat, comp_list in components.items():
                    for comp in comp_list:
                        normalized = self.matcher.preprocess_text(comp)
                        lookup[normalized] = {
                            "type": "component", "category": category,
                            "sub_category": sub_cat, "scoring_rule": scoring_rule
                        }
            elif isinstance(components, list):
                for comp in components:
                    normalized = self.matcher.preprocess_text(comp)
                    lookup[normalized] = {
                        "type": "component", "category": category, "scoring_rule": scoring_rule
                    }

        logger.info("Built hierarchy lookup with %d entries", len(lookup))
        return lookup

    def _classify_hierarchy_type(self, name: str) -> Optional[Dict[str, str]]:
        """
        Classify an ingredient's hierarchy type.
        Returns: {"type": "source"|"summary"|"component", "category": str, "scoring_rule": str} or None
        """
        if not name:
            return None

        normalized = self.matcher.preprocess_text(name)

        # Direct lookup first
        if normalized in self._hierarchy_lookup:
            return self._hierarchy_lookup[normalized]

        # Partial match for patterns like "Total Omega-3 Fatty Acids" -> matches "total omega-3"
        for key, value in self._hierarchy_lookup.items():
            if key in normalized or normalized in key:
                return value

        return None

    def _build_strain_lookup(self) -> Dict[str, str]:
        """Build a normalized lookup from probiotic strain aliases
        to strain standard_name for strain-level matching bypass."""
        lookup: Dict[str, str] = {}
        strains = self.clinical_strains_db.get(
            'clinically_relevant_strains', []
        )
        for strain in strains:
            std = strain.get('standard_name', '')
            if not std:
                continue
            # Index the standard_name itself
            key = self.matcher.preprocess_text(std)
            if key:
                lookup[key] = std
            # Index all aliases
            for alias in strain.get('aliases', []):
                key = self.matcher.preprocess_text(alias)
                if key and key not in lookup:
                    lookup[key] = std
        if lookup:
            logger.info(
                "Probiotic strain lookup: %d keys for %d strains",
                len(lookup), len(strains),
            )
        return lookup

    def _match_probiotic_strain(
        self, processed_name: str
    ) -> Optional[str]:
        """Match a preprocessed ingredient name against the
        probiotic strain lookup. Uses exact match first, then
        longest-alias substring match as fallback."""
        if not processed_name:
            return None
        # Pass 1: exact match
        if processed_name in self._probiotic_strain_lookup:
            return self._probiotic_strain_lookup[processed_name]
        # Pass 2: find the longest alias that is a substring
        # of the input (minimum 6 chars to avoid false positives
        # like "k12" matching "mk12-something")
        best_alias = ""
        best_name = None
        for alias, std_name in self._probiotic_strain_lookup.items():
            if len(alias) < 6:
                continue
            if alias in processed_name and len(alias) > len(best_alias):
                best_alias = alias
                best_name = std_name
        return best_name

    def _build_enhanced_indices(self):
        """Build comprehensive lookup indices with variations - fixed to prevent overwrites"""
        logger.info("Building enhanced ingredient lookup indices...")
        
        # Build ingredient alias lookup with variations
        self.ingredient_alias_lookup = {}
        self.ingredient_forms_lookup = {}
        
        # NEW: Store full form data for disambiguation
        self.ingredient_context_lookup = {}
        
        # Track conflicts to debug mapping issues
        conflicts = {}

        for vitamin_name, vitamin_data in self.ingredient_map.items():
            # Skip metadata keys (like _metadata, _comment, etc.)
            if vitamin_name.startswith("_") or not isinstance(vitamin_data, dict):
                continue
            standard_name = vitamin_data.get("standard_name", vitamin_name)
            
            # Add standard name and its variations FIRST (prioritize exact matches)
            standard_variations = self.matcher.generate_variations(
                self.matcher.preprocess_text(standard_name)
            )
            for variation in standard_variations:
                if variation in self.ingredient_alias_lookup:
                    existing = self.ingredient_alias_lookup[variation]
                    if existing != standard_name:
                        conflicts[variation] = f"{existing} -> {standard_name}"
                        # Keep the first mapping, don't overwrite
                        continue
                self.ingredient_alias_lookup[variation] = standard_name
            
            # Add vitamin name (key) and its variations
            name_variations = self.matcher.generate_variations(
                self.matcher.preprocess_text(vitamin_name)
            )
            for variation in name_variations:
                if variation in self.ingredient_alias_lookup:
                    existing = self.ingredient_alias_lookup[variation]
                    if existing != standard_name:
                        conflicts[variation] = f"{existing} -> {standard_name}"
                        # Keep the first mapping, don't overwrite
                        continue
                self.ingredient_alias_lookup[variation] = standard_name
            
            # Add all form aliases and their variations
            for form_name, form_data in (vitamin_data.get("forms", {}) or {}).items():
                form_variations = self.matcher.generate_variations(
                    self.matcher.preprocess_text(form_name)
                )
                for variation in form_variations:
                    if variation in self.ingredient_alias_lookup:
                        existing = self.ingredient_alias_lookup[variation]
                        if existing != standard_name:
                            conflicts[variation] = f"{existing} -> {standard_name}"
                            # Keep the first mapping, don't overwrite
                            continue
                    self.ingredient_alias_lookup[variation] = standard_name
                    self.ingredient_forms_lookup[variation] = form_name
                
                # Add aliases for this form
                for alias in form_data.get("aliases", []) or []:
                    alias_variations = self.matcher.generate_variations(
                        self.matcher.preprocess_text(alias)
                    )
                    for variation in alias_variations:
                        if variation in self.ingredient_alias_lookup:
                            existing = self.ingredient_alias_lookup[variation]
                            if existing != standard_name:
                                conflicts[variation] = f"{existing} -> {standard_name}"
                                # Keep the first mapping, don't overwrite
                                continue
                        self.ingredient_alias_lookup[variation] = standard_name
                        self.ingredient_forms_lookup[variation] = form_name
                        
                        # Store full form data for disambiguation
                        self.ingredient_context_lookup[variation] = {
                            'standard_name': standard_name,
                            'form_name': form_name,
                            'form_data': form_data
                        }

            # CRITICAL FIX: Add TOP-LEVEL aliases (aliases on the ingredient entry itself, not inside forms)
            # These are used for ingredient variants like "Iron, Microencapsulated" -> "Iron"
            for alias in vitamin_data.get("aliases", []) or []:
                alias_variations = self.matcher.generate_variations(
                    self.matcher.preprocess_text(alias)
                )
                for variation in alias_variations:
                    if variation in self.ingredient_alias_lookup:
                        existing = self.ingredient_alias_lookup[variation]
                        if existing != standard_name:
                            conflicts[variation] = f"{existing} -> {standard_name}"
                            # Keep the first mapping, don't overwrite
                            continue
                    self.ingredient_alias_lookup[variation] = standard_name

        # Log conflicts for debugging (reduced verbosity)
        if conflicts:
            logger.debug(f"Found {len(conflicts)} mapping conflicts - keeping first mappings")
            for variation, conflict in list(conflicts.items())[:5]:  # Show first 5
                logger.debug(f"Conflict: '{variation}' {conflict}")
        
        # Build enhanced allergen lookup
        self.allergen_lookup = {}

        # Support both "allergens" (current schema) and "common_allergens" (legacy schema)
        allergen_list = self.allergens_db.get("allergens", []) or self.allergens_db.get("common_allergens", []) or []
        for allergen in allergen_list:
            standard_name = allergen["standard_name"]

            # Add standard name variations
            name_variations = self.matcher.generate_variations(
                self.matcher.preprocess_text(standard_name)
            )
            for variation in name_variations:
                self.allergen_lookup[variation] = allergen

            # Add alias variations
            for alias in allergen.get("aliases", []) or []:
                alias_variations = self.matcher.generate_variations(
                    self.matcher.preprocess_text(alias)
                )
                for variation in alias_variations:
                    self.allergen_lookup[variation] = allergen
        
        # Build enhanced harmful additive lookup
        self.harmful_lookup = {}

        for additive in self.harmful_additives.get("harmful_additives", []) or []:
            standard_name = additive["standard_name"]

            # Add standard name variations
            name_variations = self.matcher.generate_variations(
                self.matcher.preprocess_text(standard_name)
            )
            for variation in name_variations:
                self.harmful_lookup[variation] = additive

            # Add alias variations to harmful_lookup ONLY (not main ingredient lookup)
            # ARCHITECTURAL FIX: Keep harmful additive detection separate from ingredient identity mapping
            # This prevents "synthetic colors" alias from polluting the main lookup with variations like "colors"
            for alias in additive.get("aliases", []) or []:
                alias_variations = self.matcher.generate_variations(
                    self.matcher.preprocess_text(alias)
                )
                for variation in alias_variations:
                    self.harmful_lookup[variation] = additive
                # NOTE: Removed addition to ingredient_alias_lookup to prevent false standardName mappings
                # Harmful additive classification should happen in enrichment, not cleaning
        
        # Build enhanced other ingredients lookup (safe additives/excipients - FDA "Other Ingredients")
        self.other_ingredients_lookup = {}
        for other_ing in self.other_ingredients.get("other_ingredients", []) or []:
            standard_name = other_ing["standard_name"]
            # Add standard name variations
            name_variations = self.matcher.generate_variations(
                self.matcher.preprocess_text(standard_name)
            )
            for variation in name_variations:
                self.other_ingredients_lookup[variation] = other_ing

            # Add alias variations
            for alias in other_ing.get("aliases", []) or []:
                alias_variations = self.matcher.generate_variations(
                    self.matcher.preprocess_text(alias)
                )
                for variation in alias_variations:
                    self.other_ingredients_lookup[variation] = other_ing

                # Add to main ingredient lookup to prevent fuzzy conflicts
                processed_alias = self.matcher.preprocess_text(alias)
                if processed_alias not in self.ingredient_alias_lookup:
                    self.ingredient_alias_lookup[processed_alias] = alias

        # CRITICAL FIX: Add other ingredients to main lookup to prevent fuzzy conflicts
        for ingredient in self.other_ingredients.get("other_ingredients", []) or []:
            standard_name = ingredient.get("standard_name", "")
            if standard_name:
                processed_standard = self.matcher.preprocess_text(standard_name)
                if processed_standard not in self.ingredient_alias_lookup:
                    self.ingredient_alias_lookup[processed_standard] = standard_name
                    
            for alias in ingredient.get("aliases", []) or []:
                processed_alias = self.matcher.preprocess_text(alias)
                if processed_alias not in self.ingredient_alias_lookup:
                    self.ingredient_alias_lookup[processed_alias] = alias

        logger.info(f"Built lookup indices with {len(self.ingredient_alias_lookup)} ingredient variations")
        logger.info(f"Built allergen index with {len(self.allergen_lookup)} variations")
        logger.info(f"Built harmful additive index with {len(self.harmful_lookup)} variations")
        logger.info(f"Built other ingredients index with {len(self.other_ingredients_lookup)} variations")

        # Build optimized fast lookups
        self._build_fast_lookups_impl()
    
    def _enhanced_ingredient_mapping(self, name: str, forms: List[str] = None) -> Tuple[str, bool, List[str]]:
        """
        Enhanced ingredient mapping with comprehensive validation and thread-safe caching
        """
        # SAFETY: Comprehensive input validation
        validated_name = self.matcher.validate_input(name, "ingredient_name")
        if not validated_name:
            return "", False, []

        # SAFETY: Validate and clean forms list
        validated_forms = []
        if forms:
            # Handle case where forms might be a dict instead of list
            if isinstance(forms, dict):
                # Extract values from dict or convert to list based on content
                if 'forms' in forms:
                    forms = forms['forms']
                else:
                    forms = list(forms.values()) if forms.values() else []

            # Ensure forms is iterable
            if not hasattr(forms, '__iter__') or isinstance(forms, str):
                forms = [forms] if forms else []

            for form in forms:
                if isinstance(form, dict):
                    # If form is a dict, try to extract a name or convert to string
                    form_str = form.get('name', '') or str(form)
                    validated_form = self.matcher.validate_input(form_str, "ingredient_form")
                    if validated_form:
                        validated_forms.append(validated_form)
                elif isinstance(form, (str, int, float)):  # Only process string-like values
                    validated_form = self.matcher.validate_input(str(form), "ingredient_form")
                    if validated_form:  # Only add non-empty forms
                        validated_forms.append(validated_form)

        self._cache_stats["ingredient_calls"] += 1

        # Use thread-safe @lru_cache - convert list to tuple for hashability
        forms_tuple = tuple(sorted(validated_forms)) if validated_forms else ()
        return self._enhanced_ingredient_mapping_cached(validated_name, forms_tuple)

    @functools.lru_cache(maxsize=2000)  # PERFORMANCE: Reduced from 10000 to prevent memory bloat
    def _enhanced_ingredient_mapping_cached(self, name: str, forms_tuple: tuple) -> Tuple[str, bool, List[str]]:
        """Thread-safe cached ingredient mapping"""
        forms = list(forms_tuple) if forms_tuple else []
        return self._perform_ingredient_mapping(name, forms)

    def _perform_ingredient_mapping(self, name: str, forms: List[str] = None) -> Tuple[str, bool, List[str]]:
        """Perform the actual ingredient mapping logic"""
        forms = forms or []
        name_lower = name.lower().strip()

        # P0.5 PRIORITY 1: Check EXPLICIT DYES first (deterministic, bypasses indicator heuristics)
        # Pre-lowercase for matching
        explicit_artificial_lower = [d.lower() for d in self.EXPLICIT_ARTIFICIAL_DYES]
        explicit_natural_lower = [d.lower() for d in self.EXPLICIT_NATURAL_DYES]

        # Check if ingredient name matches an explicit artificial dye
        is_explicit_artificial = any(dye in name_lower for dye in explicit_artificial_lower)
        if is_explicit_artificial:
            matched_dye = next(
                (d for d in self.EXPLICIT_ARTIFICIAL_DYES if d.lower() in name_lower),
                None
            )
            logger.debug(f"Explicit artificial dye match: '{name}' -> 'artificial colors' (matched: {matched_dye})")
            return "artificial colors", True, forms

        # Check if ingredient name matches an explicit natural dye
        is_explicit_natural = any(dye in name_lower for dye in explicit_natural_lower)
        if is_explicit_natural:
            matched_dye = next(
                (d for d in self.EXPLICIT_NATURAL_DYES if d.lower() in name_lower),
                None
            )
            logger.debug(f"Explicit natural dye match: '{name}' -> 'natural colors' (matched: {matched_dye})")
            return "natural colors", True, forms

        # P0.5 PRIORITY 2: Indicator-based mapping for ambiguous "Colors" terms
        if name_lower in ['colors', 'color', 'coloring', 'colorings', 'color added', 'colors added']:
            # Build context from forms
            forms_text = ' '.join(str(f).lower() for f in forms) if forms else ''

            # Check for indicators
            matched_natural = next((ind for ind in self.NATURAL_COLOR_INDICATORS if ind in forms_text), None)
            matched_artificial = next((ind for ind in self.ARTIFICIAL_COLOR_INDICATORS if ind in forms_text), None)

            if matched_natural and not matched_artificial:
                logger.debug(f"Colors indicator match: '{name}' with forms '{forms_text}' -> natural colors (matched: {matched_natural})")
                return "natural colors", True, forms
            elif matched_artificial and not matched_natural:
                logger.debug(f"Colors indicator match: '{name}' with forms '{forms_text}' -> artificial colors (matched: {matched_artificial})")
                return "artificial colors", True, forms
            elif not matched_natural and not matched_artificial:
                # Ambiguous - default to generic "colors" without synthetic/artificial label
                logger.debug(f"Colors: '{name}' with no context -> colors (unspecified)")
                return "colors (unspecified)", True, forms
            # If both indicators present, fall through to normal mapping

        # Preprocess the input name
        processed_name = self.matcher.preprocess_text(name)

        # PROBIOTIC STRAIN BYPASS: Check clinically_relevant_strains
        # BEFORE standard alias lookup to prevent strain-specific names
        # from being generalized to "Probiotics" by the IQM catchall.
        strain_name = self._match_probiotic_strain(processed_name)
        if strain_name:
            logger.info(
                "Probiotic strain match: '%s' -> '%s'",
                name, strain_name,
            )
            return strain_name, True, forms or []

        # SAFETY FIRST: Try critical exact matching for short aliases (B1, D3, K2, etc.)
        critical_match = self.matcher.exact_match_critical_aliases(name, list(self.ingredient_alias_lookup.keys()))
        if critical_match:
            mapped_name = self.ingredient_alias_lookup[critical_match]
            logger.info(f"CRITICAL vitamin/mineral exact match: '{name}' -> '{mapped_name}'")
            return mapped_name, True, forms or []

        # Debug logging for specific ingredients
        if name in ["Molybdenum", "Choline", "Alpha-Lipoic Acid"]:
            logger.debug(f"Mapping '{name}' -> processed: '{processed_name}'")
            logger.debug(f"Is '{processed_name}' in lookup? {processed_name in self.ingredient_alias_lookup}")

        # Try exact match
        if processed_name in self.ingredient_alias_lookup:
            # Check for disambiguation if needed
            if processed_name in self.ingredient_context_lookup:
                context_data = self.ingredient_context_lookup[processed_name]
                form_data = context_data.get('form_data', {})
                
                # If this ingredient has context rules, use disambiguation
                if form_data.get('context_include') or form_data.get('context_exclude'):
                    # Use the original full text as context for disambiguation
                    context_text = name.lower()
                    if not self.matcher.disambiguate_ingredient_match(context_text, form_data):
                        # Disambiguation failed, try fuzzy matching instead
                        pass
                    else:
                        mapped_name = self.ingredient_alias_lookup[processed_name]
                        mapped_forms = []
                        
                        # Try to find specific forms
                        for form in forms:
                            processed_form = self.matcher.preprocess_text(form)
                            if processed_form in self.ingredient_forms_lookup:
                                mapped_forms.append(self.ingredient_forms_lookup[processed_form])
                        
                        return mapped_name, True, mapped_forms or forms
                else:
                    # No disambiguation needed
                    mapped_name = self.ingredient_alias_lookup[processed_name]
                    mapped_forms = []
                    
                    # Try to find specific forms
                    for form in forms:
                        processed_form = self.matcher.preprocess_text(form)
                        if processed_form in self.ingredient_forms_lookup:
                            mapped_forms.append(self.ingredient_forms_lookup[processed_form])
                    
                    return mapped_name, True, mapped_forms or forms
            else:
                # No context data available, proceed normally
                mapped_name = self.ingredient_alias_lookup[processed_name]
                mapped_forms = []
                
                # Try to find specific forms
                for form in forms:
                    processed_form = self.matcher.preprocess_text(form)
                    if processed_form in self.ingredient_forms_lookup:
                        mapped_forms.append(self.ingredient_forms_lookup[processed_form])
                
                return mapped_name, True, mapped_forms or forms
        
        # NOTE: Fuzzy matching for active ingredients is INTENTIONALLY DISABLED for safety.
        # The "active" category is NOT in safe_fuzzy_categories, so this returns (None, 0).
        # Active ingredient mapping relies on EXACT matching only.
        # This prevents dangerous mismatches (e.g., B1 vs B12, Vitamin D vs Vitamin D3).
        fuzzy_match, score = self.matcher.fuzzy_match(processed_name, self.ingredient_variations, "active")
        
        if fuzzy_match:
            # Check for disambiguation on fuzzy matches too
            if fuzzy_match in self.ingredient_context_lookup:
                context_data = self.ingredient_context_lookup[fuzzy_match]
                form_data = context_data.get('form_data', {})
                
                # If this ingredient has context rules, use disambiguation
                if form_data.get('context_include') or form_data.get('context_exclude'):
                    # Use the original full text as context for disambiguation
                    context_text = name.lower()
                    if not self.matcher.disambiguate_ingredient_match(context_text, form_data):
                        # Disambiguation failed, continue searching
                        pass
                    else:
                        mapped_name = self.ingredient_alias_lookup[fuzzy_match]
                        logger.debug(f"Fuzzy matched '{name}' -> '{mapped_name}' (score: {score}) with disambiguation")
                        
                        # Try to find specific forms
                        mapped_forms = []
                        for form in forms:
                            processed_form = self.matcher.preprocess_text(form)
                            if processed_form in self.ingredient_forms_lookup:
                                mapped_forms.append(self.ingredient_forms_lookup[processed_form])
                            else:
                                # Try fuzzy matching for forms (using cached list)
                                # SAFETY: Forms are generally safe for fuzzy matching
                                fuzzy_form, form_score = self.matcher.fuzzy_match(processed_form, self.form_variations, "inactive")
                                if fuzzy_form:
                                    mapped_forms.append(self.ingredient_forms_lookup[fuzzy_form])
                                    logger.debug(f"Fuzzy matched form '{form}' -> '{fuzzy_form}' (score: {form_score})")
                        
                        return mapped_name, True, mapped_forms or forms
                else:
                    # No disambiguation needed
                    mapped_name = self.ingredient_alias_lookup[fuzzy_match]
                    logger.debug(f"Fuzzy matched '{name}' -> '{mapped_name}' (score: {score})")
                    
                    # Try to find specific forms
                    mapped_forms = []
                    for form in forms:
                        processed_form = self.matcher.preprocess_text(form)
                        if processed_form in self.ingredient_forms_lookup:
                            mapped_forms.append(self.ingredient_forms_lookup[processed_form])
                        else:
                            # Try fuzzy matching for forms (using cached list)
                            # SAFETY: Forms are generally safe for fuzzy matching
                            fuzzy_form, form_score = self.matcher.fuzzy_match(processed_form, self.form_variations, "inactive")
                            if fuzzy_form:
                                mapped_forms.append(self.ingredient_forms_lookup[fuzzy_form])
                                logger.debug(f"Fuzzy matched form '{form}' -> '{fuzzy_form}' (score: {form_score})")
                    
                    return mapped_name, True, mapped_forms or forms
            else:
                # No context data available, proceed normally
                mapped_name = self.ingredient_alias_lookup[fuzzy_match]
                logger.debug(f"Fuzzy matched '{name}' -> '{mapped_name}' (score: {score})")
                
                # Try to find specific forms
                mapped_forms = []
                for form in forms:
                    processed_form = self.matcher.preprocess_text(form)
                    if processed_form in self.ingredient_forms_lookup:
                        mapped_forms.append(self.ingredient_forms_lookup[processed_form])
                    else:
                        # Try fuzzy matching for forms (using cached list)
                        # SAFETY: Forms are generally safe for fuzzy matching
                        fuzzy_form, form_score = self.matcher.fuzzy_match(processed_form, self.form_variations, "inactive")
                        if fuzzy_form:
                            mapped_forms.append(self.ingredient_forms_lookup[fuzzy_form])
                            logger.debug(f"Fuzzy matched form '{form}' -> '{fuzzy_form}' (score: {form_score})")
                
                return mapped_name, True, mapped_forms or forms
        
        # Check if ingredient exists in harmful additives database
        harmful_info = self._enhanced_harmful_check(name)
        if harmful_info["category"] != "none":
            # DATA INTEGRITY FIX: Return canonical name from database, not input name
            # This ensures fuzzy-matched ingredients use standardized names
            processed_name = self.matcher.preprocess_text(name)
            if processed_name in self.harmful_lookup:
                canonical_name = self.harmful_lookup[processed_name].get("standard_name", name)
            else:
                # NOTE: Fuzzy matching is disabled for "harmful" category (not in safe_fuzzy_categories).
                # This code path is reached if _enhanced_harmful_check matched via substring or other logic.
                # fuzzy_match will be None, so canonical_name falls back to input name.
                fuzzy_match, _ = self.matcher.fuzzy_match(processed_name, self.harmful_variations, "harmful")
                canonical_name = self.harmful_lookup.get(fuzzy_match, {}).get("standard_name", name) if fuzzy_match else name

            logger.debug(f"Found '{name}' in harmful additives database -> '{canonical_name}' (category: {harmful_info['category']})")
            return canonical_name, True, forms

        # Check if ingredient exists in allergens database
        allergen_info = self._enhanced_allergen_check(name, forms)
        if allergen_info["is_allergen"]:
            # DATA INTEGRITY FIX: Return canonical name from database, not input name
            # This ensures fuzzy-matched allergens use standardized names
            processed_name = self.matcher.preprocess_text(name)
            if processed_name in self.allergen_lookup:
                canonical_name = self.allergen_lookup[processed_name].get("standard_name", name)
            else:
                # NOTE: Fuzzy matching is disabled for "allergen" category (not in safe_fuzzy_categories).
                # This code path is reached if _enhanced_allergen_check matched via forms or other logic.
                # fuzzy_match will be None, so canonical_name falls back to input name.
                fuzzy_match, _ = self.matcher.fuzzy_match(processed_name, self.allergen_variations, "allergen")
                canonical_name = self.allergen_lookup.get(fuzzy_match, {}).get("standard_name", name) if fuzzy_match else name

            logger.debug(f"Found '{name}' in allergens database -> '{canonical_name}' (type: {allergen_info['type']})")
            return canonical_name, True, forms
        
        # Use unified fast lookup for all remaining databases
        fast_result = self._fast_ingredient_lookup(name)
        if fast_result.get("mapped", False):
            result_type = fast_result.get("type", "unknown")
            standard_name = fast_result.get("standard_name", name)
            logger.debug(f"Found '{name}' in {result_type} database -> '{standard_name}' (priority: {fast_result.get('priority', 'N/A')})")
            return standard_name, True, forms
        
        # Don't track as unmapped here - will be handled at higher level
        # after all database checks (harmful, allergen, etc.) are complete
        return name, False, forms
    
    def _enhanced_allergen_check(self, name: str, forms: List[str] = None) -> Dict[str, Any]:
        """Enhanced allergen checking with thread-safe caching"""
        forms = forms or []
        self._cache_stats["allergen_calls"] += 1

        # Use thread-safe @lru_cache - convert list to tuple for hashability
        forms_tuple = tuple(sorted(forms)) if forms else ()
        return self._enhanced_allergen_check_cached(name, forms_tuple)

    @functools.lru_cache(maxsize=1000)  # PERFORMANCE: Reduced from 5000 to prevent memory bloat
    def _enhanced_allergen_check_cached(self, name: str, forms_tuple: tuple) -> Dict[str, Any]:
        """Thread-safe cached allergen checking"""
        forms = list(forms_tuple) if forms_tuple else []

        result = {
            "is_allergen": False,
            "type": None,
            "severity": None
        }

        check_terms = [name] + forms

        for term in check_terms:
            processed_term = self.matcher.preprocess_text(term)

            # Try exact match
            if processed_term in self.allergen_lookup:
                allergen = self.allergen_lookup[processed_term]
                # SAFETY: Ensure standard_name exists
                standard_name = allergen.get("standard_name", "")
                if standard_name:
                    result["is_allergen"] = True
                    result["type"] = standard_name.lower()
                    result["severity"] = allergen.get("severity_level", "low")
                    break

            # NOTE: Fuzzy matching for allergens is INTENTIONALLY DISABLED.
            # "allergen" is NOT in safe_fuzzy_categories, so this always returns (None, 0).
            # Allergen detection relies on EXACT matching only for safety.
            fuzzy_match, score = self.matcher.fuzzy_match(processed_term, self.allergen_variations, "allergen")
            if fuzzy_match:  # Dead code path - fuzzy_match is always None
                allergen = self.allergen_lookup[fuzzy_match]
                # SAFETY: Ensure standard_name exists
                standard_name = allergen.get("standard_name", "")
                if standard_name:
                    result["is_allergen"] = True
                    result["type"] = standard_name.lower()
                    result["severity"] = allergen.get("severity_level", "low")
                    logger.debug(f"Fuzzy allergen match '{term}' -> '{fuzzy_match}' (score: {score})")
                    break

        return result
    
    def _enhanced_harmful_check(self, name: str) -> Dict[str, Any]:
        """Enhanced harmful additive checking with thread-safe caching"""
        self._cache_stats["harmful_calls"] += 1
        return self._enhanced_harmful_check_cached(name)

    @functools.lru_cache(maxsize=1000)  # PERFORMANCE: Reduced from 5000 to prevent memory bloat
    def _enhanced_harmful_check_cached(self, name: str) -> Dict[str, Any]:
        """Thread-safe cached harmful checking"""
        result = {
            "category": "none",
            "severity_level": None
        }

        processed_name = self.matcher.preprocess_text(name)

        # Try exact match
        if processed_name in self.harmful_lookup:
            harmful = self.harmful_lookup[processed_name]
            result["category"] = harmful.get("category", "other")
            result["severity_level"] = harmful.get("severity_level", "low")
        else:
            # NOTE: Fuzzy matching for harmful additives is INTENTIONALLY DISABLED.
            # "harmful" is NOT in safe_fuzzy_categories, so this always returns (None, 0).
            # Harmful detection relies on EXACT matching only for safety.
            fuzzy_match, score = self.matcher.fuzzy_match(processed_name, self.harmful_variations, "harmful")
            if fuzzy_match:  # Dead code path - fuzzy_match is always None
                harmful = self.harmful_lookup[fuzzy_match]
                result["category"] = harmful.get("category", "other")
                result["severity_level"] = harmful.get("severity_level", "low")
                logger.debug(f"Fuzzy harmful match '{name}' -> '{fuzzy_match}' (score: {score})")

        return result

    def _enhanced_non_harmful_check(self, name: str) -> Dict[str, Any]:
        """Enhanced non-harmful additive checking with thread-safe caching"""
        self._cache_stats["non_harmful_calls"] += 1
        return self._enhanced_non_harmful_check_cached(name)

    @functools.lru_cache(maxsize=1000)  # PERFORMANCE: Reduced from 5000 to prevent memory bloat
    def _enhanced_non_harmful_check_cached(self, name: str) -> Dict[str, Any]:
        """Thread-safe cached non-harmful checking"""
        result = {
            "category": "none",
            "additive_type": None,
            "clean_label_score": None,
            "is_additive": None
        }

        processed_name = self.matcher.preprocess_text(name)

        # Try exact match
        if processed_name in self.other_ingredients_lookup:
            other_ing = self.other_ingredients_lookup[processed_name]
            result["category"] = other_ing.get("category", "other")
            result["additive_type"] = other_ing.get("additive_type", "unknown")
            result["clean_label_score"] = other_ing.get("clean_label_score", 7)
            result["is_additive"] = other_ing.get("is_additive", False)
        else:
            # Try fuzzy match (using cached list) - SAFETY: Other ingredients are safe for fuzzy matching
            fuzzy_match, score = self.matcher.fuzzy_match(processed_name, self.non_harmful_variations, "inactive")
            if fuzzy_match:
                other_ing = self.other_ingredients_lookup[fuzzy_match]
                result["category"] = other_ing.get("category", "other")
                result["additive_type"] = other_ing.get("additive_type", "unknown")
                result["clean_label_score"] = other_ing.get("clean_label_score", 7)
                result["is_additive"] = other_ing.get("is_additive", False)
                logger.debug(f"Fuzzy other ingredient match '{name}' -> '{fuzzy_match}' (score: {score})")

        return result
    
    def _check_banned_recalled(self, name: str) -> bool:
        """Check if ingredient exists in banned/recalled ingredients database"""
        processed_name = self.matcher.preprocess_text(name)
        
        # Get ALL arrays from the banned/recalled database dynamically
        arrays_to_check = []
        for key, value in self.banned_recalled.items():
            if isinstance(value, list) and len(value) > 0:
                # Check if items in the list have the expected structure for banned substances
                if any(isinstance(item, dict) and 'standard_name' in item for item in value):
                    arrays_to_check.append(key)

        # Define critical sections for prioritized checking (substring/fuzzy matching)
        critical_sections = [
            "permanently_banned", "nootropic_banned", "sarms_prohibited",
            "illegal_spiking_agents", "new_emerging_threats", "pharmaceutical_adulterants"
        ]
        
        # Check all arrays in the database for exact matches first
        for array_name in arrays_to_check:
            items = self.banned_recalled.get(array_name, [])

            for item in items:
                # Check standard_name - exact match
                standard_name = self.matcher.preprocess_text(item.get("standard_name", ""))
                if standard_name and processed_name == standard_name:
                    return True

                # Check aliases - exact match
                for alias in item.get("aliases", []) or []:
                    processed_alias = self.matcher.preprocess_text(alias)
                    if processed_name == processed_alias:
                        return True

        # Check for substring matches (bidirectional) for critical banned substances
        critical_sections = ["permanently_banned", "sarms_prohibited", "nootropic_banned",
                           "illegal_spiking_agents", "new_emerging_threats", "pharmaceutical_adulterants"]

        for array_name in critical_sections:
            items = self.banned_recalled.get(array_name, [])
            for item in items:
                # Check if banned substance name is contained in ingredient name
                standard_name = self.matcher.preprocess_text(item.get("standard_name", ""))
                if standard_name and len(standard_name) >= 4:  # Avoid short false positives
                    if standard_name in processed_name or processed_name in standard_name:
                        logger.warning(f"Substring banned match: '{name}' contains banned substance '{item.get('standard_name', '')}'")
                        return True

                # Check aliases for substring matches
                for alias in item.get("aliases", []) or []:
                    processed_alias = self.matcher.preprocess_text(alias)
                    if processed_alias and len(processed_alias) >= 4:  # Avoid short false positives
                        if processed_alias in processed_name or processed_name in processed_alias:
                            logger.warning(f"Substring banned match: '{name}' contains banned substance '{alias}'")
                            return True
        
        # NOTE: Fuzzy matching for banned substances is INTENTIONALLY DISABLED for safety.
        # The "banned" category is NOT in safe_fuzzy_categories, so fuzzy_match() returns (None, 0).
        # Banned substance detection relies on EXACT matching only (above).
        # This is the correct behavior - fuzzy matching for safety-critical categories is too risky.
        #
        # If fuzzy matching for banned substances is ever needed, it would require:
        # 1. Adding "banned" to safe_fuzzy_categories (NOT recommended)
        # 2. Using threshold >= 90 (0-100 scale, NOT 0-1)
        # 3. Extensive testing to prevent false positives
        
        return False
    
    def _priority_based_classification(self, name: str, forms: List[str] = None) -> Dict[str, Any]:
        """
        Priority-based ingredient classification to handle overlapping ingredients
        
        Priority order (highest to lowest):
        1. Banned/Recalled ingredients (critical safety)
        2. Harmful additives (risk assessment)
        3. Non-harmful additives (safe additives flagging)
        4. Allergens (safety concern)
        5. Passive/Inactive ingredients (quality neutral)
        
        Returns classification with applied priority rules
        """
        forms = forms or []
        
        # Initialize all classification results
        banned_info = {"is_banned": False, "severity": None, "category": None}
        harmful_info = {"category": "none", "severity_level": None}
        non_harmful_info = {"category": "none", "additive_type": None, "clean_label_score": None}
        allergen_info = {"is_allergen": False, "type": None, "severity": None}
        passive_info = {"is_passive": False, "category": None}
        
        # Use unified fast lookup for all databases
        fast_result = self._fast_ingredient_lookup(name)
        result_type = fast_result.get("type", "none") if fast_result.get("mapped", False) else "none"

        # Map fast lookup results to expected boolean/dict formats
        is_banned = result_type == "banned"
        is_harmful = self._enhanced_harmful_check(name)  # Keep existing for complex logic
        is_non_harmful = self._enhanced_non_harmful_check(name)  # Keep existing for complex logic
        is_allergen = self._enhanced_allergen_check(name, forms)  # Keep existing for complex logic
        # NOTE: "passive" type not currently indexed in _fast_exact_lookup
        # passive_info remains default (is_passive=False) until passive classification is implemented

        # Apply priority rules
        if is_banned:
            # PRIORITY 1: Banned/Recalled - highest priority, overrides all others
            banned_info = {"is_banned": True, "severity": "critical", "category": "banned"}
            # Still populate other info but they won't be used for scoring
            harmful_info = is_harmful
            non_harmful_info = is_non_harmful
            allergen_info = is_allergen

        elif is_harmful["category"] != "none":
            # PRIORITY 2: Harmful additives - second priority
            harmful_info = is_harmful
            non_harmful_info = {"category": "none", "additive_type": None, "clean_label_score": None}
            allergen_info = is_allergen  # Allow allergen info to coexist

        elif is_non_harmful["category"] != "none":
            # PRIORITY 3: Non-harmful additives - third priority (flagged but safe)
            non_harmful_info = is_non_harmful
            harmful_info = {"category": "none", "severity_level": None}
            allergen_info = is_allergen  # Allow allergen info to coexist

        elif is_allergen["is_allergen"]:
            # PRIORITY 4: Allergens - fourth priority
            allergen_info = is_allergen
            harmful_info = {"category": "none", "severity_level": None}
            non_harmful_info = {"category": "none", "additive_type": None, "clean_label_score": None}

        else:
            # No classification found in any database
            harmful_info = is_harmful  # Might still have fuzzy matches
            non_harmful_info = is_non_harmful  # Might still have fuzzy matches
            allergen_info = is_allergen  # Might still have fuzzy matches

        return {
            "banned_info": banned_info,
            "harmful_info": harmful_info,
            "non_harmful_info": non_harmful_info,
            "allergen_info": allergen_info,
            "passive_info": passive_info,  # Always default until passive classification implemented
            "priority_applied": {
                "banned": is_banned,
                "harmful": is_harmful["category"] != "none",
                "non_harmful": is_non_harmful["category"] != "none",
                "allergen": is_allergen["is_allergen"],
                "passive": False  # Not currently implemented
            }
        }
    
    def _flatten_nested_ingredients(self, ingredient_rows: List[Dict]) -> List[Dict]:
        """Flatten nested ingredients from blends for better scoring, preserving blend structure"""
        flattened = []

        for ing in ingredient_rows:
            name = ing.get("name", "")

            # LABEL HEADER CHECK: Must happen BEFORE skip check
            # Label headers like "Less than 2% of:" are in skip_exact but we need to extract their forms first
            if self._is_label_header(name):
                # Pass through label headers to _process_ingredients_enhanced() for form extraction
                # The header itself will be dropped there, but its forms will be extracted
                flattened.append(ing)
                continue

            # SKIP ENFORCEMENT: Skip items from skip list during flattening
            # This runs after label header check so we don't skip headers with forms
            if self._should_skip_ingredient(name):
                logger.debug(f"Skipping ingredient during flattening: {name}")
                # BUT: Still extract nestedRows from skipped parents (e.g., "Total Omega Oil")
                nested = ing.get("nestedRows", [])
                if nested:
                    logger.debug(f"Extracting {len(nested)} nestedRows from skipped parent: {name}")
                    for nested_ing in nested:
                        nested_name = nested_ing.get("name", "")
                        if self._should_skip_ingredient(nested_name):
                            continue
                        nested_ing["parentBlend"] = name
                        nested_ing["isNestedIngredient"] = True
                        if nested_ing.get("nestedRows"):
                            sub_flattened = self._flatten_nested_ingredients([nested_ing])
                            flattened.extend(sub_flattened)
                        else:
                            flattened.append(nested_ing)
                continue

            # Add the main ingredient
            flattened.append(ing)

            # For proprietary blends, nested ingredients are already processed in the main ingredient
            # Only add nested ingredients to flattened list if they're not part of a proprietary blend
            nested = ing.get("nestedRows", [])
            is_proprietary_blend = self._is_proprietary_blend_name(name)

            if nested and not is_proprietary_blend:
                for nested_ing in nested:
                    nested_name = nested_ing.get("name", "")

                    # SKIP ENFORCEMENT: Skip nested items from skip list
                    if self._should_skip_ingredient(nested_name):
                        logger.debug(f"Skipping nested ingredient: {nested_name}")
                        continue

                    # Mark as part of a blend
                    nested_ing["parentBlend"] = name or "Unknown Blend"
                    nested_ing["isNestedIngredient"] = True

                    # Recursively flatten if there are more levels
                    if nested_ing.get("nestedRows"):
                        sub_flattened = self._flatten_nested_ingredients([nested_ing])
                        flattened.extend(sub_flattened)
                    else:
                        flattened.append(nested_ing)
        
        return flattened
    
    def normalize_product(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhanced product normalization with improved ingredient mapping
        """
        try:
            # Extract basic product info
            product_id = str(raw_data.get("id", ""))
            
            # Process status and dates
            off_market = raw_data.get("offMarket", 0)
            status = "discontinued" if off_market == 1 else "active"
            discontinued_date = self._extract_discontinued_date(raw_data.get("events", []) or [])
            
            # Generate image URL
            image_url = self._generate_image_url(raw_data.get("thumbnail", ""), product_id)
            
            # Process contacts
            contacts = self._process_contacts(raw_data.get("contacts", []) or [])
            
            # Flatten and process ingredients with enhanced mapping
            raw_ingredients = raw_data.get("ingredientRows", []) or []
            flattened_ingredients = self._flatten_nested_ingredients(raw_ingredients)

            # Extract nutritional info BEFORE filtering out nutrition facts
            # Handle both "otherIngredients" and "otheringredients" keys
            other_ing_data = raw_data.get("otherIngredients", raw_data.get("otheringredients", {})) or {}
            other_ingredients_raw = other_ing_data.get("ingredients", [])
            # Handle None values from DSLD data
            if other_ingredients_raw is None:
                other_ingredients_raw = []

            # Capture nutritional info from ALL ingredients
            nutritional_info = self._extract_nutritional_info(flattened_ingredients + other_ingredients_raw)

            active_ingredients = self._process_ingredients_enhanced(flattened_ingredients, is_active=True)

            # Process other ingredients - handle both key formats
            inactive_ingredients = self._process_other_ingredients_enhanced(other_ing_data)

            # A4: Dedupe - remove inactive ingredients that also appear in active ingredients
            # If an ingredient has dose/unit in active list, it's the canonical record
            inactive_ingredients = self._dedupe_inactive_ingredients(active_ingredients, inactive_ingredients)

            # Process statements
            statements = self._process_statements(raw_data.get("statements", []) or [])
            
            # Process claims
            claims = self._process_claims(raw_data.get("claims", []) or [])
            
            # Process serving sizes
            serving_sizes = self._process_serving_sizes(raw_data.get("servingSizes", []) or [])
            
            # Calculate mapping statistics (basic cleaning metadata)
            total_ingredients = len(active_ingredients) + len(inactive_ingredients)
            mapped_ingredients = sum(1 for ing in active_ingredients + inactive_ingredients if ing.get("mapped"))

            # Aggregate data from statements and ingredients for labelText.parsed
            all_certifications = []
            all_allergen_free = []
            all_allergens = []  # Actual allergens PRESENT in product (from "Contains:" warnings)
            all_warnings = []
            all_testing = []
            all_flavors = []
            all_harvest_methods = []
            all_marketing_claims = []
            all_quality_features = []

            def add_marketing_claim(claim: str, existing_claims: list):
                """Helper to clean and add marketing claims, avoiding duplicates"""
                # Clean up newlines and extra whitespace
                claim = claim.replace('\n', ' ').replace('\r', ' ')
                claim = ' '.join(claim.split())  # Normalize whitespace
                claim = claim.strip()

                # Skip if too short or already exists
                if len(claim) < 5:
                    return
                if claim in existing_claims:
                    return

                # Skip fragments that start with lowercase "support" (likely partial matches)
                if claim.lower().startswith('support ') and claim[0].islower():
                    # This is a fragment like "support Supports immunity"
                    # Try to extract just the capitalized part
                    capitalized_match = re.search(r'\b([A-Z][^\n.]{10,})', claim)
                    if capitalized_match:
                        claim = capitalized_match.group(1).strip()
                    else:
                        return  # Skip this fragment

                # Check for substring duplicates (avoid "X" and "Y...X" both appearing)
                for existing in existing_claims:
                    if claim in existing or existing in claim:
                        # Keep the longer, more descriptive one
                        if len(claim) > len(existing):
                            existing_claims.remove(existing)
                            break
                        else:
                            return  # Skip this shorter duplicate

                # Split very long claims at logical boundaries
                if len(claim) > 120:
                    # Try to split on common conjunctions that introduce subclauses
                    parts = re.split(r',\s+(?:ensuring|which|that)\s+', claim, maxsplit=1)
                    if len(parts) > 1:
                        # Add both parts separately
                        for part in parts:
                            part = part.strip()
                            if len(part) > 10 and part not in existing_claims:
                                existing_claims.append(part)
                        return

                existing_claims.append(claim)

            # Extract from statements (parse directly from notes since statements no longer have enrichment fields)
            for stmt in statements:
                notes = stmt.get("notes", "")

                # Extract certifications directly from notes
                for cert_name, pattern in CERTIFICATION_PATTERNS.items():
                    if re.search(pattern, notes, re.IGNORECASE):
                        all_certifications.append(cert_name)

                # Extract allergen-free claims directly from notes
                for allergen, pattern in ALLERGEN_FREE_PATTERNS.items():
                    if re.search(pattern, notes, re.IGNORECASE):
                        all_allergen_free.append(allergen)

                # Also parse compound "No X, Y, Z" lists for allergen-related items
                if stmt.get("type") == "Formulation re: Does NOT Contain" or re.search(r'\bNo\s+[^.]+(?:,\s*[^.]+)+', notes, re.I):
                    items_match = re.search(r'No\s+([^.!?]+(?:,\s*(?:or\s+)?[^.!?]+)+)', notes, re.I)
                    if items_match:
                        items_text = items_match.group(1)
                        items = re.split(r',\s*(?:or\s+)?|\s+or\s+', items_text)
                        for item in items:
                            item_lower = item.strip().lower()
                            # Check for common allergens in the list
                            if 'wheat' in item_lower and 'wheat' not in all_allergen_free:
                                all_allergen_free.append('wheat')
                            if 'soy' in item_lower and 'soy' not in all_allergen_free:
                                all_allergen_free.append('soy')
                            if 'dairy' in item_lower or 'milk' in item_lower:
                                if 'dairy' not in all_allergen_free:
                                    all_allergen_free.append('dairy')
                            if 'yeast' in item_lower and 'yeast' not in all_allergen_free:
                                all_allergen_free.append('yeast')
                            if 'egg' in item_lower and 'egg' not in all_allergen_free:
                                all_allergen_free.append('egg')
                            if 'peanut' in item_lower and 'peanut' not in all_allergen_free:
                                all_allergen_free.append('peanut')
                            if 'nut' in item_lower and item_lower not in ['peanut', 'donut', 'coconut']:
                                if 'nut' not in all_allergen_free:
                                    all_allergen_free.append('nut')
                            if 'shellfish' in item_lower and 'shellfish' not in all_allergen_free:
                                all_allergen_free.append('shellfish')

                # Extract warnings
                if re.search(r"keep\s+out\s+of\s+(the\s+)?reach\s+of\s+children", notes, re.I):
                    all_warnings.append("Keep out of reach of children")
                if re.search(r"choking\s+hazard", notes, re.I):
                    all_warnings.append("Choking hazard")
                if re.search(r"not\s+recommended.*autoimmune", notes, re.I):
                    all_warnings.append("Not recommended for individuals with autoimmune conditions")
                if re.search(r"allergi.*(?:to\s+)?plants.*(?:Asteraceae|Compositae)", notes, re.I):
                    all_warnings.append("Persons with allergies to plants of the Asteraceae family should use with caution")
                if re.search(r"(not.*use|before\s+use).*if.*(pregnant|nursing|lactation)", notes, re.I):
                    all_warnings.append("If pregnant, nursing, or taking any medications, consult a healthcare professional before use")
                elif re.search(r"(?:if\s+)?pregnant.*nursing.*(?:taking|consult)", notes, re.I):
                    all_warnings.append("If pregnant, nursing, or taking any medications, consult a healthcare professional before use")
                elif re.search(r"consult.*(doctor|health\s*care\s+(?:practitioner|professional)|physician).*(pregnant|nursing|medical\s+condition|medication)", notes, re.I):
                    all_warnings.append("If pregnant, nursing, or taking any medications, consult a healthcare professional before use")
                if re.search(r"use only as directed", notes, re.I):
                    all_warnings.append("Use only as directed on label")

                # Extract allergens from "Contains:" warnings
                contains_match = re.search(r"contains:?\s+([^.]+)", notes, re.I)
                if contains_match:
                    contains_text = contains_match.group(1).strip()

                    # Negation guard: "Contains no milk...", "contains none of...",
                    # "contains zero...", "contains free of..." are FREE-FROM claims, not
                    # allergen-presence warnings. Without this, a free-from sentence like
                    # "Contains no milk, egg, fish, ..." is wrongly parsed as containing them.
                    if re.match(r"(no|none|not|zero|free|0)\b", contains_text, re.I):
                        contains_text = ""

                    # Only add "Contains:" warnings for actual allergens, not marketing fluff
                    is_real_allergen_warning = False

                    # Check for FDA major allergens
                    if re.search(r"\b(milk|dairy|whey|casein)\b", contains_text, re.I):
                        if "milk" not in all_allergens:
                            all_allergens.append("milk")
                        # Clean up milk warning text
                        if re.search(r"trace.*ferment", contains_text, re.I):
                            all_warnings.append("Contains: Milk (trace amounts from fermentation)")
                        else:
                            all_warnings.append("Contains: Milk")
                        is_real_allergen_warning = True

                    if re.search(r"\b(soy|soybean)\b", contains_text, re.I):
                        if "soy" not in all_allergens:
                            all_allergens.append("soy")
                        all_warnings.append("Contains: Soy")
                        is_real_allergen_warning = True

                    if re.search(r"\b(shellfish|crustacean|shrimp|crab|lobster)\b", contains_text, re.I):
                        if "shellfish" not in all_allergens:
                            all_allergens.append("shellfish")
                        all_warnings.append("Contains: Shellfish")
                        is_real_allergen_warning = True

                    if re.search(r"\b(tree nuts?|almond|walnut|cashew|pecan)\b", contains_text, re.I):
                        if "tree nuts" not in all_allergens:
                            all_allergens.append("tree nuts")
                        all_warnings.append("Contains: Tree Nuts")
                        is_real_allergen_warning = True

                    if re.search(r"\b(peanut|groundnut)\b", contains_text, re.I):
                        if "peanuts" not in all_allergens:
                            all_allergens.append("peanuts")
                        all_warnings.append("Contains: Peanuts")
                        is_real_allergen_warning = True

                    if re.search(r"\b(fish|salmon|tuna|cod)\b", contains_text, re.I):
                        if "fish" not in all_allergens:
                            all_allergens.append("fish")
                        all_warnings.append("Contains: Fish")
                        is_real_allergen_warning = True

                    if re.search(r"\b(wheat|gluten)\b", contains_text, re.I):
                        if "wheat" not in all_allergens:
                            all_allergens.append("wheat")
                        all_warnings.append("Contains: Wheat")
                        is_real_allergen_warning = True

                    if re.search(r"\begg\b", contains_text, re.I):
                        if "eggs" not in all_allergens:
                            all_allergens.append("eggs")
                        all_warnings.append("Contains: Eggs")
                        is_real_allergen_warning = True

                    # Skip marketing fluff like "natural ingredients", "nutrients that clinical research", etc.
                    # These are NOT warnings, just marketing claims

                # Extract testing claims
                if re.search(r'third[- ]party tested|third party testing', notes, re.I):
                    all_testing.append("Third-party tested")
                if re.search(r'meetyourherbs|traceability|ID #', notes, re.I):
                    all_testing.append("meetyourherbs traceability system")
                if re.search(r'analytical results|see analytical', notes, re.I):
                    all_testing.append("Analytical results available")
                if re.search(r'batch|COA|certificate of analysis', notes, re.I):
                    all_quality_features.append("Batch traceability")

                # Extract marketing claims (structure/function)
                if stmt.get("type") in ["Formulation re: Other", "General Statements: All Other Content", "Formula re: Contains"]:
                    # Extract specific health-related claims
                    if re.search(r'\bsupport', notes, re.I):
                        # Match complete "Support/Supports X" phrases with word boundary at start
                        claim_matches = re.findall(r'\b((?:Supports?|Support)\s+[^\n.]+?)(?:\n|\.|\*)', notes, re.I)
                        for claim in claim_matches:
                            add_marketing_claim(claim, all_marketing_claims)

                    # Brand heritage and quality claims
                    if re.search(r'since\s+\d{4}', notes, re.I):
                        match = re.search(r'(since\s+\d{4})', notes, re.I)
                        add_marketing_claim(match.group(1).title(), all_marketing_claims)
                    if re.search(r'premium\s+quality', notes, re.I):
                        match = re.search(r'(premium\s+quality[^.\n]*)', notes, re.I)
                        add_marketing_claim(match.group(1), all_marketing_claims)
                    if re.search(r'traditionally\s+used', notes, re.I):
                        match = re.search(r'(traditionally\s+used[^.\n]+)', notes, re.I)
                        if match:
                            add_marketing_claim(match.group(1), all_marketing_claims)

                    # Potency and extraction claims
                    if re.search(r'maximum.*potency|potency.*maximum', notes, re.I):
                        match = re.search(r'([^.\n]*(?:maximum|potency)[^.\n]*(?:potency|maximum)[^.\n]*)', notes, re.I)
                        if match:
                            add_marketing_claim(match.group(1), all_marketing_claims)
                    if re.search(r'full[- ]spectrum', notes, re.I):
                        match = re.search(r'(full[- ]spectrum[^,.\n]+)', notes, re.I)
                        if match:
                            add_marketing_claim(match.group(1), all_marketing_claims)
                    if re.search(r'solvent[- ]free.*extraction|extraction.*solvent[- ]free', notes, re.I):
                        match = re.search(r'([^.\n]*solvent[- ]free[^.\n]*extraction[^,.\n]*)', notes, re.I)
                        if match:
                            add_marketing_claim(match.group(1), all_marketing_claims)

                    # Testing and bioactivity claims
                    if re.search(r'tested\s+and\s+shown', notes, re.I):
                        match = re.search(r'(tested\s+and\s+shown[^,.\n]+)', notes, re.I)
                        if match:
                            add_marketing_claim(match.group(1), all_marketing_claims)

                    # Standalone marketing claims
                    standalone_claims = [
                        r'(oral\s+health)',
                        r'(fresh\s+breath)',
                        r'(guaranteed\s+potency)',
                        r'(contains\s+.*?billion.*?(?:live\s+)?(?:bacteria|cultures?).*?(?:when\s+manufactured|at\s+time\s+of\s+manufacture))',
                    ]
                    for pattern in standalone_claims:
                        match = re.search(pattern, notes, re.I)
                        if match:
                            add_marketing_claim(match.group(1), all_marketing_claims)

                # Extract quality features
                if re.search(r'safety sealed|sealed for.*protection', notes, re.I):
                    all_quality_features.append("Safety sealed")
                if re.search(r'GMP|good manufacturing practice', notes, re.I):
                    all_quality_features.append("GMP certified")
                if re.search(r'FDA[- ]inspected|FDA inspected facility', notes, re.I):
                    all_quality_features.append("FDA-inspected facility")
                if re.search(r'unconditionally\s+guaranteed\s+for\s+purity', notes, re.I):
                    all_quality_features.append("Unconditionally guaranteed for purity and labeled potency")
                if re.search(r"doctor'?s\s+suggested\s+use", notes, re.I):
                    all_quality_features.append("Doctor's Suggested Use")

                # Extract dietary certifications from statement notes (Kosher goes in certifications, not here)
                if re.search(r'\bvegan\b', notes, re.I):
                    all_quality_features.append("Vegan")
                if re.search(r'\bvegetarian\b', notes, re.I) and "Vegan" not in all_quality_features:
                    all_quality_features.append("Vegetarian")

                # Extract standardization claims
                if re.search(r'standardized', notes, re.I):
                    # Extract what it's standardized to
                    std_match = re.search(r'standardized\s+(?:to\s+)?([^.\n]+)', notes, re.I)
                    if std_match:
                        std_text = std_match.group(1).strip()
                        if len(std_text) < 50:  # Keep it concise
                            all_quality_features.append(f"Standardized to {std_text}")
                    else:
                        all_quality_features.append("Standardized")

                # Extract BioActives and flavonoid content claims
                if re.search(r'BioActives?|bio[\s-]actives?', notes, re.I):
                    all_quality_features.append("Contains BioActives")
                if re.search(r'flavonoid.*content|ensures.*flavonoid', notes, re.I):
                    all_quality_features.append("Standardized for flavonoid content")

                # Extract patented strain information
                if re.search(r'patent|trademark.*(?:BLIS|probiotic|strain)', notes, re.I):
                    if re.search(r'BLIS\s+[KM]\d+', notes, re.I):
                        all_quality_features.append("Patented probiotic strains")

            # Extract flavors from ingredients (normalized and deduplicated)
            flavor_keywords = set()  # Track unique flavors
            for ing in inactive_ingredients:
                name = ing.get("name", "").lower()
                if "flavor" in name:
                    # Normalize flavor name (e.g., "Vanilla flavor" → "vanilla", "Natural Cinnamon Flavor" → "natural cinnamon")
                    flavor_name = re.sub(r'\s*flavou?r(ing|ed|s)?\s*', ' ', name, flags=re.I).strip()
                    flavor_name = ' '.join(flavor_name.split())  # Normalize whitespace
                    if flavor_name and flavor_name not in flavor_keywords:
                        flavor_keywords.add(flavor_name)
                        # Keep original capitalization from ingredient name for final output
                        original_flavor = ing.get("name", "")
                        all_flavors.append(original_flavor)
                if "mint" in name and "flavor" not in name:
                    if "mint" not in flavor_keywords:
                        flavor_keywords.add("mint")
                        all_flavors.append(ing.get("name"))

            # Extract harvest methods from botanical ingredients
            for ing in active_ingredients:
                if ing.get("harvestMethod"):
                    all_harvest_methods.append(ing["harvestMethod"])

            # Build proprietary blend disclosure summary
            proprietary_blends = [ing for ing in active_ingredients if ing.get("proprietaryBlend")]
            proprietary_blend_disclosure = None
            if proprietary_blends:
                blend = proprietary_blends[0]  # Take first blend for summary
                nested_ings = blend.get("nestedIngredients", [])

                # Check if individual amounts are provided
                # If ANY nested ingredient has quantityProvided=False or unit="NP", then "Not Provided"
                any_not_provided = any(
                    not n.get("quantityProvided", False) or n.get("unit") == "NP"
                    for n in nested_ings
                )

                proprietary_blend_disclosure = {
                    "totalAmount": f"{blend.get('quantity', 0)}{blend.get('unit', '')}",
                    "individualAmounts": "Not Provided" if any_not_provided else "Provided",
                    "ingredients": [n["name"] for n in nested_ings]
                }

            # Build cleaned product - PRESERVE ORIGINAL DSLD FIELDS
            cleaned = {
                # ========== ORIGINAL DSLD FIELDS (PRESERVE) ==========
                "id": product_id,
                "src": raw_data.get("src"),  # Data source
                "nhanesId": raw_data.get("nhanesId"),
                "bundleName": raw_data.get("bundleName"),
                "brandIpSymbol": raw_data.get("brandIpSymbol"),
                "productVersionCode": raw_data.get("productVersionCode"),
                "pdf": raw_data.get("pdf"),
                "thumbnail": raw_data.get("thumbnail"),
                "percentDvFootnote": raw_data.get("percentDvFootnote"),

                # Core product info
                "fullName": raw_data.get("fullName", ""),
                "brandName": raw_data.get("brandName", ""),
                "upcSku": raw_data.get("upcSku", ""),
                "hasOuterCarton": raw_data.get("hasOuterCarton", None),
                "upcValid": self._validate_upc(raw_data.get("upcSku", "")),

                # Status
                "status": status,
                "discontinuedDate": discontinued_date,
                "offMarket": off_market,

                # Product details
                "servingsPerContainer": self._safe_int(raw_data.get("servingsPerContainer")) if raw_data.get("servingsPerContainer") is not None else None,
                "netContents": self._extract_net_contents(raw_data.get("netContents", [])),
                "targetGroups": raw_data.get("targetGroups", []) or [],
                "userGroups": raw_data.get("userGroups", []) or [],  # PRESERVE userGroups with Langual codes
                "productType": raw_data.get("productType", {}),  # PRESERVE full Langual structure
                "physicalState": raw_data.get("physicalState", {}),  # PRESERVE full Langual structure

                # Images
                "imageUrl": image_url,
                "images": raw_data.get("images", []) or [],

                # Manufacturer info (PRESERVE original structure with contactId, text, types)
                "contacts": raw_data.get("contacts", []) or [],  # Keep original structure

                # Events
                "events": raw_data.get("events", []) or [],

                # ========== INGREDIENTS (CLEANED) ==========
                "activeIngredients": active_ingredients,
                "inactiveIngredients": inactive_ingredients,

                # ========== NUTRITIONAL INFORMATION ==========
                "nutritionalInfo": nutritional_info,  # Calories, Carbs, Sugar, etc.

                # ========== STATEMENTS AND CLAIMS ==========
                "statements": statements,  # Parsed with certifications
                "claims": claims,  # Keep Langual codes in structure

                # Serving info
                "servingSizes": serving_sizes,

                # Label relationships
                "labelRelationships": raw_data.get("labelRelationships", []) or [],

                # ========== LABEL TEXT (STRUCTURED) ==========
                "labelText": {
                    "raw": self._extract_original_label_text(raw_data),  # Full raw text
                    "parsed": {
                        "certifications": list(set(all_certifications)),
                        "testing": list(set(all_testing)),
                        "origin": self._extract_origin(self._extract_original_label_text(raw_data), raw_data.get("contacts", [])),
                        "flavor": list(set(all_flavors)) if all_flavors else [],
                        "probioticGuarantee": list(set(all_harvest_methods)) if all_harvest_methods else [],
                        "cleanLabelClaims": self._extract_clean_claims(self._extract_original_label_text(raw_data), all_allergen_free),
                        "allergens": list(set(all_allergens)) if all_allergens else [],  # Actual allergens present in product (things it CONTAINS)
                        "allergenFree": list(set(all_allergen_free)) if all_allergen_free else [],  # Allergen-free claims (things it does NOT contain)
                        "warnings": list(set(all_warnings)),
                        "storage": self._extract_storage(statements),
                        "directions": self._extract_directions(statements),
                        "marketingClaims": list(set(all_marketing_claims)) if all_marketing_claims else [],
                        "qualityFeatures": list(set(all_quality_features)) if all_quality_features else [],
                        "proprietaryBlendDisclosure": proprietary_blend_disclosure
                    },
                    "searchText": self._generate_label_text(active_ingredients, inactive_ingredients, statements)
                },

                # ========== METADATA (CLEANING ONLY) ==========
                "metadata": {
                    "lastCleaned": datetime.utcnow().isoformat() + "Z",
                    "cleaningVersion": "2.1.0",  # Updated version - NO ENRICHMENT
                    "reference_versions": self.reference_versions,  # Track data file versions for auditability
                    "mappingStats": {
                        "totalIngredients": total_ingredients,
                        "mappedIngredients": mapped_ingredients,
                        "unmappedIngredients": total_ingredients - mapped_ingredients,
                        "mappingRate": round((mapped_ingredients / total_ingredients * 100), 2) if total_ingredients > 0 else 0,
                        "proprietaryBlends": len(proprietary_blends),
                        "nestedIngredients": sum(len(b.get("nestedIngredients", [])) for b in proprietary_blends)
                    },
                    "transparencyMetrics": self._calculate_transparency_metrics(proprietary_blends, active_ingredients)
                }
            }
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Error normalizing product {raw_data.get('id', 'unknown')}: {str(e)}")
            raise
    
    def _extract_nutritional_info(self, ingredient_rows: List[Dict]) -> Dict[str, Any]:
        """Extract nutritional information (Calories, Carbs, Sugar, etc.) from ingredients"""
        nutritional_info = {}

        for ing in ingredient_rows:
            name = ing.get("name", "").lower()

            # Extract quantities
            quantity_data = ing.get("quantity", [])
            if ing.get("unit") and not isinstance(quantity_data, (list, dict)):
                quantity_data = {"quantity": quantity_data, "unit": ing.get("unit")}
            elif ing.get("unit") and isinstance(quantity_data, dict) and "unit" not in quantity_data:
                quantity_data["unit"] = ing.get("unit")

            quantity, unit, _, _ = self._process_quantity(quantity_data)

            # Capture nutritional facts
            if "calorie" in name:
                nutritional_info["calories"] = {
                    "amount": quantity,
                    "unit": unit or "kcal"
                }
            elif "total carbohydrate" in name or "carbohydrates" in name:
                nutritional_info["totalCarbohydrates"] = {
                    "amount": quantity,
                    "unit": unit or "g"
                }
            elif name == "sugar" or "sugars" in name:
                nutritional_info["sugars"] = {
                    "amount": quantity,
                    "unit": unit or "g"
                }
            elif "total fat" in name:
                nutritional_info["totalFat"] = {
                    "amount": quantity,
                    "unit": unit or "g"
                }
            elif "protein" in name:
                nutritional_info["protein"] = {
                    "amount": quantity,
                    "unit": unit or "g"
                }
            elif "sodium" in name:
                nutritional_info["sodium"] = {
                    "amount": quantity,
                    "unit": unit or "mg"
                }
            elif "fiber" in name or "dietary fiber" in name:
                nutritional_info["dietaryFiber"] = {
                    "amount": quantity,
                    "unit": unit or "g"
                }

            # P0.2: Check nestedRows for sugar/fiber (commonly nested under Total Carbohydrates)
            nested_rows = ing.get("nestedRows", [])
            for nested in nested_rows:
                nested_name = nested.get("name", "").lower()

                # Process nested quantity
                nested_qty_data = nested.get("quantity", [])
                if nested.get("unit") and not isinstance(nested_qty_data, (list, dict)):
                    nested_qty_data = {"quantity": nested_qty_data, "unit": nested.get("unit")}
                elif nested.get("unit") and isinstance(nested_qty_data, dict) and "unit" not in nested_qty_data:
                    nested_qty_data["unit"] = nested.get("unit")

                nested_qty, nested_unit, _, _ = self._process_quantity(nested_qty_data)

                # Extract sugar from nested row (only if not already found at top level)
                if (nested_name == "sugar" or "sugars" in nested_name) and "sugars" not in nutritional_info:
                    nutritional_info["sugars"] = {
                        "amount": nested_qty,
                        "unit": nested_unit or "g"
                    }
                    logger.debug(f"Extracted sugar from nested row: {nested_qty}{nested_unit or 'g'}")

                # Extract fiber from nested row (only if not already found at top level)
                if ("fiber" in nested_name or "dietary fiber" in nested_name) and "dietaryFiber" not in nutritional_info:
                    nutritional_info["dietaryFiber"] = {
                        "amount": nested_qty,
                        "unit": nested_unit or "g"
                    }
                    logger.debug(f"Extracted fiber from nested row: {nested_qty}{nested_unit or 'g'}")

        return nutritional_info

    def _process_ingredients_enhanced(self, ingredient_rows: List[Dict], is_active: bool = True) -> List[Dict]:
        """Process ingredients with enhanced mapping"""
        processed = []

        for ing in ingredient_rows:
            name = ing.get("name", "")

            # A3: Handle "Less than 2% of:" headers with real ingredients in forms
            if self._is_label_header(name):
                # Extract real ingredients from forms and process them as inactive ingredients
                forms = ing.get("forms", []) or []
                logger.debug(f"Extracting {len(forms)} ingredients from label header: {name}")
                for form in forms:
                    if isinstance(form, dict):
                        form_name = form.get("name", "")
                        if form_name:
                            # Create a synthetic ingredient entry from the form
                            synthetic_ing = {
                                "name": form_name,
                                "ingredientId": form.get("ingredientId"),
                                "order": form.get("order", ing.get("order", 0)),
                                # Mark as coming from a label header (for transparency)
                                "_fromLabelHeader": name
                            }
                            # Process as inactive since "Less than 2%" items are minor ingredients
                            processed_form = self._process_single_ingredient_enhanced(synthetic_ing, is_active=False)
                            if processed_form is not None:
                                if isinstance(processed_form, list):
                                    processed.extend(processed_form)
                                else:
                                    processed.append(processed_form)
                # Skip the header itself
                continue

            processed_ing = self._process_single_ingredient_enhanced(ing, is_active)
            # Skip None values (nutrition facts that were filtered out)
            if processed_ing is not None:
                # Handle list returns (from skipped parents with nestedRows)
                if isinstance(processed_ing, list):
                    processed.extend(processed_ing)
                else:
                    processed.append(processed_ing)

        return processed
    
    def _process_single_ingredient_enhanced(self, ing: Dict, is_active: bool) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """Process a single ingredient with enhanced mapping.

        Returns:
            - Dict: Single processed ingredient
            - List[Dict]: When parent is skipped but has nestedRows (returns nested ingredients)
            - None: When ingredient should be skipped entirely
        """
        name = ing.get("name", "")
        nested_rows = ing.get("nestedRows", [])

        # SKIP ENFORCEMENT: Check skip list FIRST before any processing
        # Applies processing precedence: skip > empty > header > nutrition > normal
        if self._should_skip_ingredient(name):
            logger.debug(f"Skipping ingredient from skip list: {name}")
            # BUT: If parent has nestedRows, process those as standalone ingredients
            # (e.g., "Total Omega Oil" is skipped, but Omega-3/6/9 nested rows are real data)
            if nested_rows:
                logger.debug(f"Processing {len(nested_rows)} nestedRows from skipped parent: {name}")
                nested_results = []
                for nested_ing in nested_rows:
                    nested_processed = self._process_single_ingredient_enhanced(nested_ing, is_active)
                    if nested_processed:
                        if isinstance(nested_processed, list):
                            nested_results.extend(nested_processed)
                        else:
                            nested_processed["parentBlend"] = name
                            nested_processed["isNestedIngredient"] = True
                            nested_processed["quantityProvided"] = (
                                nested_processed.get("quantity", 0) > 0 and
                                nested_processed.get("unit", "") != "NP"
                            )
                            nested_results.append(nested_processed)
                if nested_results:
                    return nested_results
            return None

        notes = ing.get("notes", "")
        ingredient_group = ing.get("ingredientGroup", "")
        unit_raw = ing.get("unit", "")

        # Extract unit from quantity if not at ingredient level
        if not unit_raw:
            quantity_data = ing.get("quantity", [])
            if isinstance(quantity_data, list) and quantity_data:
                unit_raw = quantity_data[0].get("unit", "") if isinstance(quantity_data[0], dict) else ""

        # Extract forms with prefix for context-aware mapping (e.g., "from Fruits" -> "from fruits")
        forms = []
        for f in ing.get("forms", []) or []:
            if isinstance(f, dict):
                prefix = (f.get("prefix", "") or "").strip()
                name_part = (f.get("name", "") or "").strip()
                # Include prefix for context (e.g., "from Fruits" helps distinguish natural colors)
                full_form = f"{prefix} {name_part}".strip() if prefix else name_part
                if full_form:
                    forms.append(full_form)
            elif f:
                forms.append(str(f))

        # A3: Check if this is a label header like "Less than 2% of:"
        # If so, extract real ingredients from forms and skip the header itself
        if self._is_label_header(name):
            logger.debug(f"Skipping label header: {name} (forms will be extracted separately)")
            return None

        # Extract form information from ingredient name if no explicit forms provided
        if not forms and name:
            extracted_forms = self._extract_forms_from_ingredient_name(name)
            if extracted_forms:
                forms = extracted_forms

        # Skip nutritional facts - these are not supplement ingredients
        # Note: Harmful nutrition facts (trans fat, sugar, sodium) are captured by
        # _extract_nutritional_warnings() which runs before ingredient processing
        # A9: Also check ingredientGroup and unit patterns
        if self._is_nutrition_fact(name, ingredient_group, unit_raw):
            logger.debug(f"Skipping nutrition fact: {name} (group: {ingredient_group}, unit: {unit_raw})")
            return None
        
        # Enhanced mapping with fuzzy matching
        standard_name, mapped, mapped_forms = self._enhanced_ingredient_mapping(name, forms)

        # Priority-based ingredient classification to handle overlaps
        classification = self._priority_based_classification(name, forms)
        
        # Extract individual classification results with priority handling
        allergen_info = classification["allergen_info"]
        harmful_info = classification["harmful_info"]
        non_harmful_info = classification["non_harmful_info"]
        banned_info = classification["banned_info"]
        passive_info = classification["passive_info"]

        # Extract features from notes
        extracted_features = self._extract_ingredient_features(notes)

        # Process quantity - handle both nested and flat formats
        quantity_data = ing.get("quantity", [])
        
        # If unit is at ingredient level, merge it with quantity data
        if ing.get("unit") and not isinstance(quantity_data, (list, dict)):
            # Convert flat format to nested format for consistent processing
            quantity_data = {"quantity": quantity_data, "unit": ing.get("unit")}
        elif ing.get("unit") and isinstance(quantity_data, dict) and "unit" not in quantity_data:
            # Add unit to existing dict format
            quantity_data["unit"] = ing.get("unit")
            
        quantity, unit, daily_value, quantity_variants = self._process_quantity(quantity_data)

        # Check if proprietary - based on quantity OR if name contains blend indicators
        is_proprietary = quantity == 0 or unit == "NP" or self._is_proprietary_blend_name(name)
        
        # Determine disclosure level for proprietary blends
        disclosure_level = None
        nested_ingredients_processed = []
        nested_rows = ing.get("nestedRows", [])

        if is_proprietary or self._is_proprietary_blend_name(name):
            disclosure_level = self._determine_disclosure_level(name, quantity, unit, nested_rows)

        # Process nested ingredients regardless of proprietary status
        # Non-blend parents (e.g., "Total Omega Oil") can have real sub-components (Omega-3, Omega-6, etc.)
        if nested_rows:
            for nested_ing in nested_rows:
                nested_processed = self._process_single_ingredient_enhanced(nested_ing, is_active)
                if nested_processed:
                    # Handle list returns (from nested skipped parents with their own nestedRows)
                    if isinstance(nested_processed, list):
                        for item in nested_processed:
                            item["parentBlend"] = name
                            item["isNestedIngredient"] = True
                            item["quantityProvided"] = (
                                item.get("quantity", 0) > 0 and item.get("unit", "") != "NP"
                            )
                        nested_ingredients_processed.extend(nested_processed)
                    else:
                        nested_processed["parentBlend"] = name
                        nested_processed["isNestedIngredient"] = True
                        # Add quantityProvided flag for nested ingredients
                        nested_qty = nested_processed.get("quantity", 0)
                        nested_unit = nested_processed.get("unit", "")
                        nested_processed["quantityProvided"] = nested_qty > 0 and nested_unit != "NP"
                        nested_ingredients_processed.append(nested_processed)

        # An ingredient is considered "mapped" if it's found in ANY reference database
        # This includes ingredient databases, harmful additives, non-harmful additives, allergens, banned, passive databases, or proprietary blends
        is_mapped = (mapped or
                    harmful_info["category"] != "none" or
                    non_harmful_info["category"] != "none" or
                    allergen_info["is_allergen"] or
                    banned_info["is_banned"] or
                    passive_info["is_passive"] or
                    is_proprietary)

        # Track unmapped ingredients only if not found in any database
        # AND not a nutrition fact/label phrase
        if not is_mapped and not self._is_nutrition_fact(name):
            processed_name = self.matcher.preprocess_text(name)
            self.unmapped_ingredients[name] += 1
            self.unmapped_details[name] = {
                "processed_name": processed_name,
                "forms": forms,
                "variations_tried": self.matcher.generate_variations(processed_name),
                "is_active": is_active  # Track whether this is an active ingredient
            }

        # Preserve forms with full structure (including IDs if available)
        forms_structured = []
        raw_forms = ing.get("forms", []) or []
        for form in raw_forms:
            if isinstance(form, dict):
                forms_structured.append({
                    "name": form.get("name", ""),
                    "ingredientId": form.get("ingredientId"),
                    "order": form.get("order"),
                    "prefix": form.get("prefix"),
                    "percent": form.get("percent")
                })
            elif isinstance(form, str):
                forms_structured.append({"name": form})

        # Parse botanical details from notes (plantPart, genus, species, harvestMethod, form)
        botanical_details = self._parse_botanical_details(notes)

        # Check if this ingredient is an additive (add metadata flag for enrichment phase)
        processed_name_check = self.matcher.preprocess_text(name)
        is_additive = False
        additive_type = None
        if processed_name_check in self.other_ingredients_lookup:
            additive_data = self.other_ingredients_lookup[processed_name_check]
            is_additive = additive_data.get("is_additive", False)
            if is_additive:
                additive_type = additive_data.get("additive_type")

        # Extract branded token from compound names (e.g., "KSM-66" from "KSM-66 Ashwagandha Root Extract")
        # This enables correct matching to branded forms in the quality map
        branded_token = self._extract_branded_token(name)

        # Build base ingredient structure
        result = {
            # Original DSLD identifiers (PRESERVE)
            "ingredientId": ing.get("ingredientId"),
            "uniiCode": ing.get("uniiCode"),
            "order": ing.get("order", 0),

            # PROVENANCE FIELDS (Pipeline Hardening Phase 2)
            # raw_source_text: Exact substring from DSLD, set once, never modified
            "raw_source_text": name,
            # branded_token_extracted: If present, use for quality map matching instead of raw_source_text
            # This enables "KSM-66 Ashwagandha Root Extract" to match "KSM-66 ashwagandha" form
            "branded_token_extracted": branded_token,
            # raw_source_path: Source section (active/inactive), enrichment adds full path
            "raw_source_path": "activeIngredients" if is_active else "inactiveIngredients",
            # normalized_key: Stable key for dedup/tracking, computed ONCE
            "normalized_key": norm_module.make_normalized_key(name),

            # Basic ingredient info
            "name": branded_token if branded_token else name,  # Use branded token as primary name if extracted
            "standardName": standard_name,  # From our database mapping
            "ingredientGroup": ing.get("ingredientGroup"),  # PRESERVE from DSLD (even if wrong)

            # Quantity and daily value
            "quantity": quantity,
            "unit": unit,
            "dailyValue": daily_value,
            # P0.3: Preserve all quantity variants for multi-serving products
            "quantityVariants": quantity_variants if len(quantity_variants) > 1 else None,

            # Forms (PRESERVE full structure with IDs)
            "forms": forms_structured if forms_structured else [],
            "alternateNames": ing.get("alternateNames", []) or [],

            # Mapping status (basic cleaning metadata)
            "mapped": is_mapped,

            # Proprietary blend structure (transparency metadata, NOT scoring)
            "proprietaryBlend": is_proprietary,
            "disclosureLevel": disclosure_level if is_proprietary else None,

            # Nested ingredients (preserve hierarchy)
            "parentBlend": ing.get("parentBlend", None),
            "isNestedIngredient": ing.get("isNestedIngredient", False),
            "nestedIngredients": nested_ingredients_processed,

            # Hierarchy classification for scoring (source/summary/component)
            "hierarchyType": self._classify_hierarchy_type(name)
        }

        # Add additive metadata flag (for enrichment phase to use)
        if is_additive:
            result["isAdditive"] = True
            if additive_type:
                result["additiveType"] = additive_type

        # Add botanical details if present
        if botanical_details.get("plantPart"):
            result["plantPart"] = botanical_details["plantPart"]
        if botanical_details.get("genus"):
            result["genus"] = botanical_details["genus"]
        if botanical_details.get("species"):
            result["species"] = botanical_details["species"]
        if botanical_details.get("harvestMethod"):
            result["harvestMethod"] = botanical_details["harvestMethod"]
        if botanical_details.get("form"):
            result["form"] = botanical_details["form"]

        # Add notes field (after botanical parsing)
        if notes:
            result["notes"] = notes

        return result
    
    def _process_other_ingredients_enhanced(self, other_ing_data: Dict) -> List[Dict]:
        """Process inactive/other ingredients with enhanced mapping and parallel processing"""
        ingredients = other_ing_data.get("ingredients", [])

        # Handle None values from DSLD data
        if ingredients is None:
            return []

        if not ingredients:
            return []

        # Normalize ingredients - convert strings to dict format if needed
        # PRESERVE forms exactly as they appear - do NOT expand
        normalized_ingredients = []
        for ing in ingredients:
            if isinstance(ing, str):
                # Convert string to dict format
                normalized_ingredients.append({"name": ing})
            elif isinstance(ing, dict):
                # Keep ingredient as-is, preserving all fields including forms
                normalized_ingredients.append(ing)
            else:
                # Skip invalid entries
                continue

        # OPTIMIZATION: Use parallel processing for large ingredient lists
        # ✅ THREAD-SAFE: Now using @lru_cache decorators for all caching - safe for parallel processing
        if len(normalized_ingredients) >= self._parallel_threshold:
            logger.info(f"🚀 Using parallel processing for {len(normalized_ingredients)} ingredients")
            return self._process_ingredients_parallel(normalized_ingredients)
        else:
            return self._process_ingredients_sequential(normalized_ingredients)

    def _process_ingredients_parallel(self, ingredients: List[Dict]) -> List[Dict]:
        """Process ingredients using parallel execution with functional grouping support"""
        # First, expand any functional groupings (must be done sequentially to preserve order)
        # Also handle label headers here to ensure forms get properly extracted
        expanded_ingredients = []
        for ing in ingredients:
            name = ing.get("name", "")

            # LABEL HEADER SYMMETRY: Check for headers like "Less than 2% of:" BEFORE other processing
            # Drop header row, extract forms[] as child ingredients
            if self._is_label_header(name):
                forms = ing.get("forms", []) or []
                if forms:
                    logger.debug(f"Extracting {len(forms)} ingredients from label header (parallel): {name}")
                    for form in forms:
                        if isinstance(form, dict):
                            form_name = form.get("name", "")
                            # Skip check on extracted forms (forms must also pass skip filter)
                            if form_name and not self._should_skip_ingredient(form_name):
                                # Create synthetic ingredient entry from form
                                expanded_ingredients.append({
                                    "name": form_name,
                                    "ingredientId": form.get("ingredientId"),
                                    "order": form.get("order", ing.get("order", 0)),
                                    "ingredientGroup": ing.get("ingredientGroup"),
                                    "_fromLabelHeader": name,
                                    "_transparency": "standard"
                                })
                        elif isinstance(form, str) and form:
                            # Skip check on string form names too
                            if not self._should_skip_ingredient(form):
                                expanded_ingredients.append({
                                    "name": form,
                                    "order": ing.get("order", 0),
                                    "_fromLabelHeader": name,
                                    "_transparency": "standard"
                                })
                else:
                    # Header with no forms - drop anyway (adds no analytic value)
                    logger.debug(f"Dropping label header with no forms: {name}")
                # Skip the header itself - do not emit as ingredient
                continue

            # TRANSPARENCY SCORING: Check for functional grouping
            grouping_data = self.grouping_handler.process_ingredient_for_cleaning(name)

            if grouping_data['type'] == 'functional_group_with_details':
                # Expand into multiple ingredients with functional context
                for specific_ing in grouping_data['ingredients']:
                    expanded_ingredients.append({
                        **ing,  # Copy order and other fields
                        "name": specific_ing,
                        "_functional_context": grouping_data['functional_type'],
                        "_functional_prefix": grouping_data['prefix'],
                        "_transparency": "good"
                    })
            elif grouping_data['type'] in ['functional_group_vague', 'vague_declaration']:
                # Keep as-is but add transparency flags
                expanded_ingredients.append({
                    **ing,
                    "_transparency": "poor",
                    "_vague_disclosure": True,
                    "_vague_flags": grouping_data.get('vague_flags', [])
                })
            else:
                # Regular ingredient
                expanded_ingredients.append({
                    **ing,
                    "_transparency": "standard"
                })

        # Now process expanded ingredients in parallel
        processed = []
        # THREAD-SAFETY FIX: Collect unmapped info from workers, merge after parallel execution
        collected_unmapped = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # Submit all ingredient processing tasks
            future_to_ingredient = {
                executor.submit(self._process_ingredient_for_other_parallel, ing): ing
                for ing in expanded_ingredients
            }

            # Collect results as they complete
            for future in as_completed(future_to_ingredient):
                try:
                    result = future.result()
                    # Result is now (ingredient_data, unmapped_info) tuple
                    if result is not None:
                        ingredient_data, unmapped_info = result
                        if ingredient_data is not None:
                            processed.append(ingredient_data)
                        if unmapped_info is not None:
                            collected_unmapped.append(unmapped_info)
                except Exception as e:
                    ingredient = future_to_ingredient[future]
                    logger.error(f"Error processing ingredient '{ingredient.get('name', 'unknown')}': {e}")
                    # Add a basic result for failed processing (CLEANING ONLY - NO ENRICHMENT)
                    ing_name = ingredient.get("name", "")
                    processed.append({
                        "order": ingredient.get("order", 0),
                        "ingredientId": ingredient.get("ingredientId"),
                        "uniiCode": ingredient.get("uniiCode"),
                        # PROVENANCE FIELDS (Pipeline Hardening Phase 2)
                        "raw_source_text": ing_name,
                        "raw_source_path": "inactiveIngredients",
                        "normalized_key": norm_module.make_normalized_key(ing_name),
                        "name": ing_name,
                        "standardName": ing_name,
                        "ingredientGroup": ingredient.get("ingredientGroup"),
                        "forms": [],
                        "alternateNames": [],
                        "mapped": False
                    })

        # THREAD-SAFETY FIX: Merge unmapped info in single-threaded context
        for unmapped in collected_unmapped:
            name = unmapped["name"]
            self.unmapped_ingredients[name] += 1
            self.unmapped_details[name] = {
                "processed_name": unmapped["processed_name"],
                "forms": unmapped["forms"],
                "variations_tried": unmapped["variations_tried"],
                "is_active": unmapped["is_active"]
            }

        # Sort by original order (with safe comparison)
        def safe_order_key(x):
            order = x.get("order", 0)
            # Ensure order is always a number
            try:
                return float(order) if order is not None else 0.0
            except (ValueError, TypeError):
                return 0.0

        processed.sort(key=safe_order_key)
        return processed

    def _process_ingredient_for_other_parallel(self, ingredient_data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Process a single other/inactive ingredient for parallel execution.

        Returns:
            Tuple of (processed_ingredient, unmapped_info)
            - processed_ingredient: cleaned ingredient dict, or None if skipped
            - unmapped_info: dict with name, processed_name, etc. if unmapped, else None

        Thread-safety: This method does NOT mutate shared state. The caller
        merges unmapped_info in a single-threaded step after parallel execution.
        """
        name = ingredient_data.get("name", "")

        # SKIP ENFORCEMENT: Check skip list FIRST before any processing
        if self._should_skip_ingredient(name):
            logger.debug(f"Skipping other ingredient from skip list: {name}")
            return (None, None)  # Tuple format for consistency with normal return

        # Extract forms with prefix for context-aware mapping (e.g., "from Fruits" for natural colors)
        forms = []
        for f in ingredient_data.get("forms", []) or []:
            if isinstance(f, dict):
                prefix = (f.get("prefix", "") or "").strip()
                name_part = (f.get("name", "") or "").strip()
                full_form = f"{prefix} {name_part}".strip() if prefix else name_part
                if full_form:
                    forms.append(full_form)
            elif f:
                forms.append(str(f))

        # Enhanced mapping (pass forms for context-aware mapping)
        standard_name, mapped, _ = self._enhanced_ingredient_mapping(name, forms)

        # Enhanced checks
        allergen_info = self._enhanced_allergen_check(name, forms)
        harmful_info = self._enhanced_harmful_check(name)

        # Check if proprietary blend
        is_proprietary = self._is_proprietary_blend_name(name)

        # Calculate final mapping status
        is_mapped = (mapped or
                    harmful_info["category"] != "none" or
                    allergen_info["is_allergen"] or
                    is_proprietary)

        # Track unmapped ingredients only if not found in any database
        # NOTE: We collect unmapped info here but DON'T mutate shared state
        # The calling function merges this in a single-threaded step after parallel execution
        unmapped_info = None
        if not is_mapped and not self._is_nutrition_fact(name):
            processed_name = self.matcher.preprocess_text(name)
            unmapped_info = {
                "name": name,
                "processed_name": processed_name,
                "forms": forms,  # Include forms for context
                "variations_tried": self.matcher.generate_variations(processed_name),
                "is_active": False  # Other ingredients
            }

        # Preserve forms with full structure (including IDs if available)
        forms_structured = []
        raw_forms = ingredient_data.get("forms", []) or []
        for form in raw_forms:
            if isinstance(form, dict):
                forms_structured.append({
                    "name": form.get("name", ""),
                    "ingredientId": form.get("ingredientId"),
                    "order": form.get("order"),
                    "prefix": form.get("prefix"),
                    "percent": form.get("percent")
                })
            elif isinstance(form, str):
                forms_structured.append({"name": form})

        # Check if this ingredient is an additive (add metadata flag for enrichment phase)
        processed_name_check = self.matcher.preprocess_text(name)
        is_additive = False
        additive_type = None
        if processed_name_check in self.other_ingredients_lookup:
            additive_data = self.other_ingredients_lookup[processed_name_check]
            is_additive = additive_data.get("is_additive", False)
            if is_additive:
                additive_type = additive_data.get("additive_type")

        # Build result - CLEANING ONLY (no enrichment)
        result = {
            # Original DSLD identifiers (PRESERVE)
            "ingredientId": ingredient_data.get("ingredientId"),
            "uniiCode": ingredient_data.get("uniiCode"),
            "order": ingredient_data.get("order", 0),

            # PROVENANCE FIELDS (Pipeline Hardening Phase 2)
            # raw_source_text: Exact substring from DSLD, set once, never modified
            "raw_source_text": name,
            # raw_source_path: Source section (inactive for other ingredients)
            "raw_source_path": "inactiveIngredients",
            # normalized_key: Stable key for dedup/tracking, computed ONCE
            "normalized_key": norm_module.make_normalized_key(name),

            # Basic ingredient info
            "name": name,
            "standardName": standard_name,  # From our database mapping
            "ingredientGroup": ingredient_data.get("ingredientGroup"),  # PRESERVE from DSLD (even if wrong)

            # Forms (PRESERVE full structure with IDs)
            "forms": forms_structured if forms_structured else [],
            "alternateNames": ingredient_data.get("alternateNames", []) or [],

            # Mapping status (basic cleaning metadata)
            "mapped": is_mapped,

            # Hierarchy classification for scoring (source/summary/component)
            "hierarchyType": self._classify_hierarchy_type(name)
        }

        # Add additive metadata flag (for enrichment phase to use)
        if is_additive:
            result["isAdditive"] = True
            if additive_type:
                result["additiveType"] = additive_type

        # NO ENRICHMENT FIELDS (transparency, formsDisclosed, functional_context, vague_disclosure, etc.)
        # Those belong in the enrichment phase

        # Return tuple: (processed_ingredient, unmapped_info)
        # Caller merges unmapped_info in single-threaded step (thread-safety fix)
        return (result, unmapped_info)

    def _process_ingredients_sequential(self, ingredients: List[Dict]) -> List[Dict]:
        """Process ingredients sequentially (for small lists)"""
        processed = []

        for ing in ingredients:
            name = ing.get("name", "")

            # SKIP ENFORCEMENT: Check skip list FIRST before any processing
            if self._should_skip_ingredient(name):
                logger.debug(f"Skipping ingredient from skip list: {name}")
                continue

            # LABEL HEADER SYMMETRY: Check for headers like "Less than 2% of:"
            # Drop header row, extract forms[] as child ingredients
            if self._is_label_header(name):
                forms = ing.get("forms", []) or []
                if forms:
                    logger.debug(f"Extracting {len(forms)} ingredients from label header (sequential): {name}")
                    for form in forms:
                        if isinstance(form, dict):
                            form_name = form.get("name", "")
                            # Skip check on extracted forms (forms must also pass skip filter)
                            if form_name and not self._should_skip_ingredient(form_name):
                                # Process form as a standalone ingredient
                                form_std_name, form_mapped, _ = self._enhanced_ingredient_mapping(form_name)
                                form_allergen_info = self._enhanced_allergen_check(form_name)
                                form_harmful_info = self._enhanced_harmful_check(form_name)
                                form_is_proprietary = self._is_proprietary_blend_name(form_name)
                                form_is_mapped = (form_mapped or
                                                form_harmful_info["category"] != "none" or
                                                form_allergen_info["is_allergen"] or
                                                form_is_proprietary)

                                # Track unmapped if not found
                                if not form_is_mapped and not self._is_nutrition_fact(form_name):
                                    form_processed_name = self.matcher.preprocess_text(form_name)
                                    self.unmapped_ingredients[form_name] += 1
                                    self.unmapped_details[form_name] = {
                                        "processed_name": form_processed_name,
                                        "forms": [],
                                        "variations_tried": self.matcher.generate_variations(form_processed_name),
                                        "is_active": False
                                    }

                                processed.append({
                                    "ingredientId": form.get("ingredientId"),
                                    "uniiCode": form.get("uniiCode"),
                                    "order": form.get("order", ing.get("order", 0)),
                                    # PROVENANCE FIELDS (Pipeline Hardening Phase 2)
                                    "raw_source_text": form_name,
                                    "raw_source_path": "inactiveIngredients",
                                    "normalized_key": norm_module.make_normalized_key(form_name),
                                    "name": form_name,
                                    "standardName": form_std_name,
                                    "ingredientGroup": ing.get("ingredientGroup"),
                                    "forms": [],
                                    "alternateNames": [],
                                    "mapped": form_is_mapped,
                                    "hierarchyType": self._classify_hierarchy_type(form_name),
                                    "_fromLabelHeader": name
                                })
                        elif isinstance(form, str) and form:
                            # Skip check on string form names too
                            if not self._should_skip_ingredient(form):
                                form_std_name, form_mapped, _ = self._enhanced_ingredient_mapping(form)
                                form_allergen_info = self._enhanced_allergen_check(form)
                                form_harmful_info = self._enhanced_harmful_check(form)
                                form_is_proprietary = self._is_proprietary_blend_name(form)
                                form_is_mapped = (form_mapped or
                                                form_harmful_info["category"] != "none" or
                                                form_allergen_info["is_allergen"] or
                                                form_is_proprietary)

                                processed.append({
                                    "order": ing.get("order", 0),
                                    # PROVENANCE FIELDS (Pipeline Hardening Phase 2)
                                    "raw_source_text": form,
                                    "raw_source_path": "inactiveIngredients",
                                    "normalized_key": norm_module.make_normalized_key(form),
                                    "name": form,
                                    "standardName": form_std_name,
                                    "ingredientGroup": ing.get("ingredientGroup"),
                                    "forms": [],
                                    "alternateNames": [],
                                    "mapped": form_is_mapped,
                                    "hierarchyType": self._classify_hierarchy_type(form),
                                    "_fromLabelHeader": name
                                })
                else:
                    # Header with no forms - drop anyway (adds no analytic value)
                    logger.debug(f"Dropping label header with no forms: {name}")
                # Skip the header itself - do not emit as ingredient
                continue

            # CLEANING ONLY - No enrichment, no transparency scoring
            # Extract forms with prefix for context-aware mapping (e.g., "from Fruits" for natural colors)
            forms = []
            for f in ing.get("forms", []) or []:
                if isinstance(f, dict):
                    prefix = (f.get("prefix", "") or "").strip()
                    name_part = (f.get("name", "") or "").strip()
                    full_form = f"{prefix} {name_part}".strip() if prefix else name_part
                    if full_form:
                        forms.append(full_form)
                elif f:
                    forms.append(str(f))

            # Enhanced mapping to get standardName (pass forms for context-aware mapping)
            standard_name, mapped, _ = self._enhanced_ingredient_mapping(name, forms)

            # Enhanced checks ONLY for determining if ingredient is "mapped" (found in database)
            allergen_info = self._enhanced_allergen_check(name, forms)
            harmful_info = self._enhanced_harmful_check(name)
            is_proprietary = self._is_proprietary_blend_name(name)

            # An ingredient is considered "mapped" if it's found in ANY reference database
            is_mapped = (mapped or
                        harmful_info["category"] != "none" or
                        allergen_info["is_allergen"] or
                        is_proprietary)

            # Track unmapped ingredients only if not found in any database
            if not is_mapped and not self._is_nutrition_fact(name):
                processed_name = self.matcher.preprocess_text(name)
                self.unmapped_ingredients[name] += 1
                self.unmapped_details[name] = {
                    "processed_name": processed_name,
                    "forms": forms,
                    "variations_tried": self.matcher.generate_variations(processed_name),
                    "is_active": False  # Inactive ingredients
                }

            # Preserve forms with full structure (including IDs if available)
            forms_structured = []
            raw_forms = ing.get("forms", []) or []
            for form in raw_forms:
                if isinstance(form, dict):
                    forms_structured.append({
                        "name": form.get("name", ""),
                        "ingredientId": form.get("ingredientId"),
                        "order": form.get("order"),
                        "prefix": form.get("prefix"),
                        "percent": form.get("percent")
                    })
                elif isinstance(form, str):
                    forms_structured.append({"name": form})

            # Check if this ingredient is an additive (add metadata flag for enrichment phase)
            processed_name_check = self.matcher.preprocess_text(name)
            is_additive = False
            additive_type = None
            if processed_name_check in self.other_ingredients_lookup:
                additive_data = self.other_ingredients_lookup[processed_name_check]
                is_additive = additive_data.get("is_additive", False)
                if is_additive:
                    additive_type = additive_data.get("additive_type")

            # Build result - CLEANING ONLY (no enrichment)
            result = {
                # Original DSLD identifiers (PRESERVE)
                "ingredientId": ing.get("ingredientId"),
                "uniiCode": ing.get("uniiCode"),
                "order": ing.get("order", 0),

                # PROVENANCE FIELDS (Pipeline Hardening Phase 2)
                # raw_source_text: Exact substring from DSLD, set once, never modified
                "raw_source_text": name,
                # raw_source_path: Source section (inactive for other ingredients)
                "raw_source_path": "inactiveIngredients",
                # normalized_key: Stable key for dedup/tracking, computed ONCE
                "normalized_key": norm_module.make_normalized_key(name),

                # Basic ingredient info
                "name": name,
                "standardName": standard_name,  # From our database mapping
                "ingredientGroup": ing.get("ingredientGroup"),  # PRESERVE from DSLD (even if wrong)

                # Forms (PRESERVE full structure with IDs)
                "forms": forms_structured if forms_structured else [],
                "alternateNames": ing.get("alternateNames", []) or [],

                # Mapping status (basic cleaning metadata)
                "mapped": is_mapped,

                # Hierarchy classification for scoring (source/summary/component)
                "hierarchyType": self._classify_hierarchy_type(name)
            }

            # Add additive metadata flag (for enrichment phase to use)
            if is_additive:
                result["isAdditive"] = True
                if additive_type:
                    result["additiveType"] = additive_type

            # NO ENRICHMENT FIELDS - NO category, isHarmful, harmfulCategory, riskLevel,
            # allergen, allergenType, allergenSeverity, transparency, vague_disclosure, etc.
            # Those ALL belong in the enrichment phase

            processed.append(result)

        return processed

    def _dedupe_inactive_ingredients(
        self, active_ingredients: List[Dict], inactive_ingredients: List[Dict]
    ) -> List[Dict]:
        """
        A4: Deduplicate inactive ingredients that also appear in active ingredients.

        If an ingredient appears in both active (Supplement Facts) and inactive
        (Other Ingredients), keep only the active record since it has dose/unit info.

        Args:
            active_ingredients: Processed active ingredients list
            inactive_ingredients: Processed inactive ingredients list

        Returns:
            Filtered inactive ingredients list with duplicates removed
        """
        if not active_ingredients or not inactive_ingredients:
            return inactive_ingredients

        # Build a set of normalized active ingredient names for fast lookup
        active_names = set()
        for ing in active_ingredients:
            # Use standardName if available, else fall back to name
            std_name = ing.get("standardName", "")
            name = ing.get("name", "")

            if std_name:
                active_names.add(self.matcher.preprocess_text(std_name))
            if name:
                active_names.add(self.matcher.preprocess_text(name))

        # Filter out inactive ingredients that match active ingredients
        deduplicated = []
        duplicates_removed = 0

        for ing in inactive_ingredients:
            std_name = ing.get("standardName", "")
            name = ing.get("name", "")

            # Check if this inactive ingredient matches any active ingredient
            is_duplicate = False

            if std_name and self.matcher.preprocess_text(std_name) in active_names:
                is_duplicate = True
            elif name and self.matcher.preprocess_text(name) in active_names:
                is_duplicate = True

            if is_duplicate:
                duplicates_removed += 1
                logger.debug(
                    "Deduped inactive ingredient '%s' (also in active ingredients)",
                    name or std_name
                )
                # Optionally: flag the active ingredient that it was also listed
                # in other ingredients (for transparency reporting)
            else:
                deduplicated.append(ing)

        if duplicates_removed > 0:
            logger.info(
                "Removed %d duplicate ingredients from inactive list (already in active)",
                duplicates_removed
            )

        return deduplicated

    # Include all other methods from the original normalizer
    # (I'll keep the existing methods for compatibility)

    def _safe_int(self, value: Any, field_name: str = "value", default: int = 0) -> int:
        """
        Safely convert value to integer with comprehensive error handling
        """
        # Handle None explicitly
        if value is None:
            logger.debug(f"NULL {field_name} converted to {default}")
            return default

        # Handle empty strings and "none"
        if isinstance(value, str):
            value = value.strip().lower()
            if not value or value == "none":
                logger.debug(f"Empty/none {field_name} converted to {default}")
                return default

        try:
            result = int(float(value))  # Handle "1.0" -> 1
            return result
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert {field_name} '{value}' to int: {e}. Using {default}")
            return default

    def _safe_float(self, value: Any, field_name: str = "value", default: float = 0.0) -> float:
        """
        Safely convert value to float with comprehensive error handling
        """
        # Handle None explicitly
        if value is None:
            logger.debug(f"NULL {field_name} converted to {default}")
            return default

        # Handle empty strings and "none"
        if isinstance(value, str):
            value = value.strip().lower()
            if not value or value == "none":
                logger.debug(f"Empty/none {field_name} converted to {default}")
                return default

        try:
            result = float(value)
            return result
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert {field_name} '{value}' to float: {e}. Using {default}")
            return default
    
    def _extract_field_value(self, field_data: Any) -> str:
        """Extract string value from field that can be either string or dict with langualCodeDescription"""
        if isinstance(field_data, str):
            return field_data
        elif isinstance(field_data, dict) and "langualCodeDescription" in field_data:
            return field_data["langualCodeDescription"]
        else:
            return str(field_data) if field_data else ""

    def _extract_forms_from_ingredient_name(self, ingredient_name: str) -> List[str]:
        """Extract form information from ingredient name for precise scoring"""
        name = ingredient_name.lower()
        extracted_forms = []

        # Enhanced parenthetical extraction for complex DSLD formats
        paren_matches = re.findall(r'\(([^)]+)\)', name)
        for match in paren_matches:
            clean_match = match.strip().lower()
            
            # Handle complex DSLD parenthetical formats like "Form: as D3 (Alt. Name: Cholecalciferol)"
            if "form:" in clean_match or "as " in clean_match:
                # Split on " and as " to handle multiple forms in one parenthetical
                # Example: "(as magnesium bisglycinate chelate, from algae, and as magnesium oxide)"
                as_parts = re.split(r',?\s+and\s+as\s+', clean_match)

                for part in as_parts:
                    # Extract after "as " or "form: as "
                    if "as " in part:
                        form_part = part.split("as ", 1)[1]
                        # Handle nested parentheses like "as D3 (Alt. Name: Cholecalciferol)"
                        if "(" in form_part:
                            form_part = form_part.split("(")[0].strip()

                        # CLEANUP: Remove source descriptors to get clean chemical form name
                        # Split on common separators: " and ", " from ", ",", " with "
                        # This ensures we extract just the form (e.g., "ascorbic acid")
                        # without source info (e.g., "from ferment media")
                        for separator in [" and ", " from ", " with "]:
                            if separator in form_part:
                                form_part = form_part.split(separator)[0]
                                break

                        # Remove trailing punctuation and whitespace
                        form_part = form_part.strip().rstrip('.,;:')

                        if form_part:  # Only add non-empty forms
                            extracted_forms.append(form_part)
            else:
                # Direct parenthetical forms - expanded list
                common_paren_forms = [
                    'cholecalciferol', 'ergocalciferol', 'ascorbic acid', 'calcium ascorbate',
                    'retinyl palmitate', 'retinyl acetate', 'beta-carotene', 
                    'd-alpha tocopherol', 'd-alpha tocopheryl acetate', 'dl-alpha tocopheryl acetate',
                    'methylcobalamin', 'cyanocobalamin', 'dibencozide', 'coenzyme b12'
                ]
                if clean_match in common_paren_forms:
                    extracted_forms.append(clean_match)
        
        # Extract form identifiers from the main name
        form_identifiers = []
        
        # Vitamin D forms
        if re.search(r'\b(?:vitamin\s*)?d3\b', name) or re.search(r'\bcholecalciferol\b', name):
            form_identifiers.append('D3')
            if 'cholecalciferol' not in extracted_forms:
                form_identifiers.append('cholecalciferol')
        elif re.search(r'\b(?:vitamin\s*)?d2\b', name) or re.search(r'\bergocalciferol\b', name):
            form_identifiers.append('D2')
            if 'ergocalciferol' not in extracted_forms:
                form_identifiers.append('ergocalciferol')
        
        # Vitamin C forms
        if re.search(r'\bascorbic\s*acid\b', name):
            form_identifiers.append('ascorbic acid')
        elif re.search(r'\bcalcium\s*ascorbate\b', name):
            form_identifiers.append('calcium ascorbate')
        elif re.search(r'\bmagnesium\s*ascorbate\b', name):
            form_identifiers.append('magnesium ascorbate')
        
        # Enhanced vitamin forms
        if re.search(r'\bretinyl\s*palmitate\b', name):
            form_identifiers.append('retinyl palmitate')
        if re.search(r'\bretinyl\s*acetate\b', name):
            form_identifiers.append('retinyl acetate')
        if re.search(r'\bbeta[\s-]*carotene\b', name):
            form_identifiers.append('beta-carotene')
        
        # Vitamin E forms
        if re.search(r'\bd[\s-]*alpha[\s-]*tocopherol\b', name):
            form_identifiers.append('d-alpha tocopherol')
        elif re.search(r'\bd[\s-]*alpha[\s-]*tocopheryl[\s-]*acetate\b', name):
            form_identifiers.append('d-alpha tocopheryl acetate')
        elif re.search(r'\bdl[\s-]*alpha[\s-]*tocopheryl[\s-]*acetate\b', name):
            form_identifiers.append('dl-alpha tocopheryl acetate')
        
        # B12 forms
        if re.search(r'\bmethylcobalamin\b', name):
            form_identifiers.append('methylcobalamin')
        elif re.search(r'\bcyanocobalamin\b', name):
            form_identifiers.append('cyanocobalamin')
        elif re.search(r'\bdibencozide\b', name) or re.search(r'\bcoenzyme\s*b12\b', name):
            form_identifiers.append('dibencozide')
        
        # Common mineral forms (existing)
        mineral_forms = ['bisglycinate', 'picolinate', 'citrate', 'glycinate', 'malate', 'taurate', 'carbonate', 'oxide']
        for mineral_form in mineral_forms:
            if re.search(rf'\b{mineral_form}\b', name):
                form_identifiers.append(mineral_form)
        
        # FIXED ISSUE #1: Sulfate forms detection
        sulfate_forms = ['sulfate', 'sulphate']  # Handle both spellings
        for sulfate_form in sulfate_forms:
            if re.search(rf'\b{sulfate_form}\b', name):
                form_identifiers.append('sulfate')
                break  # Only add sulfate once
        
        # FIXED ISSUE #2: HCl/Hydrochloride forms detection
        if re.search(r'\bhcl\b', name) or re.search(r'\bhydrochloride\b', name):
            form_identifiers.append('hydrochloride')
        
        # FIXED ISSUE #3: Extract forms detection
        if re.search(r'\bextract\b', name):
            form_identifiers.append('extract')
        
        # FIXED ISSUE #4: Standardized forms detection
        if re.search(r'\bstandardized\b', name) or re.search(r'\bstandardised\b', name):
            form_identifiers.append('standardized')
        
        # Chelated forms
        if re.search(r'\bchelate\b', name) or re.search(r'\bchelated\b', name):
            form_identifiers.append('chelated')
        
        # Organic/natural indicators
        if re.search(r'\borganic\b', name):
            form_identifiers.append('organic')
        if re.search(r'\bnatural\b', name) and not re.search(r'\bnatural\s+flavor', name):
            form_identifiers.append('natural')
        
        # Combine all extracted forms
        all_forms = extracted_forms + form_identifiers
        
        # Remove duplicates while preserving order
        seen = set()
        unique_forms = []
        for form in all_forms:
            if form not in seen:
                seen.add(form)
                unique_forms.append(form)
                
        return unique_forms
    
    def _validate_upc(self, upc: str) -> bool:
        """Validate UPC or SKU format based on retail standards"""
        from dsld_validator import DSLDValidator
        return DSLDValidator.validate_upc_sku(upc)
    
    def _generate_image_url(self, thumbnail: str, product_id: str) -> str:
        """Generate valid DSLD image URL"""
        if not product_id:
            return ""
        return DSLD_IMAGE_URL_TEMPLATE.format(product_id)
    
    def _extract_discontinued_date(self, events: List[Dict]) -> Optional[str]:
        """Extract discontinued date from events"""
        for event in events:
            if event.get("type") == "Off Market":
                date = event.get("date", "")
                if date:
                    return date + "T00:00:00Z"
        return None
    
    def _extract_net_contents(self, net_contents: List[Dict]) -> List[Dict]:
        """
        Preserve netContents array structure from raw DSLD data
        Returns: Array with order, quantity, unit, display fields
        """
        if not net_contents:
            return []

        # PRESERVE ORIGINAL STRUCTURE - NO TRANSFORMATION
        return net_contents
    
    def _process_contacts(self, contacts: List[Dict]) -> List[Dict]:
        """Process manufacturer contact information"""
        if not contacts:
            return []
        
        processed_contacts = []
        
        # Process all contacts (not just first one)
        for contact in contacts:
            # Handle both nested contactDetails and flat structure
            if "contactDetails" in contact:
                details = contact["contactDetails"]
                name = details.get("name", "")
                city = details.get("city", "")
                state = details.get("state", "")
                country = details.get("country", "")
                phone = details.get("phoneNumber", "")
                web = details.get("webAddress", "")
            else:
                # Flat structure (like our test data)
                name = contact.get("name", "")
                city = contact.get("city", "")
                state = contact.get("state", "")
                country = contact.get("country", "")
                phone = contact.get("phoneNumber", "")
                web = contact.get("webAddress", "")
                
            # Also preserve the type from flat structure if available
            contact_type = contact.get("type", "")
            
            # Look up manufacturer score
            manufacturer_score = None
            if name:
                # Search in top manufacturers database
                # Handle both array and object formats
                manufacturers = self.manufacturers_db
                if isinstance(self.manufacturers_db, dict):
                    manufacturers = self.manufacturers_db.get("manufacturers", [])
                
                for mfr in manufacturers:
                    mfr_name = mfr.get("standard_name", "")
                    if name.lower() in mfr_name.lower():
                        manufacturer_score = mfr.get("score_contribution", None)
                        break
            
            # Build processed contact
            processed_contact = {
                "name": name,
                "type": contact_type,
                "webAddress": web,
                "city": city,
                "state": state,
                "country": country,
                "phoneNumber": phone,
                "isGMP": False,  # Will be set from statements
                "manufacturerScore": manufacturer_score
            }
            
            processed_contacts.append(processed_contact)
        
        return processed_contacts
    
    def _process_quantity(self, quantities) -> Tuple[float, str, Optional[float], List[Dict]]:
        """
        Extract quantity, unit, daily value, and all quantity variants from various formats.

        P0.3: Lossless cleaning - preserve ALL quantity variants for multi-serving products.

        Returns:
            Tuple of (quantity, unit, daily_value, quantity_variants)
            - quantity: The primary/canonical quantity (first in list or adult default)
            - unit: The unit for the primary quantity
            - daily_value: The daily value percentage if available
            - quantity_variants: List of all quantity objects for different servings
        """
        # Handle different input formats robustly
        if not quantities:
            return 0.0, "unspecified", None, []

        # Case 1: Direct numeric value (int/float)
        if isinstance(quantities, (int, float)):
            variant = {"quantity": float(quantities), "unit": "unspecified", "context": "direct"}
            return float(quantities), "unspecified", None, [variant]

        # Case 2: String value
        if isinstance(quantities, str):
            qty = self._safe_float(quantities)
            variant = {"quantity": qty, "unit": "unspecified", "context": "string"}
            return qty, "unspecified", None, [variant]

        # Case 3: Single dict object
        if isinstance(quantities, dict):
            quantity = self._safe_float(quantities.get("quantity", quantities.get("value", 0)))
            unit = quantities.get("unit", "unspecified")

            # Get daily value if available
            daily_value = None
            dv_groups = quantities.get("dailyValueTargetGroup", [])
            if dv_groups and isinstance(dv_groups, list):
                daily_value = self._safe_float(dv_groups[0].get("percent", 0))

            # Build variant with context
            variant = {
                "quantity": quantity,
                "unit": unit,
                "context": "single_dict"
            }
            if daily_value:
                variant["daily_value"] = daily_value

            return quantity, unit, daily_value, [variant]

        # Case 4: List of quantity objects (original expected format)
        # P0.3: Preserve ALL variants
        if isinstance(quantities, list):
            quantity_variants = []

            for idx, q in enumerate(quantities):
                if isinstance(q, dict):
                    qty = self._safe_float(q.get("quantity", q.get("value", 0)))
                    u = q.get("unit", "unspecified")

                    # Get daily value if available
                    dv = None
                    dv_groups = q.get("dailyValueTargetGroup", [])
                    if dv_groups and isinstance(dv_groups, list):
                        dv = self._safe_float(dv_groups[0].get("percent", 0))

                    # Extract serving context from dailyValueTargetGroup if available
                    context = None
                    serving_size_qty = None
                    serving_size_unit = None
                    if dv_groups and isinstance(dv_groups, list) and len(dv_groups) > 0:
                        dv_group = dv_groups[0]
                        serving_size_qty = dv_group.get("servingSizeQuantity")
                        serving_size_unit = dv_group.get("servingSizeUnitOfMeasure")
                        # Try to extract target group context
                        target_group = dv_group.get("targetGroup", "")
                        if target_group:
                            context = target_group

                    variant = {
                        "quantity": qty,
                        "unit": u,
                        "index": idx
                    }
                    if dv:
                        variant["daily_value"] = dv
                    if serving_size_qty:
                        variant["serving_size_quantity"] = serving_size_qty
                    if serving_size_unit:
                        variant["serving_size_unit"] = serving_size_unit
                    if context:
                        variant["context"] = context

                    quantity_variants.append(variant)
                else:
                    # List contains non-dict values, treat as direct numeric
                    qty = self._safe_float(q)
                    quantity_variants.append({
                        "quantity": qty,
                        "unit": "unspecified",
                        "index": idx
                    })

            # Take first quantity as canonical (usually standard serving)
            # P0.3: Enrichment phase will select canonical based on user groups
            if quantity_variants:
                first = quantity_variants[0]
                quantity = first["quantity"]
                unit = first["unit"]
                daily_value = first.get("daily_value")

                # NOTE: IU conversion is vitamin-specific and complex:
                # - Vitamin D: 1 IU = 0.025 mcg
                # - Vitamin A: 1 IU = 0.3 mcg (retinol) or 0.6 mcg (beta-carotene)
                # - Vitamin E: 1 IU ≈ 0.67 mg (d-alpha-tocopherol)
                # Leaving IU values as-is; enrichment phase handles conversions with ingredient context.

                return quantity, unit, daily_value, quantity_variants
            else:
                return 0.0, "unspecified", None, []

        # Fallback for unexpected types
        logger.warning(f"Unexpected quantity format: {type(quantities)} - {quantities}")
        return 0.0, "unspecified", None, []
    def _extract_ingredient_features(self, notes: str) -> Dict[str, Any]:
        """Extract features from ingredient notes"""
        features = {
            "phrases": [],
            "standardized": False,
            "standardization_percent": None,
            "natural_source": None
        }
        
        if not notes:
            return features
        
        # Extract standardization
        for pattern in STANDARDIZATION_PATTERNS:
            match = re.search(pattern, notes, re.IGNORECASE)
            if match:
                features["standardized"] = True
                try:
                    features["standardization_percent"] = self._safe_float(match.group(1)) if len(match.groups()) >= 1 else 0.0
                    features["phrases"].append(match.group(0))
                except IndexError:
                    features["standardization_percent"] = 0.0
                    features["phrases"].append(match.group(0) if match else "")
                break
        
        # Extract natural source
        for pattern in NATURAL_SOURCE_PATTERNS:
            match = re.search(pattern, notes, re.IGNORECASE)
            if match:
                try:
                    features["natural_source"] = match.group(0)
                    features["phrases"].append(match.group(0))
                except IndexError:
                    features["natural_source"] = ""
                break
        
        # Check for proprietary blend
        for indicator in PROPRIETARY_BLEND_INDICATORS:
            if indicator.lower() in notes.lower():
                features["phrases"].append(indicator)
        
        # Check for delivery enhancement
        for pattern in DELIVERY_ENHANCEMENT_PATTERNS:
            if re.search(pattern, notes, re.IGNORECASE):
                features["phrases"].append(pattern)
        
        return features
    
    def _process_statements(self, statements: List[Dict]) -> List[Dict]:
        """
        Process statements - CLEANING ONLY
        Preserve original DSLD structure without enrichment
        """
        processed = []

        for stmt in statements:
            # PRESERVE ORIGINAL STRUCTURE ONLY - NO ENRICHMENT
            processed.append({
                "type": stmt.get("type", ""),
                "notes": stmt.get("notes", "")
            })

        return processed
    
    def _process_claims(self, claims: List[Dict]) -> List[Dict]:
        """
        Process claims - CLEANING ONLY
        Preserve original DSLD Langual code structure without enrichment
        """
        processed = []

        for claim in claims:
            # PRESERVE ORIGINAL STRUCTURE ONLY - NO ENRICHMENT
            processed.append({
                "langualCode": claim.get("langualCode", ""),
                "langualCodeDescription": claim.get("langualCodeDescription", "")
            })

        return processed
    
    def _process_serving_sizes(self, serving_sizes: List[Dict]) -> List[Dict]:
        """Process serving size information"""
        processed = []
        
        for serving in serving_sizes:
            min_qty = self._safe_float(serving.get("minQuantity", DEFAULT_SERVING_SIZE))
            max_qty = self._safe_float(serving.get("maxQuantity", min_qty))
            
            processed.append({
                "minQuantity": min_qty,
                "maxQuantity": max_qty,
                "unit": serving.get("unit", "serving"),
                "minDailyServings": self._safe_int(serving.get("minDailyServings", DEFAULT_DAILY_SERVINGS)),
                "maxDailyServings": self._safe_int(serving.get("maxDailyServings", DEFAULT_DAILY_SERVINGS)),
                "normalizedServing": max_qty  # Use max as normalized
            })

        return processed
    def _generate_label_text(self, active_ingredients: List[Dict], 
                           inactive_ingredients: List[Dict], 
                           statements: List[Dict]) -> str:
        """Generate searchable label text"""
        text_parts = []
        
        # Add ingredient names
        for ing in active_ingredients:
            text_parts.append(ing.get("name", ""))
            # Extract form names from forms array
            forms_data = ing.get("forms", [])
            if forms_data and isinstance(forms_data, list):
                for form_dict in forms_data:
                    if isinstance(form_dict, dict) and "name" in form_dict:
                        form_name = form_dict.get("name", "")
                        if form_name:
                            text_parts.append(form_name)
            text_parts.append(ing.get("notes", ""))
        
        for ing in inactive_ingredients:
            text_parts.append(ing.get("name", ""))
        
        # Add statement notes
        for stmt in statements:
            text_parts.append(stmt.get("notes", ""))
        
        # Clean and join
        cleaned_parts = [p.strip() for p in text_parts if p]
        return " ".join(cleaned_parts)

    def _extract_original_label_text(self, raw_data: Dict[str, Any]) -> str:
        """
        Extract original raw text from statements for enrichment text parsing.
        Preserves unprocessed text for downstream analysis.
        """
        text_parts = []

        # Extract all statement notes from raw data
        raw_statements = raw_data.get("statements", []) or []
        for stmt in raw_statements:
            if isinstance(stmt, dict):
                notes = stmt.get("notes", "")
                if notes:
                    text_parts.append(notes)

        # Join all text
        return " ".join(text_parts).strip()

    def _parse_botanical_details(self, notes: str) -> Dict[str, Any]:
        """
        Parse botanical details from ingredient notes field.
        Extracts: plantPart, genus, species, harvestMethod, form

        Example notes:
        "Sage PlantPart: leaves Genus: Salvia Species: officinalis Note: ecologically harvested"
        "Peppermint leaf essential oil PlantPart: leaf Genus: Mentha Species: piperita"
        """
        if not notes:
            return {}

        details = {}

        # Extract plant part (case-insensitive)
        plant_part_match = re.search(r'PlantPart:\s*([^,\n]+?)(?:\s+(?:Genus|Species|Note|Form)|$)', notes, re.I)
        if plant_part_match:
            details["plantPart"] = plant_part_match.group(1).strip()

        # Extract genus
        genus_match = re.search(r'Genus:\s*([^,\s]+)', notes, re.I)
        if genus_match:
            details["genus"] = genus_match.group(1).strip()

        # Extract species
        species_match = re.search(r'Species:\s*([^,\s]+)', notes, re.I)
        if species_match:
            details["species"] = species_match.group(1).strip()

        # Extract harvest method from Note: field
        note_match = re.search(r'Note:\s*(.+?)(?:\s+PlantPart:|$)', notes, re.I)
        if note_match:
            harvest_note = note_match.group(1).strip()
            # Common harvest methods
            if re.search(r'ecologically\s+harvested|ecological\s+harvest', harvest_note, re.I):
                details["harvestMethod"] = "ecologically harvested"
            elif re.search(r'organic|Organic ingredient', harvest_note, re.I):
                details["harvestMethod"] = harvest_note.strip()
            elif harvest_note:
                details["harvestMethod"] = harvest_note

        # Extract form (e.g., "essential oil", "freeze dried extract", "extract")
        # Look for form patterns in the ingredient name or notes
        form_patterns = [
            r'\b(essential oil)\b',
            r'\b(freeze[- ]dried extract)\b',
            r'\b(dried extract)\b',
            r'\b(extract)\b',
            r'\b(powder)\b',
            r'\b(oil)\b',
            r'\b(gel)\b'
        ]
        for pattern in form_patterns:
            form_match = re.search(pattern, notes, re.I)
            if form_match:
                details["form"] = form_match.group(1).lower()
                break

        return details

    def _calculate_transparency_metrics(self, proprietary_blends: List[Dict], active_ingredients: List[Dict]) -> Dict[str, Any]:
        """
        Calculate transparency metrics for product metadata.
        Provides visibility into ingredient disclosure quality.
        """
        has_proprietary_blend = len(proprietary_blends) > 0

        if not has_proprietary_blend:
            return {
                "hasProprietaryBlend": False,
                "blendTransparency": "full",
                "disclosedIngredients": len(active_ingredients),
                "undisclosedQuantities": 0,
                "transparencyScore": 100.0
            }

        # Count disclosed vs undisclosed ingredients
        total_nested = sum(len(b.get("nestedIngredients", [])) for b in proprietary_blends)
        disclosed_quantities = sum(
            1 for b in proprietary_blends
            for n in b.get("nestedIngredients", [])
            if n.get("quantityProvided", False)
        )
        undisclosed_quantities = total_nested - disclosed_quantities

        # Determine blend transparency level
        if disclosed_quantities == total_nested:
            blend_transparency = "full"
            transparency_score = 100.0
        elif disclosed_quantities > 0:
            blend_transparency = "partial"
            transparency_score = 50.0 + (disclosed_quantities / total_nested * 50)
        else:
            blend_transparency = "low"
            # Score based on whether names are disclosed (even without quantities)
            transparency_score = 30.0 if total_nested > 0 else 10.0

        return {
            "hasProprietaryBlend": True,
            "blendTransparency": blend_transparency,
            "disclosedIngredients": total_nested,
            "undisclosedQuantities": undisclosed_quantities,
            "transparencyScore": round(transparency_score, 1)
        }

    def _extract_storage(self, statements: List[Dict]) -> List[str]:
        """Extract storage instructions from statements"""
        storage = []
        for stmt in statements:
            if stmt.get("type") == "Storage":
                notes = stmt.get("notes", "")
                if notes:
                    storage.append(notes.strip())
        return storage

    def _extract_directions(self, statements: List[Dict]) -> str:
        """Extract usage directions from statements"""
        for stmt in statements:
            if "Suggested" in stmt.get("type", "") or "Usage" in stmt.get("type", "") or "Directions" in stmt.get("type", ""):
                notes = stmt.get("notes", "")
                if notes:
                    # Extract just the directions part
                    directions_match = re.search(r'(?:Suggested Use|Directions)[:\s]+(.*?)(?:\n|$)', notes, re.I | re.S)
                    if directions_match:
                        return directions_match.group(1).strip()
                    return notes.strip()
        return ""

    def _extract_origin(self, label_text: str, contacts: List[Dict] = None) -> List[str]:
        """
        Extract origin/manufacturing location claims from label text and contacts

        Args:
            label_text: Text from statements
            contacts: Contact information from raw DSLD data

        Returns:
            List of origin/manufacturing location claims
        """
        origins = []

        # Extract from label text
        if "Made in the USA" in label_text or "Made in USA" in label_text:
            origins.append("Made in USA")
        if "Made in America" in label_text:
            origins.append("Made in America")
        if re.search(r"Manufactured in.*USA", label_text, re.I):
            origins.append("Manufactured in USA")

        # Extract from contacts
        if contacts:
            for contact in contacts:
                # Ensure contact_text and country are strings, not None
                contact_text = contact.get("text") or ""
                country = contact.get("country") or ""

                # Only process if we have actual text
                if contact_text:
                    # Check for "Product of X" in contact text
                    product_of_match = re.search(r"Product of\s+([A-Za-z\s]+?)(?:\s+Manufactured|$)", contact_text, re.I)
                    if product_of_match:
                        country_name = product_of_match.group(1).strip()
                        origins.append(f"Product of {country_name}")

                    # Check for "Manufactured in X by Y" in contact text
                    mfg_match = re.search(r"Manufactured (?:in|for.*by)\s+([A-Za-z\s,]+?)(?:\s+by|$)", contact_text, re.I)
                    if mfg_match:
                        location = mfg_match.group(1).strip()
                        # If it's a city/region (like "Tuscany"), append " by Company"
                        contact_name = contact.get("name")
                        if contact_name:
                            origins.append(f"Manufactured in {location} by {contact_name}")
                        else:
                            origins.append(f"Manufactured in {location}")

                # Also check country field for manufacturer type contacts
                if country and "Manufacturer" in (contact.get("types") or []):
                    if country not in str(origins):  # Avoid duplicates
                        origins.append(f"Manufactured in {country}")

        return list(set(origins))

    def _extract_clean_claims(self, label_text: str, allergen_free_list: List[str] = None) -> List[str]:
        """Extract clean label claims from label text

        Args:
            label_text: Raw label text to parse
            allergen_free_list: List of allergen-free items detected (e.g., ['gluten', 'soy', 'dairy'])

        Returns:
            List of clean label claims
        """
        claims = []

        # Parse compound "No X, Y, Z" statements (e.g., "No salt, yeast, wheat, soy, dairy products, artificial colors, flavors, or preservatives")
        no_compound_match = re.search(r'No\s+([^.!?]+(?:,\s*(?:or\s+)?[^.!?]+)+)', label_text, re.I)
        if no_compound_match:
            items_text = no_compound_match.group(1)
            # Split by comma or "or"
            items = re.split(r',\s*(?:or\s+)?|\s+or\s+', items_text)

            # Check if "artificial" appears in the compound statement context
            has_artificial_context = 'artificial' in items_text.lower()

            for item in items:
                item = item.strip().lower()
                if 'salt' in item:
                    claims.append("No Salt")
                if 'yeast' in item and 'yeast' not in [c.lower() for c in claims]:
                    claims.append("Yeast Free")
                if 'wheat' in item:
                    claims.append("No Wheat")
                if 'soy' in item:
                    claims.append("Soy Free")
                if 'dairy' in item or 'milk' in item:
                    claims.append("Dairy Free")

                # Handle "artificial colors" and bare "colors" if artificial context exists
                if 'artificial color' in item or 'artificial dye' in item:
                    claims.append("No Artificial Colors")
                elif has_artificial_context and ('color' in item or 'dye' in item):
                    if "No Artificial Colors" not in claims:
                        claims.append("No Artificial Colors")

                # Handle "artificial flavors" and bare "flavors" if artificial context exists
                if 'artificial flavor' in item:
                    claims.append("No Artificial Flavors")
                elif has_artificial_context and 'flavor' in item:
                    if "No Artificial Flavors" not in claims:
                        claims.append("No Artificial Flavors")

                if 'preservative' in item:
                    claims.append("No Preservatives")

        # Standard pattern matching for individual claims
        claims_map = {
            "No Artificial Colors": ["No Artificial Colors", "No Artificial Coloring", "No Artificial Dyes"],
            "No Artificial Flavors": ["No Artificial Flavors", "No Artificial Flavoring"],
            "No Preservatives": ["No Preservatives", "Preservative Free"],
            "No Artificial Dyes or Preservatives": ["No Artificial Dyes or Preservatives"],
            "No Salt": ["No Salt", "Salt Free", "Sodium Free"],
            "No Wheat": ["No Wheat", "Wheat Free"],
            "Gluten Free": ["No Gluten", "Gluten Free", "Gluten-Free"],
            "Dairy Free": ["No Dairy", "Dairy Free", "Dairy-Free", "No Milk"],
            "Soy Free": ["No Soy", "Soy Free", "Soy-Free"],
            "Yeast Free": ["Yeast Free", "No Yeast"],
            "No Sugar": ["No Sugar", "Sugar Free"],
            "Non-GMO": ["Non-GMO", "Non GMO", "GMO Free"]
        }

        for canonical, patterns in claims_map.items():
            for pattern in patterns:
                if pattern in label_text:
                    if canonical not in claims:  # Avoid duplicates
                        claims.append(canonical)
                    break

        # Add allergen-free claims if provided
        if allergen_free_list:
            allergen_claim_map = {
                "gluten": "Gluten Free",
                "dairy": "Dairy Free",
                "soy": "Soy Free",
                "nut": "Nut Free",
                "egg": "Egg Free",
                "shellfish": "Shellfish Free",
                "peanut": "Peanut Free",
                "yeast": "Yeast Free"
            }
            for allergen in allergen_free_list:
                if allergen in allergen_claim_map:
                    claim = allergen_claim_map[allergen]
                    if claim not in claims:  # Avoid duplicates
                        claims.append(claim)

        return list(set(claims))
    def get_unmapped_snapshot(self) -> set:
        """Get a snapshot of current unmapped ingredient names for delta tracking.

        Returns:
            Set of unmapped ingredient names currently tracked
        """
        return set(self.unmapped_ingredients.keys())

    def get_unmapped_delta(self, previous_snapshot: set) -> Dict[str, Any]:
        """Get unmapped ingredients added since the previous snapshot.

        Args:
            previous_snapshot: Set of ingredient names from previous snapshot

        Returns:
            Dict with newly unmapped ingredients and their details
        """
        current_snapshot = set(self.unmapped_ingredients.keys())
        new_unmapped = current_snapshot - previous_snapshot

        unmapped_with_details = []
        for name in new_unmapped:
            details = self.unmapped_details.get(name, {})
            unmapped_with_details.append({
                "name": name,
                "occurrences": self.unmapped_ingredients[name],
                "processedName": details.get("processed_name", ""),
                "forms": details.get("forms", []),
                "variationsTried": details.get("variations_tried", []),
                "isActive": details.get("is_active", False),
                "suggestedMapping": {
                    "needsReview": True,
                    "category": "unknown",
                    "confidence": "low"
                }
            })

        return {
            "unmapped": unmapped_with_details,
            "stats": {
                "totalUnmapped": len(new_unmapped),
                "totalOccurrences": sum(self.unmapped_ingredients[name] for name in new_unmapped),
                "enhancedProcessing": True,
                "fuzzyMatchingEnabled": FUZZY_AVAILABLE
            }
        }

    def get_enhanced_unmapped_summary(self) -> Dict[str, Any]:
        """Get detailed summary of unmapped ingredients with context"""
        unmapped_with_details = []

        for name, count in self.unmapped_ingredients.most_common():
            details = self.unmapped_details.get(name, {})
            unmapped_with_details.append({
                "name": name,
                "occurrences": count,
                "processedName": details.get("processed_name", ""),
                "forms": details.get("forms", []),
                "variationsTried": details.get("variations_tried", []),
                "isActive": details.get("is_active", False),  # Include active/inactive status
                "suggestedMapping": {
                    "needsReview": True,
                    "category": "unknown",
                    "confidence": "low"
                }
            })

        return {
            "unmapped": unmapped_with_details,
            "stats": {
                "totalUnmapped": len(self.unmapped_ingredients),
                "totalOccurrences": sum(self.unmapped_ingredients.values()),
                "enhancedProcessing": True,
                "fuzzyMatchingEnabled": FUZZY_AVAILABLE
            }
        }
    
    def process_and_save_unmapped_tracking(self):
        """Process unmapped ingredients and save separate active/inactive tracking files"""
        if not self.unmapped_tracker:
            logger.warning("Unmapped tracker not initialized. Call set_output_directory() first.")
            return
        
        # Separate active and inactive ingredients
        active_ingredients = set()
        unmapped_data = {}
        
        for name, count in self.unmapped_ingredients.items():
            details = self.unmapped_details.get(name, {})
            is_active = details.get("is_active", False)
            
            if is_active:
                active_ingredients.add(name)
            
            unmapped_data[name] = count
        
        # Process with the tracker
        self.unmapped_tracker.process_unmapped_ingredients(unmapped_data, active_ingredients)
        
        # Save the tracking files
        self.unmapped_tracker.save_tracking_files()
        
        return {
            "active_count": len(active_ingredients),
            "inactive_count": len(unmapped_data) - len(active_ingredients),
            "total_count": len(unmapped_data)
        }
    
    def _is_nutrition_fact(self, name: str, ingredient_group: str = None, unit: str = None) -> bool:
        """
        Check if ingredient name is a label phrase or nutrition fact to exclude.

        Args:
            name: The ingredient name
            ingredient_group: The ingredientGroup field from DSLD (e.g., "Calories")
            unit: The unit field (e.g., "{Calories}", "{Gram(s)}")

        Returns:
            True if this should be excluded from ingredient processing
        """
        if not name:
            return False

        # A9: Check ingredientGroup - if it matches nutrition patterns, skip
        if ingredient_group:
            group_lower = ingredient_group.lower().strip()
            if group_lower in self._preprocessed_excluded_nutrition:
                logger.debug(f"Excluding via ingredientGroup: {name} (group: {ingredient_group})")
                return True

        # A9: Check unit patterns like {Calories}, {Gram(s)} - these indicate nutrition facts
        if unit:
            unit_lower = unit.lower().strip()
            # Units in curly braces are typically nutrition fact indicators
            if unit_lower.startswith("{") and unit_lower.endswith("}"):
                # Extract the content inside braces
                inner_unit = unit_lower[1:-1].strip()
                if inner_unit in ["calories", "calorie", "kcal", "cal", "gram", "grams", "gram(s)"]:
                    logger.debug(f"Excluding via unit pattern: {name} (unit: {unit})")
                    return True

        # Preprocess the name for comparison
        processed_name = self.matcher.preprocess_text(name)

        # Check against preprocessed excluded nutrition facts
        if processed_name in self._preprocessed_excluded_nutrition:
            return True

        # Check against preprocessed label phrases
        if processed_name in self._preprocessed_excluded_labels:
            logger.debug(f"Excluding label phrase: {name}")
            return True

        # Enhanced pattern matching using ENHANCED_EXCLUSION_PATTERNS from constants
        name_lower = name.lower()

        # Use the enhanced patterns from constants for comprehensive exclusion
        for pattern in ENHANCED_EXCLUSION_PATTERNS:
            if re.search(pattern, name_lower):
                logger.debug(f"Excluding via enhanced pattern: {name}")
                return True

        # All pattern-based exclusions are now handled by ENHANCED_EXCLUSION_PATTERNS

        return False

    def _is_label_header(self, name: str) -> bool:
        """
        Check if ingredient name is a label header like 'Less than 2% of:' that may contain
        real ingredients in its forms array.

        These should be skipped as ingredients themselves, but their forms should be extracted.

        Args:
            name: The ingredient name

        Returns:
            True if this is a structural header (not an actual ingredient)
        """
        if not name:
            return False

        name_lower = name.lower().strip()

        # A3: Patterns for structural headers that contain real ingredients in forms
        header_patterns = [
            r"^less\s+than\s+\d+%\s+of:?$",
            r"^contains?\s+less\s+than\s+\d+%\s+of:?$",
            r"^contains?\s*<?\s*\d+%\s+of:?$",
            r"^<\s*\d+%\s+of:?$",
            r"^\d+%\s+or\s+less\s+of:?$",
            r"^contains?\s+\d+%\s+or\s+less\s+of:?$",
            r"^may\s+contain\s+one\s+or\s+more\s+of(\s+the\s+following)?:?$",
            r"^contains?\s+one\s+or\s+more\s+of(\s+the\s+following)?:?$",
        ]

        for pattern in header_patterns:
            if re.match(pattern, name_lower):
                return True

        return False
    
    def _is_proprietary_blend_name(self, name: str) -> bool:
        """Check if ingredient name contains proprietary blend indicators"""
        if not name:
            return False

        name_lower = name.lower()

        # Check against known proprietary blend indicators
        for indicator in PROPRIETARY_BLEND_INDICATORS:
            if indicator.lower() in name_lower:
                logger.debug("Found proprietary blend indicator '%s' in '%s'", indicator, name)
                return True

        return False
    
    def _determine_disclosure_level(self, name: str, quantity: float, unit: str, nested_ingredients: List[Dict]) -> Optional[str]:
        """
        Determine the disclosure level of a proprietary blend
        
        Returns:
            'full' - All ingredients have specific quantities
            'partial' - Some ingredients have quantities, some don't
            'none' - Only total blend weight given, no individual quantities
            None - Not a proprietary blend
        """
        # Check if this is actually a blend
        if not (self._is_proprietary_blend_name(name) or unit == "NP" or quantity == 0):
            # Also check if it has nested ingredients (could be a blend even without keyword)
            if not nested_ingredients:
                return None

        # If no nested ingredients, it's a proprietary blend with no disclosure
        # This includes:
        # 1. Ingredients with proprietary keywords in name
        # 2. Ingredients marked proprietary by unit="NP" or quantity=0
        # In both cases, if there are no nested ingredients, disclosure is "none"
        if not nested_ingredients:
            return "none"  # No ingredient breakdown = no disclosure
        
        # Check disclosure level based on nested ingredients
        has_quantities = []
        for nested_ing in nested_ingredients:
            # Handle quantity as list format (DSLD uses list of quantity objects)
            quantity_list = nested_ing.get("quantity", [])
            nested_qty = 0
            nested_unit = ""
            
            if isinstance(quantity_list, list) and quantity_list:
                # Get first quantity entry
                qty_entry = quantity_list[0] if quantity_list else {}
                nested_qty = qty_entry.get("quantity", 0) if isinstance(qty_entry.get("quantity"), (int, float)) else 0
                nested_unit = qty_entry.get("unit", "")
            elif isinstance(quantity_list, (int, float)):
                nested_qty = quantity_list
                nested_unit = nested_ing.get("unit", "")
            
            # Check if nested ingredient has a real quantity
            if nested_qty > 0 and nested_unit not in ["NP", "", None]:
                has_quantities.append(True)
            else:
                has_quantities.append(False)
        
        # Determine disclosure level
        if all(has_quantities) and len(has_quantities) > 0:
            return "full"  # All nested ingredients have quantities
        elif any(has_quantities):
            return "partial"  # Some have quantities, some don't
        else:
            return "none"  # No individual quantities provided

    def _calculate_transparency_percentage(self, nested_ingredients: List[Dict]) -> float:
        """
        Calculate transparency percentage for partial disclosure blends
        Returns 0-100 percentage of ingredients with disclosed quantities
        """
        if not nested_ingredients:
            return 0.0

        disclosed_count = 0
        total_count = len(nested_ingredients)

        for nested_ing in nested_ingredients:
            # Extract quantity using same logic as disclosure determination
            quantity_list = nested_ing.get("quantity", [])
            nested_qty = 0
            nested_unit = ""

            if isinstance(quantity_list, list) and quantity_list:
                qty_entry = quantity_list[0] if quantity_list else {}
                nested_qty = qty_entry.get("quantity", 0) if isinstance(qty_entry.get("quantity"), (int, float)) else 0
                nested_unit = qty_entry.get("unit", "")
            elif isinstance(quantity_list, (int, float)):
                nested_qty = quantity_list
                nested_unit = nested_ing.get("unit", "")

            # Count as disclosed if has real quantity
            if nested_qty > 0 and nested_unit not in ["NP", "", None]:
                disclosed_count += 1

        transparency_percentage = (disclosed_count / total_count) * 100
        logger.debug(f"Transparency: {disclosed_count}/{total_count} = {transparency_percentage:.1f}%")

        return round(transparency_percentage, 1)

    def _extract_nutritional_amount(self, ingredient: Dict) -> Optional[Dict]:
        """Extract amount information from ingredient for nutritional warnings"""
        # First check the quantity field
        quantity = ingredient.get("quantity", [])
        if quantity and isinstance(quantity, list) and len(quantity) > 0:
            q = quantity[0]
            if isinstance(q, dict):
                amount = q.get("amount")
                unit = q.get("unit", "").lower()
                if amount is not None and amount > 0:
                    return {"amount": amount, "unit": unit}
        
        # Then check forms
        forms = ingredient.get("forms", [])
        for form in forms:
            amount = form.get("amount")
            unit = form.get("unit", "").lower()
            if amount is not None and amount > 0:
                return {"amount": amount, "unit": unit}
        
        return None
    
    def _convert_to_standard_unit(self, amount: float, unit: str, conversions: Dict[str, float]) -> float:
        """Convert amount to standard unit using conversion factors"""
        unit_lower = unit.lower().strip()
        
        # Look for unit in conversions
        for conv_unit, factor in conversions.items():
            if conv_unit in unit_lower:
                return amount * factor
        
        # If no conversion found, assume it's already in the standard unit
        return amount
    
