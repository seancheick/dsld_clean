"""
Enhanced DSLD Data Normalizer Module
Improved ingredient mapping with fuzzy matching, better preprocessing, and expanded aliases
"""
import re
import json
import logging
import string
import os
from typing import Dict, List, Tuple, Optional, Any, Set
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict
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
    NON_HARMFUL_ADDITIVES,
    ALLERGENS,
    TOP_MANUFACTURERS,
    PROPRIETARY_BLENDS,
    EXCLUDED_NUTRITION_FACTS,
    EXCLUDED_LABEL_PHRASES,
    STANDARDIZED_BOTANICALS,
    BANNED_RECALLED,
    PASSIVE_INACTIVE_INGREDIENTS,
    BOTANICAL_INGREDIENTS,
    ENHANCED_DELIVERY,
    UNIT_CONVERSIONS,
    DSLD_IMAGE_URL_TEMPLATE,
    CERTIFICATION_PATTERNS,
    ALLERGEN_FREE_PATTERNS,
    UNSUBSTANTIATED_CLAIM_PATTERNS,
    NATURAL_SOURCE_PATTERNS,
    STANDARDIZATION_PATTERNS,
    PROPRIETARY_BLEND_INDICATORS,
    DELIVERY_ENHANCEMENT_PATTERNS,
    DEFAULT_STATUS,
    DOSE_PATTERN,
    FORM_QUALIFIERS,
    COMMA_SPLIT_PATTERN,
    DEFAULT_SERVING_SIZE,
    DEFAULT_DAILY_SERVINGS,
    EXCLUDED_NUTRITION_FACTS,
    NUTRITIONAL_WARNING_FIELDS
)

# Import the UnmappedIngredientTracker
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unmapped_ingredient_tracker import UnmappedIngredientTracker

logger = logging.getLogger(__name__)


class EnhancedIngredientMatcher:
    """Enhanced ingredient matching with fuzzy logic and comprehensive preprocessing"""

    def __init__(self):
        self.fuzzy_threshold = 85  # Minimum fuzzy match score
        self.partial_threshold = 90  # Minimum partial match score

        # OPTIMIZATION: Pre-compiled fuzzy patterns for common ingredients
        self._fuzzy_cache = {}  # Cache for fuzzy match results
        self._common_patterns = {}  # Pre-compiled patterns for common ingredients
        self._exact_match_cache = {}  # Cache for exact matches
        
        # Fuzzy matching blacklist - pairs that should NEVER be matched
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
            ("chromium", "vanadium"),       # Different trace minerals
        }
        
    def preprocess_text(self, text: str) -> str:
        """
        Comprehensive text preprocessing for better matching
        """
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower().strip()
        
        # Remove common parenthetical information
        text = re.sub(r'\([^)]*\)', '', text)
        
        # Remove brackets and their contents
        text = re.sub(r'\[[^\]]*\]', '', text)
        
        # Remove trademark symbols
        text = re.sub(r'[™®©]', '', text)
        
        # Remove extra whitespace and punctuation at ends
        text = text.strip(string.punctuation + string.whitespace)
        
        # Normalize multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Remove common prefixes/suffixes that don't affect matching
        prefixes_to_remove = ['dl-', 'd-', 'l-', 'natural ', 'synthetic ', 'organic ']
        for prefix in prefixes_to_remove:
            if text.startswith(prefix):
                text = text[len(prefix):]
        
        suffixes_to_remove = [' extract', ' powder', ' oil', ' concentrate']
        for suffix in suffixes_to_remove:
            if text.endswith(suffix):
                text = text[:-len(suffix)]
        
        return text.strip()
    
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
    
    def fuzzy_match(self, query: str, targets: List[str]) -> Tuple[Optional[str], int]:
        """
        Enhanced fuzzy matching with caching and optimization
        """
        if not targets or not query:
            return None, 0

        # OPTIMIZATION: Check cache first
        cache_key = f"{query}:{len(targets)}"
        if cache_key in self._fuzzy_cache:
            return self._fuzzy_cache[cache_key]

        result = self._perform_fuzzy_match(query, targets)

        # Cache the result (limit cache size to prevent memory bloat)
        if len(self._fuzzy_cache) < 10000:
            self._fuzzy_cache[cache_key] = result

        return result

    def _perform_fuzzy_match(self, query: str, targets: List[str]) -> Tuple[Optional[str], int]:
        """Perform the actual fuzzy matching logic"""
        if FUZZY_AVAILABLE:
            # Filter out very short targets that can cause false positives in fuzzy matching
            # Short aliases like "mi", "b1", "d3" can match almost anything with partial_ratio
            filtered_targets = [t for t in targets if len(t) >= 4]

            # Use fuzzywuzzy for better performance
            match = process.extractOne(query, filtered_targets, scorer=fuzz.ratio)
            if match and match[1] >= self.fuzzy_threshold:
                # Check blacklist before accepting the match
                if not self._is_blacklisted_match(query, match[0]):
                    return match[0], match[1]
                else:
                    logger.warning(f"Rejected blacklisted fuzzy match: '{query}' -> '{match[0]}' (score: {match[1]})")
                    return None, 0

            # Try partial matching with filtered targets to avoid false positives
            if len(query) >= 6:  # Only use partial matching for longer queries
                match = process.extractOne(query, filtered_targets, scorer=fuzz.partial_ratio)
                if match and match[1] >= self.partial_threshold:
                    return match[0], match[1]
        else:
            # Fallback to difflib
            best_match = None
            best_score = 0

            for target in targets:
                ratio = SequenceMatcher(None, query, target).ratio() * 100
                if ratio > best_score:
                    best_score = ratio
                    best_match = target

            if best_score >= self.fuzzy_threshold:
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
        import re
        
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
        import re
        
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

    def get_context_window(self, text: str, match_start: int, match_end: int, window_size: int = 20) -> str:
        """Extract context window around a match for disambiguation"""
        start = max(0, match_start - window_size)
        end = min(len(text), match_end + window_size)
        return text[start:end].lower()

    def disambiguate_ingredient_match(self, context_text: str, ingredient_data: Dict[str, Any]) -> bool:
        """
        Determine if an ingredient match is valid based on context disambiguation
        
        Args:
            context_text: Text context around the matched ingredient
            ingredient_data: Ingredient form data with context_include/context_exclude
            
        Returns:
            True if match is valid, False if should be rejected
        """
        import re
        
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
        """Clear fuzzy matching cache to free memory"""
        self._fuzzy_cache.clear()
        self._exact_match_cache.clear()


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
        self.non_harmful_additives = self._load_json(NON_HARMFUL_ADDITIVES)
        self.passive_inactive_ingredients = self._load_json(PASSIVE_INACTIVE_INGREDIENTS)
        self.botanical_ingredients = self._load_json(BOTANICAL_INGREDIENTS)
        self.enhanced_delivery = self._load_json(ENHANCED_DELIVERY)
        
        # Initialize enhanced matcher
        self.matcher = EnhancedIngredientMatcher()
        
        # Build enhanced lookup indices
        self._build_enhanced_indices()

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

        # OPTIMIZATION: Multi-level caching system
        self._ingredient_cache = {}  # Cache for ingredient processing results
        self._harmful_cache = {}     # Cache for harmful additive checks
        self._non_harmful_cache = {}  # Cache for non-harmful additive checks
        self._allergen_cache = {}    # Cache for allergen checks
        self._fuzzy_match_cache = {}  # Cache for fuzzy matching results
        self._preprocessing_cache = {}  # Cache for text preprocessing
        
        # OPTIMIZATION: Performance statistics tracking
        self._cache_hits = {"ingredient": 0, "harmful": 0, "non_harmful": 0, "allergen": 0, "fuzzy": 0, "preprocess": 0}
        self._cache_misses = {"ingredient": 0, "harmful": 0, "non_harmful": 0, "allergen": 0, "fuzzy": 0, "preprocess": 0}
        
        # OPTIMIZATION: Memory management
        self._max_cache_size = 50000  # Maximum entries per cache
        self._cache_cleanup_threshold = 45000  # When to start cleanup

        # OPTIMIZATION: Parallel processing configuration
        self._max_workers = min(8, (os.cpu_count() or 4))  # Adaptive worker count
        self._parallel_threshold = 10  # Minimum ingredients to use parallel processing
        self._cache_lock = threading.Lock()  # Thread-safe cache access

        # OPTIMIZATION: Fast lookup indices for common operations
        self._fast_exact_lookup = {}  # Combined exact match lookup
        self._common_ingredients_cache = {}  # Cache for most common ingredients
        self._build_fast_lookups()

    def set_output_directory(self, output_dir: Path):
        """Set the output directory and initialize the unmapped tracker"""
        self.unmapped_tracker = UnmappedIngredientTracker(output_dir / "unmapped")
        
    def clear_caches(self):
        """Clear all caches to free memory"""
        with self._cache_lock:
            self._ingredient_cache.clear()
            self._harmful_cache.clear()
            self._non_harmful_cache.clear()
            self._allergen_cache.clear()
            self._fuzzy_match_cache.clear()
            self._preprocessing_cache.clear()
        self.matcher.clear_cache()
        self._fast_exact_lookup.clear()
        self._common_ingredients_cache.clear()
        logger.info("Cleared all ingredient processing caches")
        
    def _manage_cache_size(self, cache_dict: Dict, cache_name: str):
        """Manage cache size to prevent memory overflow"""
        if len(cache_dict) > self._max_cache_size:
            # Remove oldest 10% of entries (simple FIFO approach)
            remove_count = len(cache_dict) - self._cache_cleanup_threshold
            keys_to_remove = list(cache_dict.keys())[:remove_count]
            for key in keys_to_remove:
                cache_dict.pop(key, None)
            logger.info(f"Cache cleanup: removed {remove_count} entries from {cache_name} cache")
    
    def get_cache_stats(self) -> Dict[str, Dict[str, int]]:
        """Get performance statistics for caching system"""
        return {
            "cache_hits": self._cache_hits.copy(),
            "cache_misses": self._cache_misses.copy(),
            "cache_sizes": {
                "ingredient": len(self._ingredient_cache),
                "harmful": len(self._harmful_cache),
                "non_harmful": len(self._non_harmful_cache),
                "allergen": len(self._allergen_cache),
                "fuzzy": len(self._fuzzy_match_cache),
                "preprocess": len(self._preprocessing_cache)
            }
        }

    def _build_fast_lookups(self):
        """Build optimized lookup indices for common operations"""
        # This will be called after the main indices are built
        pass  # Implementation will be added after indices are built

    def _build_fast_lookups_impl(self):
        """Build optimized fast lookup indices"""
        logger.info("Building fast lookup indices...")

        # Build combined exact match lookup for all databases
        self._fast_exact_lookup = {}

        # Add ingredient lookups
        for key, value in self.ingredient_alias_lookup.items():
            self._fast_exact_lookup[key] = {
                "type": "ingredient",
                "standard_name": value,
                "mapped": True
            }

        # Add harmful additive lookups
        for key, value in self.harmful_lookup.items():
            self._fast_exact_lookup[key] = {
                "type": "harmful",
                "category": value.get("category", "other"),
                "risk_level": value.get("risk_level", "low"),
                "mapped": True
            }

        # Add allergen lookups
        for key, value in self.allergen_lookup.items():
            self._fast_exact_lookup[key] = {
                "type": "allergen",
                "allergen_type": value["standard_name"].lower(),
                "severity": value.get("severity_level", "low"),
                "mapped": True
            }

        logger.info(f"Built fast lookup index with {len(self._fast_exact_lookup)} entries")

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
        forms = ingredient_data.get("forms", [])

        # Enhanced mapping
        standard_name, mapped, _ = self._enhanced_ingredient_mapping(name, forms)

        # Enhanced checks
        allergen_info = self._enhanced_allergen_check(name, forms)
        harmful_info = self._enhanced_harmful_check(name)

        # Calculate final mapping status
        is_mapped = (mapped or
                    harmful_info["category"] != "none" or
                    allergen_info["is_allergen"])

        # Track unmapped ingredients only if not found in any database
        if not is_mapped:
            processed_name = self.matcher.preprocess_text(name)
            with self._cache_lock:
                self.unmapped_ingredients[name] += 1
                self.unmapped_details[name] = {
                    "processed_name": processed_name,
                    "forms": forms,
                    "variations_tried": self.matcher.generate_variations(processed_name),
                    "is_active": True  # This method is for active ingredients from the context
                }

        return {
            "order": ingredient_data.get("order", 0),
            "name": name,
            "standardName": standard_name,
            "category": ingredient_data.get("category", ""),
            "ingredientGroup": ingredient_data.get("ingredientGroup", ""),
            "isHarmful": harmful_info["category"] != "none",
            "harmfulCategory": harmful_info["category"],
            "riskLevel": harmful_info["risk_level"],
            "allergen": allergen_info["is_allergen"],
            "allergenType": allergen_info["type"],
            "allergenSeverity": allergen_info["severity"],
            "mapped": is_mapped
        }

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
            self._non_harmful_variations_cache = list(self.non_harmful_lookup.keys())
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
            banned_ingredients = self.banned_recalled.get("banned_ingredients", [])
            for banned in banned_ingredients:
                all_banned_terms.append(banned.get("standard_name", "").lower())
                all_banned_terms.extend([alias.lower() for alias in banned.get("aliases", [])])
            self._banned_variations_cache = [term for term in all_banned_terms if term]
        return self._banned_variations_cache

    @property
    def inactive_variations(self) -> List[str]:
        """Cached inactive variations list for fuzzy matching"""
        if self._inactive_variations_cache is None:
            all_inactive_terms = []
            inactive_ingredients = self.passive_inactive_ingredients.get("passive_inactive_ingredients", [])
            for inactive in inactive_ingredients:
                all_inactive_terms.append(inactive.get("standard_name", "").lower())
                all_inactive_terms.extend([alias.lower() for alias in inactive.get("aliases", [])])
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
                all_botanical_terms.extend([alias.lower() for alias in botanical.get("aliases", [])])
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
            for form_name, form_data in vitamin_data.get("forms", {}).items():
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
                for alias in form_data.get("aliases", []):
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
        
        # Log conflicts for debugging
        if conflicts:
            logger.warning(f"Found {len(conflicts)} mapping conflicts - keeping first mappings")
            for variation, conflict in list(conflicts.items())[:10]:  # Show first 10
                logger.debug(f"Conflict: '{variation}' {conflict}")
        
        # Build enhanced allergen lookup
        self.allergen_lookup = {}

        for allergen in self.allergens_db.get("common_allergens", []):
            standard_name = allergen["standard_name"]

            # Add standard name variations
            name_variations = self.matcher.generate_variations(
                self.matcher.preprocess_text(standard_name)
            )
            for variation in name_variations:
                self.allergen_lookup[variation] = allergen

            # Add alias variations
            for alias in allergen.get("aliases", []):
                alias_variations = self.matcher.generate_variations(
                    self.matcher.preprocess_text(alias)
                )
                for variation in alias_variations:
                    self.allergen_lookup[variation] = allergen
        
        # Build enhanced harmful additive lookup
        self.harmful_lookup = {}

        for additive in self.harmful_additives.get("harmful_additives", []):
            standard_name = additive["standard_name"]

            # Add standard name variations
            name_variations = self.matcher.generate_variations(
                self.matcher.preprocess_text(standard_name)
            )
            for variation in name_variations:
                self.harmful_lookup[variation] = additive

            # Add alias variations
            for alias in additive.get("aliases", []):
                alias_variations = self.matcher.generate_variations(
                    self.matcher.preprocess_text(alias)
                )
                for variation in alias_variations:
                    self.harmful_lookup[variation] = additive
                    
                # CRITICAL FIX: Add simple harmful ingredients to main ingredient lookup
                # This prevents fuzzy matching from picking up complex forms instead
                processed_alias = self.matcher.preprocess_text(alias)
                if processed_alias not in self.ingredient_alias_lookup:
                    self.ingredient_alias_lookup[processed_alias] = alias  # Use the alias as standard name
        
        # Build enhanced non-harmful additives lookup
        self.non_harmful_lookup = {}
        for additive in self.non_harmful_additives.get("non_harmful_additives", []):
            standard_name = additive["standard_name"]
            # Add standard name variations
            name_variations = self.matcher.generate_variations(
                self.matcher.preprocess_text(standard_name)
            )
            for variation in name_variations:
                self.non_harmful_lookup[variation] = additive

            # Add alias variations
            for alias in additive.get("aliases", []):
                alias_variations = self.matcher.generate_variations(
                    self.matcher.preprocess_text(alias)
                )
                for variation in alias_variations:
                    self.non_harmful_lookup[variation] = additive
                    
                # Add to main ingredient lookup to prevent fuzzy conflicts
                processed_alias = self.matcher.preprocess_text(alias)
                if processed_alias not in self.ingredient_alias_lookup:
                    self.ingredient_alias_lookup[processed_alias] = alias
        
        # CRITICAL FIX: Add passive inactive ingredients to main lookup to prevent fuzzy conflicts
        for ingredient in self.passive_inactive_ingredients.get("passive_inactive_ingredients", []):
            standard_name = ingredient.get("standard_name", "")
            if standard_name:
                processed_standard = self.matcher.preprocess_text(standard_name)
                if processed_standard not in self.ingredient_alias_lookup:
                    self.ingredient_alias_lookup[processed_standard] = standard_name
                    
            for alias in ingredient.get("aliases", []):
                processed_alias = self.matcher.preprocess_text(alias)
                if processed_alias not in self.ingredient_alias_lookup:
                    self.ingredient_alias_lookup[processed_alias] = alias

        logger.info(f"Built lookup indices with {len(self.ingredient_alias_lookup)} ingredient variations")
        logger.info(f"Built allergen index with {len(self.allergen_lookup)} variations")
        logger.info(f"Built harmful additive index with {len(self.harmful_lookup)} variations")
        logger.info(f"Built non-harmful additive index with {len(self.non_harmful_lookup)} variations")

        # Build optimized fast lookups
        self._build_fast_lookups_impl()
    
    def _enhanced_ingredient_mapping(self, name: str, forms: List[str] = None) -> Tuple[str, bool, List[str]]:
        """
        Enhanced ingredient mapping with fuzzy matching and comprehensive preprocessing
        """
        if not name:
            return name, False, []

        forms = forms or []

        # OPTIMIZATION: Check cache first
        cache_key = f"{name}:{':'.join(sorted(forms))}"
        if cache_key in self._ingredient_cache:
            return self._ingredient_cache[cache_key]

        # Perform the actual mapping
        result = self._perform_ingredient_mapping(name, forms)

        # Cache the result (limit cache size to prevent memory bloat)
        if len(self._ingredient_cache) < 50000:
            self._ingredient_cache[cache_key] = result

        return result

    def _perform_ingredient_mapping(self, name: str, forms: List[str] = None) -> Tuple[str, bool, List[str]]:
        """Perform the actual ingredient mapping logic"""
        forms = forms or []

        # Preprocess the input name
        processed_name = self.matcher.preprocess_text(name)
        
        # Debug logging for specific ingredients
        if name in ["Molybdenum", "Choline", "Alpha-Lipoic Acid"]:
            logger.debug(f"Mapping '{name}' -> processed: '{processed_name}'")
            logger.debug(f"Is '{processed_name}' in lookup? {processed_name in self.ingredient_alias_lookup}")
        
        # Try exact match first
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
        
        # Try fuzzy matching against all ingredient variations (using cached list)
        fuzzy_match, score = self.matcher.fuzzy_match(processed_name, self.ingredient_variations)
        
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
                                fuzzy_form, form_score = self.matcher.fuzzy_match(processed_form, self.form_variations)
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
                            fuzzy_form, form_score = self.matcher.fuzzy_match(processed_form, self.form_variations)
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
                        fuzzy_form, form_score = self.matcher.fuzzy_match(processed_form, self.form_variations)
                        if fuzzy_form:
                            mapped_forms.append(self.ingredient_forms_lookup[fuzzy_form])
                            logger.debug(f"Fuzzy matched form '{form}' -> '{fuzzy_form}' (score: {form_score})")
                
                return mapped_name, True, mapped_forms or forms
        
        # Check if ingredient exists in harmful additives database
        harmful_info = self._enhanced_harmful_check(name)
        if harmful_info["category"] != "none":
            logger.debug(f"Found '{name}' in harmful additives database -> '{harmful_info['category']}'")
            return name, True, forms
        
        # Check if ingredient exists in allergens database
        allergen_info = self._enhanced_allergen_check(name, forms)
        if allergen_info["is_allergen"]:
            logger.debug(f"Found '{name}' in allergens database -> '{allergen_info['type']}'")
            return name, True, forms
        
        # Check if ingredient exists in proprietary blends database
        if self._check_proprietary_blends(name):
            logger.debug(f"Found '{name}' in proprietary blends database")
            return name, True, forms
        
        # Check if ingredient exists in standardized botanicals database
        if self._check_standardized_botanicals(name):
            logger.debug(f"Found '{name}' in standardized botanicals database")
            return name, True, forms
        
        # Check if ingredient exists in banned/recalled ingredients database
        if self._check_banned_recalled(name):
            logger.debug(f"Found '{name}' in banned/recalled ingredients database")
            return name, True, forms
        
        # Check if ingredient exists in passive inactive ingredients database
        if self._check_passive_inactive_ingredients(name):
            logger.debug(f"Found '{name}' in passive inactive ingredients database")
            return name, True, forms
        
        # Check if ingredient exists in botanical ingredients database
        if self._check_botanical_ingredients(name):
            logger.debug(f"Found '{name}' in botanical ingredients database")
            return name, True, forms
        
        # Don't track as unmapped here - will be handled at higher level
        # after all database checks (harmful, allergen, etc.) are complete
        return name, False, forms
    
    def _enhanced_allergen_check(self, name: str, forms: List[str] = None) -> Dict[str, Any]:
        """Enhanced allergen checking with fuzzy matching and caching"""
        forms = forms or []

        # OPTIMIZATION: Check cache first
        cache_key = f"{name}:{':'.join(sorted(forms))}"
        if cache_key in self._allergen_cache:
            return self._allergen_cache[cache_key]

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
                result["is_allergen"] = True
                result["type"] = allergen["standard_name"].lower()
                result["severity"] = allergen.get("severity_level", "low")
                break

            # Try fuzzy match
            fuzzy_match, score = self.matcher.fuzzy_match(processed_term, self.allergen_variations)
            if fuzzy_match:
                allergen = self.allergen_lookup[fuzzy_match]
                result["is_allergen"] = True
                result["type"] = allergen["standard_name"].lower()
                result["severity"] = allergen.get("severity_level", "low")
                logger.debug(f"Fuzzy allergen match '{term}' -> '{fuzzy_match}' (score: {score})")
                break

        # Cache the result (limit cache size)
        if len(self._allergen_cache) < 20000:
            self._allergen_cache[cache_key] = result

        return result
    
    def _enhanced_harmful_check(self, name: str) -> Dict[str, Any]:
        """Enhanced harmful additive checking with fuzzy matching and caching"""
        # OPTIMIZATION: Check cache first
        if name in self._harmful_cache:
            return self._harmful_cache[name]

        result = {
            "category": "none",
            "risk_level": None
        }

        processed_name = self.matcher.preprocess_text(name)

        # Try exact match
        if processed_name in self.harmful_lookup:
            harmful = self.harmful_lookup[processed_name]
            result["category"] = harmful.get("category", "other")
            result["risk_level"] = harmful.get("risk_level", "low")
        else:
            # Try fuzzy match (using cached list)
            fuzzy_match, score = self.matcher.fuzzy_match(processed_name, self.harmful_variations)
            if fuzzy_match:
                harmful = self.harmful_lookup[fuzzy_match]
                result["category"] = harmful.get("category", "other")
                result["risk_level"] = harmful.get("risk_level", "low")
                logger.debug(f"Fuzzy harmful match '{name}' -> '{fuzzy_match}' (score: {score})")

        # Cache the result (limit cache size)
        if len(self._harmful_cache) < 20000:
            self._harmful_cache[name] = result

        return result

    def _enhanced_non_harmful_check(self, name: str) -> Dict[str, Any]:
        """Enhanced non-harmful additive checking with fuzzy matching and caching"""
        # OPTIMIZATION: Check cache first
        if name in self._non_harmful_cache:
            self._cache_hits["non_harmful"] += 1
            return self._non_harmful_cache[name]
        
        self._cache_misses["non_harmful"] += 1
        
        result = {
            "category": "none",
            "additive_type": None,
            "clean_label_score": None
        }

        processed_name = self.matcher.preprocess_text(name)

        # Try exact match
        if processed_name in self.non_harmful_lookup:
            non_harmful = self.non_harmful_lookup[processed_name]
            result["category"] = non_harmful.get("category", "other")
            result["additive_type"] = non_harmful.get("additive_type", "unknown")
            result["clean_label_score"] = non_harmful.get("clean_label_score", 7)
        else:
            # Try fuzzy match (using cached list)
            fuzzy_match, score = self.matcher.fuzzy_match(processed_name, self.non_harmful_variations)
            if fuzzy_match:
                non_harmful = self.non_harmful_lookup[fuzzy_match]
                result["category"] = non_harmful.get("category", "other")
                result["additive_type"] = non_harmful.get("additive_type", "unknown")
                result["clean_label_score"] = non_harmful.get("clean_label_score", 7)
                logger.debug(f"Fuzzy non-harmful match '{name}' -> '{fuzzy_match}' (score: {score})")

        # Cache the result with size management
        if len(self._non_harmful_cache) < self._max_cache_size:
            self._non_harmful_cache[name] = result
        else:
            self._manage_cache_size(self._non_harmful_cache, "non_harmful")
            self._non_harmful_cache[name] = result

        return result
    
    def log_performance_summary(self):
        """Log performance statistics for the current session"""
        stats = self.get_cache_stats()
        
        # Calculate cache hit ratios
        total_hits = sum(stats["cache_hits"].values())
        total_misses = sum(stats["cache_misses"].values())
        total_requests = total_hits + total_misses
        
        if total_requests > 0:
            hit_ratio = (total_hits / total_requests) * 100
            logger.info(f"🚀 Performance Summary:")
            logger.info(f"   Cache Hit Ratio: {hit_ratio:.1f}% ({total_hits}/{total_requests})")
            logger.info(f"   Cache Hits: {stats['cache_hits']}")
            logger.info(f"   Cache Sizes: {stats['cache_sizes']}")
            logger.info(f"   Workers Used: {self._max_workers}")
        else:
            logger.info("No cache statistics available for this session")
    
    def _check_proprietary_blends(self, name: str) -> bool:
        """Check if ingredient exists in proprietary blends penalty database"""
        processed_name = self.matcher.preprocess_text(name)
        
        # Check all red flag terms in all blend categories
        for concern in self.proprietary_blends.get("proprietary_blend_concerns", []):
            # Check standard_name field
            standard_name = concern.get("standard_name", "")
            if processed_name == self.matcher.preprocess_text(standard_name):
                return True
                
            # Check red_flag_terms array
            red_flag_terms = concern.get("red_flag_terms", [])
            
            # Check exact matches
            for term in red_flag_terms:
                processed_term = self.matcher.preprocess_text(term)
                if processed_name == processed_term:
                    return True
            
            # Check fuzzy matches
            fuzzy_match, score = self.matcher.fuzzy_match(processed_name, 
                [self.matcher.preprocess_text(term) for term in red_flag_terms])
            if fuzzy_match and score >= self.matcher.fuzzy_threshold:
                logger.debug(f"Fuzzy proprietary blend match '{name}' -> '{fuzzy_match}' (score: {score})")
                return True
        
        return False
    
    def _check_standardized_botanicals(self, name: str) -> bool:
        """Check if ingredient exists in standardized botanicals database
        
        Requires BOTH botanical name/alias AND standardization marker to be present
        Example: 'Ginger Extract standardized to 5% gingerols' = TRUE
                 'Ginger Extract' alone = FALSE
        """
        processed_name = self.matcher.preprocess_text(name)
        original_name = name.lower()  # Keep original for marker detection
        
        # Check standardized botanicals entries (now array structure)
        botanicals_data = self.standardized_botanicals.get("standardized_botanicals", [])

        # Check each botanical entry in the array
        for item in botanicals_data:
            botanical_found = False
            
            # Check if botanical name (standard_name) is present
            standard_name = self.matcher.preprocess_text(item.get("standard_name", ""))
            if standard_name and standard_name in processed_name:
                botanical_found = True

            # Check if any alias is present
            if not botanical_found:
                for alias in item.get("aliases", []):
                    processed_alias = self.matcher.preprocess_text(alias)
                    if processed_alias and processed_alias in processed_name:
                        botanical_found = True
                        break
            
            # If botanical is found, check for standardization markers
            if botanical_found:
                markers = item.get("markers", [])
                for marker in markers:
                    marker_lower = marker.lower()
                    # Check if marker is present in original ingredient name
                    if marker_lower in original_name:
                        logger.debug(f"Standardized botanical match: '{name}' contains '{item.get('standard_name')}' + marker '{marker}'")
                        return True
        
        # Fallback: Check for general standardization patterns (e.g., "standardized to 5% extract")
        for pattern in STANDARDIZATION_PATTERNS:
            match = re.search(pattern, original_name, re.IGNORECASE)
            if match:
                # Found a standardization pattern - this qualifies as standardized
                percentage = match.group(1) if len(match.groups()) >= 1 else "unknown"
                compound = match.group(2).strip() if len(match.groups()) >= 2 else "compound"
                logger.debug(f"Fallback standardized pattern match: '{name}' contains '{percentage}% {compound}'")
                return True
        
        # No valid standardized botanical match found (need both botanical + marker OR standardization pattern)
        return False
    
    def _check_banned_recalled(self, name: str) -> bool:
        """Check if ingredient exists in banned/recalled ingredients database"""
        processed_name = self.matcher.preprocess_text(name)
        
        # List of all arrays to check in the banned/recalled database
        arrays_to_check = [
            "permanently_banned",
            "sarms_prohibited", 
            "high_risk_ingredients",
            "illegal_spiking_agents",
            "wada_prohibited_2024",
            "state_regional_bans",
            "manufacturing_violations",
            # Also check legacy names in case they exist
            "banned_ingredients",
            "recalled_ingredients"
        ]
        
        # Check all arrays in the database for exact matches first
        for array_name in arrays_to_check:
            items = self.banned_recalled.get(array_name, [])

            for item in items:
                # Check standard_name
                standard_name = self.matcher.preprocess_text(item.get("standard_name", ""))
                if standard_name and processed_name == standard_name:
                    return True

                # Check aliases
                for alias in item.get("aliases", []):
                    processed_alias = self.matcher.preprocess_text(alias)
                    if processed_name == processed_alias:
                        return True
        
        # Try fuzzy matching with cached banned variations
        if self.banned_variations:
            fuzzy_match, score = self.matcher.fuzzy_match(processed_name, self.banned_variations)
            if fuzzy_match and score >= self.matcher.fuzzy_threshold:
                logger.debug(f"Fuzzy banned/recalled match '{name}' -> '{fuzzy_match}' (score: {score})")
                return True
        
        return False
    
    def _check_passive_inactive_ingredients(self, name: str) -> bool:
        """Check if ingredient exists in passive inactive ingredients database"""
        processed_name = self.matcher.preprocess_text(name)
        
        # Check passive inactive ingredients entries
        inactive_ingredients = self.passive_inactive_ingredients.get("passive_inactive_ingredients", [])
        
        # Check each inactive ingredient for exact matches first
        for item in inactive_ingredients:
            # Check standard_name
            standard_name = self.matcher.preprocess_text(item.get("standard_name", ""))
            if standard_name and processed_name == standard_name:
                return True

            # Check aliases
            for alias in item.get("aliases", []):
                processed_alias = self.matcher.preprocess_text(alias)
                if processed_name == processed_alias:
                    return True
        
        # Try fuzzy matching with cached inactive variations
        if self.inactive_variations:
            fuzzy_match, score = self.matcher.fuzzy_match(processed_name, self.inactive_variations)
            if fuzzy_match and score >= self.matcher.fuzzy_threshold:
                logger.debug(f"Fuzzy passive inactive match '{name}' -> '{fuzzy_match}' (score: {score})")
                return True
        
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
        harmful_info = {"category": "none", "risk_level": None}
        non_harmful_info = {"category": "none", "additive_type": None, "clean_label_score": None}
        allergen_info = {"is_allergen": False, "type": None, "severity": None}
        passive_info = {"is_passive": False, "category": None}
        
        # Check all databases
        is_banned = self._check_banned_recalled(name)
        is_harmful = self._enhanced_harmful_check(name)
        is_non_harmful = self._enhanced_non_harmful_check(name)
        is_allergen = self._enhanced_allergen_check(name, forms)
        is_passive = self._check_passive_inactive_ingredients(name)
        
        # Apply priority rules
        if is_banned:
            # PRIORITY 1: Banned/Recalled - highest priority, overrides all others
            banned_info = {"is_banned": True, "severity": "critical", "category": "banned"}
            # Still populate other info but they won't be used for scoring
            harmful_info = is_harmful
            non_harmful_info = is_non_harmful
            allergen_info = is_allergen
            passive_info = {"is_passive": False, "category": None}  # Override passive classification
            
        elif is_harmful["category"] != "none":
            # PRIORITY 2: Harmful additives - second priority
            harmful_info = is_harmful
            non_harmful_info = {"category": "none", "additive_type": None, "clean_label_score": None}  # Override
            allergen_info = is_allergen  # Allow allergen info to coexist
            passive_info = {"is_passive": False, "category": None}  # Override passive classification
            
        elif is_non_harmful["category"] != "none":
            # PRIORITY 3: Non-harmful additives - third priority (flagged but safe)
            non_harmful_info = is_non_harmful
            harmful_info = {"category": "none", "risk_level": None}  # Override
            allergen_info = is_allergen  # Allow allergen info to coexist
            passive_info = {"is_passive": False, "category": None}  # Override passive classification
            
        elif is_allergen["is_allergen"]:
            # PRIORITY 4: Allergens - fourth priority
            allergen_info = is_allergen
            # Reset others to none since allergen takes priority over passive
            harmful_info = {"category": "none", "risk_level": None}
            non_harmful_info = {"category": "none", "additive_type": None, "clean_label_score": None}
            passive_info = {"is_passive": False, "category": None}  # Override passive classification
            
        elif is_passive:
            # PRIORITY 5: Passive/Inactive - lowest priority, only applies if no higher priority match
            passive_info = {"is_passive": True, "category": "passive_ingredient"}
            # Keep other classifications as none
            harmful_info = {"category": "none", "risk_level": None}
            non_harmful_info = {"category": "none", "additive_type": None, "clean_label_score": None}
            allergen_info = {"is_allergen": False, "type": None, "severity": None}
        
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
            "passive_info": passive_info,
            "priority_applied": {
                "banned": is_banned,
                "harmful": is_harmful["category"] != "none",
                "non_harmful": is_non_harmful["category"] != "none",
                "allergen": is_allergen["is_allergen"],
                "passive": is_passive
            }
        }
    
    def _check_botanical_ingredients(self, name: str) -> bool:
        """Check if ingredient exists in botanical ingredients database"""
        processed_name = self.matcher.preprocess_text(name)
        
        # Check botanical ingredients entries
        botanical_ingredients = self.botanical_ingredients.get("botanical_ingredients", [])
        
        # Check each botanical ingredient for exact matches first
        for item in botanical_ingredients:
            # Check standard_name
            standard_name = self.matcher.preprocess_text(item.get("standard_name", ""))
            if standard_name and processed_name == standard_name:
                return True

            # Check aliases
            for alias in item.get("aliases", []):
                processed_alias = self.matcher.preprocess_text(alias)
                if processed_name == processed_alias:
                    return True
        
        # Try fuzzy matching with cached botanical variations
        if self.botanical_variations:
            fuzzy_match, score = self.matcher.fuzzy_match(processed_name, self.botanical_variations)
            if fuzzy_match and score >= self.matcher.fuzzy_threshold:
                logger.debug(f"Fuzzy botanical ingredients match '{name}' -> '{fuzzy_match}' (score: {score})")
                return True
        
        return False
    
    def _flatten_nested_ingredients(self, ingredient_rows: List[Dict]) -> List[Dict]:
        """Flatten nested ingredients from blends for better scoring"""
        flattened = []
        
        for ing in ingredient_rows:
            # Add the main ingredient
            flattened.append(ing)
            
            # Process nested ingredients
            nested = ing.get("nestedRows", [])
            if nested:
                for nested_ing in nested:
                    # Mark as part of a blend
                    nested_ing["parentBlend"] = ing.get("name", "Unknown Blend")
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
            discontinued_date = self._extract_discontinued_date(raw_data.get("events", []))
            
            # Generate image URL
            image_url = self._generate_image_url(raw_data.get("thumbnail", ""), product_id)
            
            # Process contacts
            contacts = self._process_contacts(raw_data.get("contacts", []))
            
            # Flatten and process ingredients with enhanced mapping
            raw_ingredients = raw_data.get("ingredientRows", [])
            flattened_ingredients = self._flatten_nested_ingredients(raw_ingredients)
            
            # Extract nutritional warnings before filtering out nutrition facts
            # Need to check both active ingredients and other ingredients for nutritional facts
            other_ingredients_raw = raw_data.get("otheringredients", {}).get("ingredients", [])
            all_ingredients_for_warnings = flattened_ingredients + other_ingredients_raw
            nutritional_warnings = self._extract_nutritional_warnings(all_ingredients_for_warnings)
            
            active_ingredients = self._process_ingredients_enhanced(flattened_ingredients, is_active=True)
            
            # Process other ingredients
            inactive_ingredients = self._process_other_ingredients_enhanced(
                raw_data.get("otheringredients", {})
            )
            
            # Process statements
            statements = self._process_statements(raw_data.get("statements", []))
            
            # Process claims
            claims = self._process_claims(raw_data.get("claims", []))
            
            # Process serving sizes
            serving_sizes = self._process_serving_sizes(raw_data.get("servingSizes", []))
            
            # Extract quality flags
            quality_flags = self._extract_quality_flags(
                active_ingredients, 
                inactive_ingredients, 
                statements
            )
            
            # Calculate mapping statistics
            total_ingredients = len(active_ingredients) + len(inactive_ingredients)
            mapped_ingredients = sum(1 for ing in active_ingredients + inactive_ingredients if ing.get("mapped"))
            
            # Calculate proprietary blend disclosure statistics
            blend_stats = self._calculate_blend_disclosure_stats(active_ingredients + inactive_ingredients)
            
            # Build cleaned product
            cleaned = {
                # Core identifiers
                "id": product_id,
                "fullName": raw_data.get("fullName", ""),
                "brandName": raw_data.get("brandName", ""),
                "upcSku": raw_data.get("upcSku", ""),
                "upcValid": self._validate_upc(raw_data.get("upcSku", "")),
                
                # Status
                "status": status,
                "discontinuedDate": discontinued_date,
                "offMarket": off_market,
                
                # Product details
                "servingsPerContainer": self._safe_int(raw_data.get("servingsPerContainer", 0)),
                "netContents": self._extract_net_contents(raw_data.get("netContents", [])),
                "targetGroups": raw_data.get("targetGroups", []),
                "productType": raw_data.get("productType", {}).get("langualCodeDescription", ""),
                "physicalState": raw_data.get("physicalState", {}).get("langualCodeDescription", ""),
                
                # Images
                "imageUrl": image_url,
                "images": raw_data.get("images", []),
                
                # Manufacturer info
                "contacts": contacts,
                
                # Events
                "events": raw_data.get("events", []),
                
                # Ingredients
                "activeIngredients": active_ingredients,
                "inactiveIngredients": inactive_ingredients,
                
                # Statements and claims
                "statements": statements,
                "claims": claims,
                
                # Serving info
                "servingSizes": serving_sizes,
                
                # Label relationships
                "labelRelationships": raw_data.get("labelRelationships", []),
                
                # Combined label text for search
                "labelText": self._generate_label_text(
                    active_ingredients, 
                    inactive_ingredients, 
                    statements
                ),
                
                # RDA compliance (empty for future use)
                "rdaCompliance": [],
                
                # Nutritional warnings for UI display
                "nutritionalWarnings": nutritional_warnings,
                
                # Enhanced metadata
                "metadata": {
                    "lastCleaned": datetime.utcnow().isoformat() + "Z",
                    "cleaningVersion": "2.0.0",  # Enhanced version
                    "completeness": {
                        "score": 0,  # Will be set by validator
                        "missingFields": [],
                        "criticalFieldsComplete": True
                    },
                    "qualityFlags": quality_flags,
                    "mappingStats": {
                        "totalIngredients": total_ingredients,
                        "mappedIngredients": mapped_ingredients,
                        "unmappedIngredients": total_ingredients - mapped_ingredients,
                        "mappingRate": round((mapped_ingredients / total_ingredients * 100), 2) if total_ingredients > 0 else 0
                    },
                    "enhancedFeatures": {
                        "fuzzyMatchingUsed": FUZZY_AVAILABLE,
                        "nestedIngredientsFlattened": len(flattened_ingredients) > len(raw_ingredients),
                        "preprocessingApplied": True
                    },
                    "proprietaryBlendStats": blend_stats
                }
            }
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Error normalizing product {raw_data.get('id', 'unknown')}: {str(e)}")
            raise
    
    def _process_ingredients_enhanced(self, ingredient_rows: List[Dict], is_active: bool = True) -> List[Dict]:
        """Process ingredients with enhanced mapping"""
        processed = []
        
        for ing in ingredient_rows:
            processed_ing = self._process_single_ingredient_enhanced(ing, is_active)
            # Skip None values (nutrition facts that were filtered out)
            if processed_ing is not None:
                processed.append(processed_ing)
        
        return processed
    
    def _process_single_ingredient_enhanced(self, ing: Dict, is_active: bool) -> Dict[str, Any]:
        """Process a single ingredient with enhanced mapping"""
        name = ing.get("name", "")
        notes = ing.get("notes", "")
        forms = [f.get("name", "") for f in ing.get("forms", [])]
        
        # Skip nutritional facts - these are not supplement ingredients
        if self._is_nutrition_fact(name):
            logger.debug(f"Skipping nutrition fact: {name}")
            return None
        
        # Enhanced mapping with fuzzy matching
        standard_name, mapped, mapped_forms = self._enhanced_ingredient_mapping(name, forms)
        
        # Get ingredient quality info - ONLY for active ingredients
        quality_info = {"natural": False, "bio_score": 0}
        if is_active:
            quality_info = self._get_ingredient_quality_info(standard_name, mapped_forms)
        
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

        # Process quantity
        quantity, unit, daily_value = self._process_quantity(ing.get("quantity", []))

        # Check if proprietary - based on quantity OR if name contains blend indicators
        is_proprietary = quantity == 0 or unit == "NP" or self._is_proprietary_blend_name(name)
        
        # Determine disclosure level for proprietary blends
        disclosure_level = None
        if is_proprietary or self._is_proprietary_blend_name(name):
            # For parent blends, check original nested structure
            nested_rows = ing.get("nestedRows", [])
            disclosure_level = self._determine_disclosure_level(name, quantity, unit, nested_rows)

        # An ingredient is considered "mapped" if it's found in ANY reference database
        # This includes ingredient databases, harmful additives, non-harmful additives, allergens, banned, or passive databases
        is_mapped = (mapped or
                    harmful_info["category"] != "none" or
                    non_harmful_info["category"] != "none" or
                    allergen_info["is_allergen"] or
                    banned_info["is_banned"] or
                    passive_info["is_passive"])

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

        return {
            "order": ing.get("order", 0),
            "name": name,
            "standardName": standard_name,
            "quantity": quantity,
            "unit": unit,
            "dailyValue": daily_value,
            "forms": mapped_forms if mapped_forms else (forms if forms else ["unspecified"]),
            "formDetails": " ".join(mapped_forms) if mapped_forms else " ".join(forms),
            "notes": notes,
            "labelPhrases": extracted_features.get("phrases", []),
            "natural": quality_info.get("natural", False),
            "standardized": extracted_features.get("standardized", False),
            "standardizationPercent": extracted_features.get("standardization_percent", None),
            "category": ing.get("category", ""),
            "ingredientGroup": ing.get("ingredientGroup", ""),

            # Enhanced allergen info
            "allergen": allergen_info["is_allergen"],
            "allergenType": allergen_info["type"],
            "allergenSeverity": allergen_info["severity"],

            # Enhanced harmful info
            "harmfulCategory": harmful_info["category"],
            "riskLevel": harmful_info["risk_level"],

            # Enhanced non-harmful additive info
            "nonHarmfulCategory": non_harmful_info["category"],
            "additiveType": non_harmful_info["additive_type"],
            "cleanLabelScore": non_harmful_info["clean_label_score"],

            # Enhanced banned/recalled info
            "isBanned": banned_info["is_banned"],
            "bannedSeverity": banned_info["severity"],
            "bannedCategory": banned_info["category"],

            # Enhanced passive/inactive info
            "isPassiveIngredient": passive_info["is_passive"],
            "passiveCategory": passive_info["category"],

            # Proprietary and mapping
            "proprietaryBlend": is_proprietary,
            "isProprietaryBlend": is_proprietary,
            "disclosureLevel": disclosure_level,  # 'full', 'partial', 'none', or None for non-blends
            "mapped": is_mapped,
            
            # Blend information (if applicable)
            "parentBlend": ing.get("parentBlend", None),
            "isNestedIngredient": ing.get("isNestedIngredient", False),
            
            # Nested ingredients (empty for flattened structure)
            "nestedIngredients": [],
            
            # Enrichment placeholders (to be populated during enrichment phase)
            "clinicalEvidence": None,
            "synergyClusters": [],
            "enhancedDelivery": None,
            "brandedForm": None
        }
    
    def _process_other_ingredients_enhanced(self, other_ing_data: Dict) -> List[Dict]:
        """Process inactive/other ingredients with enhanced mapping and parallel processing"""
        ingredients = other_ing_data.get("ingredients", [])

        if not ingredients:
            return []

        # OPTIMIZATION: Use parallel processing for large ingredient lists
        # Parallel processing disabled due to thread safety issues with self references
        # TODO: Implement proper parallel processing with thread-safe methods
        return self._process_ingredients_sequential(ingredients)

    def _process_ingredients_parallel(self, ingredients: List[Dict]) -> List[Dict]:
        """Process ingredients using parallel execution"""
        processed = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # Submit all ingredient processing tasks
            future_to_ingredient = {
                executor.submit(self._process_ingredient_parallel, ing): ing
                for ing in ingredients
            }

            # Collect results as they complete
            for future in as_completed(future_to_ingredient):
                try:
                    result = future.result()
                    processed.append(result)
                except Exception as e:
                    ingredient = future_to_ingredient[future]
                    logger.error(f"Error processing ingredient '{ingredient.get('name', 'unknown')}': {e}")
                    # Add a basic result for failed processing
                    processed.append({
                        "order": ingredient.get("order", 0),
                        "name": ingredient.get("name", ""),
                        "standardName": ingredient.get("name", ""),
                        "category": ingredient.get("category", ""),
                        "ingredientGroup": ingredient.get("ingredientGroup", ""),
                        "isHarmful": False,
                        "harmfulCategory": "none",
                        "riskLevel": None,
                        "allergen": False,
                        "allergenType": None,
                        "allergenSeverity": None,
                        "mapped": False
                    })

        # Sort by original order
        processed.sort(key=lambda x: x.get("order", 0))
        return processed

    def _process_ingredients_sequential(self, ingredients: List[Dict]) -> List[Dict]:
        """Process ingredients sequentially (for small lists)"""
        processed = []

        for ing in ingredients:
            name = ing.get("name", "")

            # Enhanced mapping
            standard_name, mapped, _ = self._enhanced_ingredient_mapping(name)

            # Enhanced checks
            allergen_info = self._enhanced_allergen_check(name)
            harmful_info = self._enhanced_harmful_check(name)

            # An ingredient is considered "mapped" if it's found in ANY reference database
            # This includes ingredient databases, harmful additives, or allergen databases
            is_mapped = (mapped or
                        harmful_info["category"] != "none" or
                        allergen_info["is_allergen"])

            # Track unmapped ingredients only if not found in any database
            if not is_mapped:
                processed_name = self.matcher.preprocess_text(name)
                self.unmapped_ingredients[name] += 1
                self.unmapped_details[name] = {
                    "processed_name": processed_name,
                    "forms": [],
                    "variations_tried": self.matcher.generate_variations(processed_name),
                    "is_active": False  # Inactive ingredients
                }

            processed.append({
                "order": ing.get("order", 0),
                "name": name,
                "standardName": standard_name,
                "category": ing.get("category", ""),
                "ingredientGroup": ing.get("ingredientGroup", ""),
                "isHarmful": harmful_info["category"] != "none",
                "harmfulCategory": harmful_info["category"],
                "riskLevel": harmful_info["risk_level"],
                "allergen": allergen_info["is_allergen"],
                "allergenType": allergen_info["type"],
                "allergenSeverity": allergen_info["severity"],
                "mapped": is_mapped
            })

        return processed
    
    # Include all other methods from the original normalizer
    # (I'll keep the existing methods for compatibility)
    
    def _safe_int(self, value: Any) -> int:
        """Safely convert value to integer"""
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    
    def _safe_float(self, value: Any) -> float:
        """Safely convert value to float"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
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
    
    def _extract_net_contents(self, net_contents: List[Dict]) -> str:
        """Extract net contents display string"""
        if net_contents and len(net_contents) > 0:
            return net_contents[0].get("display", "")
        return "[]"
    
    def _process_contacts(self, contacts: List[Dict]) -> Dict[str, Any]:
        """Process manufacturer contact information"""
        if not contacts:
            return {
                "name": "",
                "webAddress": "",
                "city": "",
                "state": "",
                "country": "",
                "phoneNumber": "",
                "isGMP": False,
                "manufacturerScore": None
            }
        
        # Take first contact
        contact = contacts[0]
        details = contact.get("contactDetails", {})
        name = details.get("name", "")
        
        # Look up manufacturer score
        manufacturer_score = None
        if name:
            # Search in top manufacturers database
            # Handle both array and object formats
            manufacturers = self.manufacturers_db
            if isinstance(self.manufacturers_db, dict):
                manufacturers = self.manufacturers_db.get("manufacturers", [])
            
            for mfr in manufacturers:
                mfr_name = mfr.get("standard_name", "") or mfr.get("name", "")
                if name.lower() in mfr_name.lower():
                    manufacturer_score = mfr.get("score_contribution", None) or mfr.get("reputation_score", None)
                    break
        
        return {
            "name": name,
            "webAddress": details.get("webAddress", ""),
            "city": details.get("city", ""),
            "state": details.get("state", ""),
            "country": details.get("country", ""),
            "phoneNumber": details.get("phoneNumber", ""),
            "isGMP": False,  # Will be set from statements
            "manufacturerScore": manufacturer_score
        }
    
    def _process_quantity(self, quantities: List[Dict]) -> Tuple[float, str, Optional[float]]:
        """Extract quantity, unit, and daily value from quantity array"""
        if not quantities:
            return 0.0, "unspecified", None
        
        # Take first quantity (usually for standard serving)
        q = quantities[0]
        quantity = self._safe_float(q.get("quantity", 0))
        unit = q.get("unit", "unspecified")
        
        # Get daily value if available
        daily_value = None
        dv_groups = q.get("dailyValueTargetGroup", [])
        if dv_groups:
            daily_value = self._safe_float(dv_groups[0].get("percent", 0))
        
        # Convert units if needed (e.g., IU to mcg for Vitamin D)
        if unit == "IU" and "vitamin d" in unit.lower():
            quantity = quantity * 0.025  # Convert to mcg
            unit = "mcg"
        
        return quantity, unit, daily_value
    
    def _get_ingredient_quality_info(self, standard_name: str, forms: List[str]) -> Dict[str, Any]:
        """Get quality information for ingredient"""
        info = {"natural": False, "bio_score": 0}
        
        # Look up in ingredient quality map
        for vitamin_name, vitamin_data in self.ingredient_map.items():
            if vitamin_data.get("standard_name", "").lower() == standard_name.lower():
                # Check each form
                for form in forms:
                    form_lower = form.lower()
                    for form_name, form_data in vitamin_data.get("forms", {}).items():
                        if form_lower == form_name.lower() or form_lower in [a.lower() for a in form_data.get("aliases", [])]:
                            info["natural"] = form_data.get("natural", False)
                            info["bio_score"] = form_data.get("bio_score", 0)
                            return info
        
        return info
    
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
                features["standardization_percent"] = self._safe_float(match.group(1))
                features["phrases"].append(match.group(0))
                break
        
        # Extract natural source
        for pattern in NATURAL_SOURCE_PATTERNS:
            match = re.search(pattern, notes, re.IGNORECASE)
            if match:
                features["natural_source"] = match.group(0)
                features["phrases"].append(match.group(0))
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
        """Process and extract information from statements"""
        processed = []
        
        for stmt in statements:
            stmt_type = stmt.get("type", "")
            notes = stmt.get("notes", "")
            
            # Extract certifications
            certifications = []
            for cert_name, pattern in CERTIFICATION_PATTERNS.items():
                if re.search(pattern, notes, re.IGNORECASE):
                    certifications.append(cert_name)
            
            # Extract allergen-free claims
            allergen_free = []
            for allergen, pattern in ALLERGEN_FREE_PATTERNS.items():
                if re.search(pattern, notes, re.IGNORECASE):
                    allergen_free.append(allergen)
            
            # Check for GMP
            gmp_certified = bool(re.search(CERTIFICATION_PATTERNS["GMP"], notes, re.IGNORECASE))
            
            # Extract allergens mentioned
            allergens = []
            if "allergi" in stmt_type.lower():
                # Extract specific allergens mentioned
                for allergen_data in self.allergens_db.get("common_allergens", []):
                    if allergen_data["standard_name"].lower() in notes.lower():
                        allergens.append(allergen_data["standard_name"].lower())
            
            processed.append({
                "type": stmt_type,
                "notes": notes,
                "certifications": certifications,
                "allergenFree": allergen_free,
                "allergens": allergens,
                "gmpCertified": gmp_certified,
                "thirdPartyTested": "Third-Party" in certifications
            })
        
        return processed
    
    def _process_claims(self, claims: List[Dict]) -> List[Dict]:
        """Process product claims"""
        processed = []
        
        for claim in claims:
            code = claim.get("langualCode", "")
            description = claim.get("langualCodeDescription", "")
            
            # For now, we don't have full claim text in the data
            full_text = ""
            
            # Check for unsubstantiated terms
            has_unsubstantiated = False
            flagged_terms = []
            
            for pattern in UNSUBSTANTIATED_CLAIM_PATTERNS:
                if re.search(pattern, full_text, re.IGNORECASE):
                    has_unsubstantiated = True
                    flagged_terms.append(pattern)
            
            processed.append({
                "code": code,
                "description": description,
                "fullText": full_text,
                "hasUnsubstantiated": has_unsubstantiated,
                "flaggedTerms": flagged_terms
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
    
    def _extract_quality_flags(self, active_ingredients: List[Dict], 
                              inactive_ingredients: List[Dict], 
                              statements: List[Dict]) -> Dict[str, Any]:
        """Extract quality flags from processed data"""
        # Check for proprietary blends
        has_proprietary = any(ing.get("proprietaryBlend", False) for ing in active_ingredients)
        
        # Check for harmful additives
        has_harmful = any(ing.get("isHarmful", False) for ing in inactive_ingredients)
        
        # Check for allergens from ingredients
        allergen_types = []
        for ing in active_ingredients + inactive_ingredients:
            if ing.get("allergen"):
                allergen_type = ing.get("allergenType")
                if allergen_type:
                    allergen_types.append(allergen_type)
        
        # Add facility cross-contamination allergens from statements
        for stmt in statements:
            facility_allergens = stmt.get("allergens", [])
            allergen_types.extend(facility_allergens)
        
        # Check for standardized ingredients
        has_standardized = any(ing.get("standardized", False) for ing in active_ingredients)
        
        # Check for natural sources
        has_natural = any(ing.get("natural", False) for ing in active_ingredients)
        
        # Get certifications
        all_certifications = []
        for stmt in statements:
            all_certifications.extend(stmt.get("certifications", []))
        
        # Check for unsubstantiated claims
        has_unsubstantiated = False  # Would be set from claims processing
        
        return {
            "hasProprietary": has_proprietary,
            "hasHarmfulAdditives": has_harmful,
            "hasAllergens": len(allergen_types) > 0,
            "allergenTypes": list(set(allergen_types)),
            "hasStandardized": has_standardized,
            "hasNaturalSources": has_natural,
            "hasCertifications": len(all_certifications) > 0,
            "certificationTypes": list(set(all_certifications)),
            "hasUnsubstantiatedClaims": has_unsubstantiated
        }
    
    def _generate_label_text(self, active_ingredients: List[Dict], 
                           inactive_ingredients: List[Dict], 
                           statements: List[Dict]) -> str:
        """Generate searchable label text"""
        text_parts = []
        
        # Add ingredient names
        for ing in active_ingredients:
            text_parts.append(ing.get("name", ""))
            text_parts.extend(ing.get("forms", []))
            text_parts.append(ing.get("notes", ""))
        
        for ing in inactive_ingredients:
            text_parts.append(ing.get("name", ""))
        
        # Add statement notes
        for stmt in statements:
            text_parts.append(stmt.get("notes", ""))
        
        # Clean and join
        cleaned_parts = [p.strip() for p in text_parts if p]
        return " ".join(cleaned_parts)
    
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
    
    def _is_nutrition_fact(self, name: str) -> bool:
        """Check if ingredient name is a label phrase or nutrition fact to exclude"""
        if not name:
            return False
        
        # Preprocess the name for comparison
        processed_name = self.matcher.preprocess_text(name)
        
        # Check against excluded nutrition facts
        if processed_name in EXCLUDED_NUTRITION_FACTS:
            return True
            
        # Check against label phrases
        if processed_name in EXCLUDED_LABEL_PHRASES:
            logger.debug(f"Excluding label phrase: {name}")
            return True
            
        # More aggressive pattern matching for percentage headers
        # This catches variations like "Less Than 2% Of:", "Contains Less Than 2% of", etc.
        name_lower = name.lower()
        percentage_patterns = [
            r"less\s+than\s+\d+%",
            r"contains?\s+less\s+than\s+\d+%",
            r"contains?\s+<?\s*\d+%\s+of",
            r"<\s*\d+%\s+of",
            r"other\s+carbohydrate"
        ]
        
        for pattern in percentage_patterns:
            if re.search(pattern, name_lower):
                logger.debug(f"Excluding percentage/label phrase via pattern: {name}")
                return True
            
        # Additional specific checks for variations not caught by exact match
        # Check for standalone percentage indicators (preprocessing strips % symbol)
        if processed_name in ["less than 2%", "less than 2", "<2% of", "< 2% of", "<2 of", "< 2 of"]:
            logger.debug("Excluding percentage indicator: %s", name)
            return True
            
        # Check for pattern-based exclusions
        # Matches things like "Contains 3% or less of" with any percentage
        percentage_pattern = r"contains?\s*<?(\d+%|\d+\s*%)\s*(or\s*less\s*)?of"
        if re.search(percentage_pattern, processed_name):
            logger.debug(f"Excluding percentage header: {name}")
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
        
        # If no nested ingredients, it's either a single proprietary ingredient or blend with no disclosure
        if not nested_ingredients:
            if self._is_proprietary_blend_name(name):
                return "none"  # Blend with no ingredient breakdown at all
            return None  # Single ingredient, not a blend
        
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
                nested_qty = qty_entry.get("value", 0) if isinstance(qty_entry.get("value"), (int, float)) else 0
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
    
    def _calculate_blend_disclosure_stats(self, ingredients: List[Dict]) -> Dict[str, Any]:
        """Calculate statistics about proprietary blend disclosure levels"""
        stats = {
            "totalBlends": 0,
            "fullDisclosure": 0,
            "partialDisclosure": 0, 
            "noDisclosure": 0,
            "hasProprietaryBlends": False
        }
        
        # Count blends by disclosure level
        for ing in ingredients:
            if ing.get("isProprietaryBlend"):
                stats["hasProprietaryBlends"] = True
                stats["totalBlends"] += 1
                
                disclosure_level = ing.get("disclosureLevel")
                if disclosure_level == "full":
                    stats["fullDisclosure"] += 1
                elif disclosure_level == "partial":
                    stats["partialDisclosure"] += 1
                elif disclosure_level == "none":
                    stats["noDisclosure"] += 1
        
        # Determine overall disclosure level
        if not stats["hasProprietaryBlends"]:
            stats["disclosure"] = None  # No proprietary blends
        elif stats["noDisclosure"] > 0:
            stats["disclosure"] = "none"  # Any blend with no disclosure = overall none
        elif stats["partialDisclosure"] > 0:
            stats["disclosure"] = "partial"  # Any partial disclosure = overall partial
        else:
            stats["disclosure"] = "full"  # All blends have full disclosure
        
        return stats
    
    def smart_split_ingredients(self, text: str) -> List[str]:
        """
        Enhanced comma splitting that respects nested parentheses and brackets
        Useful for parsing raw text ingredient lists from unstructured data
        """
        if not text or not isinstance(text, str):
            return []
        
        # Manual parsing to handle complex nesting
        parts = []
        current_part = ""
        paren_depth = 0
        bracket_depth = 0
        
        for char in text:
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif char == '[':
                bracket_depth += 1
            elif char == ']':
                bracket_depth -= 1
            elif char == ',' and paren_depth == 0 and bracket_depth == 0:
                # Safe to split here
                if current_part.strip():
                    parts.append(current_part.strip())
                current_part = ""
                continue
            
            current_part += char
        
        # Add the last part
        if current_part.strip():
            parts.append(current_part.strip())
        
        return parts
    
    def extract_dose_from_text(self, text: str) -> Dict[str, Any]:
        """
        Extract ingredient name and dose information from text using enhanced pattern recognition
        Returns dict with 'ingredient', 'value', 'unit' keys
        """
        if not text or not isinstance(text, str):
            return {"ingredient": text, "value": None, "unit": None}
        
        text = text.strip()
        
        # Try multiple dose patterns
        patterns = [
            # Pattern 1: "Ingredient 500mg" or "Ingredient (500mg)"
            r'^(.+?)\s*\(?(\d+(?:\.\d+)?)\s*(mg|mcg|g|μg|IU)\s*\)?$',
            # Pattern 2: "Ingredient 500 mg" (with space)
            r'^(.+?)\s+(\d+(?:\.\d+)?)\s+(mg|mcg|g|μg|IU)$',
            # Pattern 3: Handle parentheses with dose: "Ingredient (500 mg)"
            r'^(.+?)\s*\(\s*(\d+(?:\.\d+)?)\s+(mg|mcg|g|μg|IU)\s*\)$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                ingredient_name = match.group(1).strip()
                # Remove trailing commas, colons, etc.
                ingredient_name = re.sub(r'[,:;]\s*$', '', ingredient_name)
                dose_value = float(match.group(2))
                dose_unit = match.group(3)
                
                return {
                    "ingredient": ingredient_name,
                    "value": dose_value,
                    "unit": dose_unit,
                    "original_text": text
                }
        
        # If no dose pattern found, return original text as ingredient
        return {"ingredient": text.strip(), "value": None, "unit": None}
    
    def normalize_ingredient_name(self, name: str) -> str:
        """
        Enhanced ingredient name normalization with explicit form qualifier removal
        """
        if not name or not isinstance(name, str):
            return name
        
        # First apply existing preprocessing
        normalized = self.matcher.preprocess_text(name)
        
        # Remove form qualifiers more explicitly
        normalized = re.sub(FORM_QUALIFIERS, '', normalized, flags=re.IGNORECASE)
        
        # Clean up any extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def parse_blend_ingredients_from_text(self, blend_text: str) -> List[Dict[str, Any]]:
        """
        Parse individual ingredients from a blend text description
        Combines smart splitting with dose extraction for unstructured data
        """
        if not blend_text or not isinstance(blend_text, str):
            return []
        
        # Split ingredients using smart comma splitting
        ingredient_parts = self.smart_split_ingredients(blend_text)
        
        parsed_ingredients = []
        for part in ingredient_parts:
            # Extract dose information
            dose_info = self.extract_dose_from_text(part)
            
            # Normalize the ingredient name
            normalized_name = self.normalize_ingredient_name(dose_info["ingredient"])
            
            # Try to map the ingredient
            mapped_name, is_mapped, forms = self._perform_ingredient_mapping(normalized_name)
            
            ingredient_data = {
                "name": mapped_name if is_mapped else dose_info["ingredient"],
                "original_name": dose_info["ingredient"],
                "normalized_name": normalized_name,
                "is_mapped": is_mapped,
                "quantity": [{"value": dose_info["value"], "unit": dose_info["unit"]}] if dose_info["value"] else [],
                "forms": forms,
                "original_text": part
            }
            
            parsed_ingredients.append(ingredient_data)
        
        return parsed_ingredients
    
    def _extract_nutritional_warnings(self, ingredient_rows: List[Dict]) -> Dict[str, Any]:
        """
        Extract nutritional warning information for UI display
        Only flag if above thresholds: sugar >1g, sodium >150mg, saturated fat >2g
        """
        warnings = {
            "excessiveDoses": [],  # Initialize but do not populate during cleaning
            "sugarContent": None,
            "sodiumContent": None,
            "fatContent": None
        }
        
        # Define nutritional component patterns and thresholds
        nutritional_checks = {
            "sugar": {
                "keywords": ["sugar", "sugars", "total sugar", "total sugars", "added sugar"],
                "threshold": 1,  # grams
                "unit_conversions": {"g": 1, "gram": 1, "grams": 1, "mg": 0.001}
            },
            "sodium": {
                "keywords": ["sodium"],
                "threshold": 150,  # milligrams
                "unit_conversions": {"mg": 1, "milligram": 1, "milligrams": 1, "g": 1000}
            },
            "saturated_fat": {
                "keywords": ["saturated fat", "saturated fats", "sat fat"],
                "threshold": 2,  # grams
                "unit_conversions": {"g": 1, "gram": 1, "grams": 1, "mg": 0.001}
            }
        }
        
        for ing in ingredient_rows:
            name = ing.get("name", "").lower().strip()
            
            # Check sugar content
            for keyword in nutritional_checks["sugar"]["keywords"]:
                if keyword in name:
                    amount_info = self._extract_nutritional_amount(ing)
                    if amount_info:
                        amount_in_g = self._convert_to_standard_unit(
                            amount_info["amount"], 
                            amount_info["unit"], 
                            nutritional_checks["sugar"]["unit_conversions"]
                        )
                        if amount_in_g > nutritional_checks["sugar"]["threshold"]:
                            warnings["sugarContent"] = f"{amount_in_g}g per serving"
                    break
            
            # Check sodium content
            for keyword in nutritional_checks["sodium"]["keywords"]:
                if keyword in name:
                    amount_info = self._extract_nutritional_amount(ing)
                    if amount_info:
                        amount_in_mg = self._convert_to_standard_unit(
                            amount_info["amount"], 
                            amount_info["unit"], 
                            nutritional_checks["sodium"]["unit_conversions"]
                        )
                        if amount_in_mg > nutritional_checks["sodium"]["threshold"]:
                            warnings["sodiumContent"] = f"{amount_in_mg}mg per serving"
                    break
            
            # Check saturated fat content
            for keyword in nutritional_checks["saturated_fat"]["keywords"]:
                if keyword in name:
                    amount_info = self._extract_nutritional_amount(ing)
                    if amount_info:
                        amount_in_g = self._convert_to_standard_unit(
                            amount_info["amount"], 
                            amount_info["unit"], 
                            nutritional_checks["saturated_fat"]["unit_conversions"]
                        )
                        if amount_in_g > nutritional_checks["saturated_fat"]["threshold"]:
                            warnings["fatContent"] = f"{amount_in_g}g saturated fat per serving"
                    break
        
        return warnings
    
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
    
    def _extract_quantity_from_forms(self, forms: List[Dict]) -> Optional[Dict]:
        """Extract quantity information from forms"""
        for form in forms:
            amount = form.get("amount")
            unit = form.get("unit", "")
            
            if amount is not None:
                return {
                    "amount": amount,
                    "unit": unit
                }
        
        return None