"""
Single-Source Normalization Module v1.0.0
==========================================
All pipeline stages MUST use this module for text normalization.
Ensures stable, reproducible normalized_key generation.

CRITICAL: Once a normalized_key is generated, it MUST NOT be recomputed.
Store it at entity creation time and propagate through all stages.
"""

import re
import string
import unicodedata
from functools import lru_cache
from typing import Tuple

VERSION = "1.0.0"


@lru_cache(maxsize=10000)
def normalize_text(raw: str) -> str:
    """
    Standard text normalization for display and fuzzy matching.

    Operations (in order):
    1. Unicode NFC normalization
    2. Lowercase
    3. Strip leading/trailing whitespace
    4. Greek beta (β) → 'beta' in supplement contexts
    5. Micro sign (µg) → 'mcg'
    6. Em-dash/en-dash → regular hyphen
    7. Normalize numeric slashes (1/2 → 1 2)
    8. Commas, middle dots → space
    9. Trademark/copyright symbols removed
    10. Collapse internal whitespace

    Returns: normalized string for matching

    This function consolidates logic from:
    - enrich_supplements_v3.py:_normalize_text (lines 673-721)
    """
    if not raw:
        return ""

    # Unicode NFC normalization
    text = unicodedata.normalize('NFC', raw)

    # Lowercase and strip
    text = text.lower().strip()

    # Normalize Greek beta: ONLY in known supplement compound patterns
    # β-glucan, β-carotene, β-sitosterol, β-alanine, β-hydroxy, etc.
    text = re.sub(r'β-(glucan|carotene|sitosterol|alanine|hydroxy|cryptoxanthin)',
                  r'beta-\1', text)
    # Handle standalone β at word boundaries
    text = re.sub(r'\bβ\b', 'beta', text)
    # Handle β glucan pattern
    text = re.sub(r'β glucan', 'beta glucan', text)

    # Normalize micro sign: ONLY before gram units (µg, µgram)
    text = re.sub(r'µg\b', 'mcg', text)
    text = re.sub(r'µgram', 'mcgram', text)

    # Normalize dashes: em-dash (—), en-dash (–) → regular hyphen
    text = re.sub(r'[—–]', '-', text)

    # Normalize numeric slashes: "1/2" or "1 / 2" → "1 2"
    text = re.sub(r'(\d)\s*/\s*(\d)', r'\1 \2', text)

    # Normalize commas and middle dots to spaces (for patterns like "1,3/1,6")
    text = re.sub(r'[,\u00B7]', ' ', text)

    # Remove trademark symbols
    text = re.sub(r'[™®©]', '', text)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


@lru_cache(maxsize=10000)
def make_normalized_key(raw: str) -> str:
    """
    Generate a stable, deterministic key for deduplication and tracking.

    Operations (beyond normalize_text):
    1. Apply normalize_text()
    2. Remove ALL punctuation except hyphens
    3. Replace spaces and hyphens with underscores
    4. Collapse multiple underscores
    5. Strip leading/trailing underscores

    Returns: immutable key string (e.g., "vitamin_b12_methylcobalamin")

    CRITICAL: Once generated, normalized_key MUST NOT be recomputed.
    Store it at entity creation time.

    Examples:
        "Vitamin B12" → "vitamin_b12"
        "Vitamin B12 (as Methylcobalamin)" → "vitamin_b12_as_methylcobalamin"
        "β-Glucan" → "beta_glucan"
        "1,000 mcg" → "1_000_mcg"
    """
    if not raw:
        return ""

    # Start with standard normalization
    text = normalize_text(raw)

    # Remove parentheses but keep contents
    text = re.sub(r'[()]', ' ', text)

    # Remove brackets but keep contents
    text = re.sub(r'[\[\]]', ' ', text)

    # Remove all punctuation except hyphens (convert to space first)
    # Keep alphanumeric, hyphens, and spaces
    text = re.sub(r'[^\w\s-]', '', text)

    # Replace spaces and hyphens with underscores
    text = re.sub(r'[\s-]+', '_', text)

    # Collapse multiple underscores
    text = re.sub(r'_+', '_', text)

    # Strip leading/trailing underscores
    text = text.strip('_')

    return text


@lru_cache(maxsize=5000)
def normalize_company_name(name: str) -> str:
    """
    Normalize company name for manufacturer matching.

    Additional operations beyond normalize_text:
    - Remove corporate suffixes (LLC, Inc, Corp, etc.)
    - Handle special characters in brand names

    Returns: normalized company name for matching

    Examples:
        "Garden of Life LLC" → "garden of life"
        "NOW Foods, Inc." → "now foods"
    """
    if not name:
        return ""

    # Apply standard normalization first
    name = normalize_text(name)

    # Remove common corporate suffixes
    # Order matters: longer suffixes first to prevent partial matches
    # The suffix must be its own token: require whitespace or a comma before it,
    # otherwise word endings get eaten ("Costco" -> "cost", "Visa" -> "vi").
    suffixes_pattern = (
        r'(?:\s+|\s*,\s*)('
        r'l\.l\.c\.|llc|'
        r'incorporated|inc\.?|'
        r'corporation|corp\.?|'
        r'company|co\.?|'
        r'limited|ltd\.?|'
        r'plc|gmbh|ag|sa|nv|bv|pty|pvt'
        r')\.?\s*$'
    )
    name = re.sub(suffixes_pattern, '', name, flags=re.IGNORECASE)

    return name.strip()


@lru_cache(maxsize=5000)
def normalize_for_skip_matching(name: str) -> str:
    """
    Tier B normalization for skip set matching.
    Minimal transformation to preserve specificity.

    Operations:
    1. Unicode NFC normalization
    2. Strip whitespace
    3. Collapse internal whitespace

    Does NOT lowercase or remove punctuation.
    Used for matching against skip sets where case and punctuation matter.

    This preserves the logic from:
    - enhanced_normalizer.py:_normalize_for_skip (lines 1418-1439)
    """
    if not name:
        return ""

    # NFC normalization
    normalized = unicodedata.normalize('NFC', name)

    # Trim whitespace
    normalized = normalized.strip()

    # Collapse internal whitespace to single space
    normalized = re.sub(r'\s+', ' ', normalized)

    return normalized


@lru_cache(maxsize=5000)
def preprocess_text(text: str) -> str:
    """
    Comprehensive text preprocessing for ingredient matching.
    Used by EnhancedDSLDNormalizer for initial ingredient processing.

    Operations:
    1. Lowercase + strip
    2. Remove parenthetical information
    3. Remove brackets and contents
    4. Remove curly braces (keep contents)
    5. Remove trademark symbols
    6. Strip punctuation at ends
    7. Collapse whitespace
    8. Remove common prefixes (dl-, d-, l-, natural, synthetic, organic)
    9. Remove common suffixes (extract, powder, oil, concentrate)

    This preserves the logic from:
    - enhanced_normalizer.py:preprocess_text (lines 225-278)
    """
    if not text:
        return ""

    # Lowercase and strip
    text = text.lower().strip()

    # Remove common parenthetical information
    text = re.sub(r'\([^)]*\)', '', text)

    # Remove brackets and their contents
    text = re.sub(r'\[[^\]]*\]', '', text)

    # Remove curly braces but keep their contents
    text = re.sub(r'[{}]', '', text)

    # Remove trademark symbols
    text = re.sub(r'[™®©]', '', text)

    # Remove extra whitespace and punctuation at ends
    text = text.strip(string.punctuation + string.whitespace)

    # Normalize multiple spaces
    text = re.sub(r'\s+', ' ', text)

    # Remove common prefixes that don't affect matching
    prefixes_to_remove = ['dl-', 'd-', 'l-', 'natural ', 'synthetic ', 'organic ']
    for prefix in prefixes_to_remove:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break

    # Loop suffix removal to handle multiple suffixes like "Extract, Powder"
    suffixes_to_remove = [' extract', ' powder', ' oil', ' concentrate']
    changed = True
    while changed:
        changed = False
        # Strip punctuation first
        text = text.strip(string.punctuation + string.whitespace)
        for suffix in suffixes_to_remove:
            if text.endswith(suffix):
                text = text[:-len(suffix)]
                changed = True
                break

    # Final cleanup
    text = text.strip(string.punctuation + string.whitespace)

    return text.strip()


@lru_cache(maxsize=5000)
def strip_extraction_noise(text: str) -> str:
    """
    Strip extraction/dosage noise prefixes from ingredient names.

    Handles patterns commonly found in supplement labels where the actual
    ingredient is buried after dosage or sourcing information:

    - "providing X mg of Y" → "Y"
    - "providing X mg Y" → "Y"
    - "from X mg of Y" → "Y"
    - "from X mg Y" → "Y"
    - "min. X mg Y" → "Y"
    - "minimum X mg Y" → "Y"
    - "Contains X mg of Y" → "Y"
    - "yielding X mg of Y" → "Y"
    - "standardized to X% Y" → "Y"
    - "standardized for X mg Y" → "Y"
    - "supplying X mg of Y" → "Y"
    - "delivering X mg of Y" → "Y"

    Examples:
        "Fish Oil (providing 180 mg of EPA)" → "EPA"
        "from 500 mg of Green Tea Extract" → "Green Tea Extract"
        "standardized to 95% curcuminoids" → "curcuminoids"
        "min. 50 mg silymarin" → "silymarin"

    Returns: cleaned ingredient name with noise stripped
    """
    if not text:
        return ""

    # Work on lowercased version for pattern matching
    lower_text = text.lower().strip()

    # Patterns to strip (order matters - more specific first)
    # Each pattern captures the meaningful ingredient at the end
    extraction_patterns = [
        # "providing X mg/mcg/g of Y" or "providing X mg/mcg/g Y"
        r'^.*?providing\s+[\d,.]+\s*(?:mg|mcg|g|iu|µg)\s+(?:of\s+)?(.+)$',
        # "from X mg/mcg/g of Y" or "from X mg/mcg/g Y"
        r'^.*?from\s+[\d,.]+\s*(?:mg|mcg|g|iu|µg)\s+(?:of\s+)?(.+)$',
        # "yielding X mg/mcg/g of Y" or "yielding X mg/mcg/g Y"
        r'^.*?yielding\s+[\d,.]+\s*(?:mg|mcg|g|iu|µg)\s+(?:of\s+)?(.+)$',
        # "supplying X mg/mcg/g of Y" or "supplying X mg/mcg/g Y"
        r'^.*?supplying\s+[\d,.]+\s*(?:mg|mcg|g|iu|µg)\s+(?:of\s+)?(.+)$',
        # "delivering X mg/mcg/g of Y" or "delivering X mg/mcg/g Y"
        r'^.*?delivering\s+[\d,.]+\s*(?:mg|mcg|g|iu|µg)\s+(?:of\s+)?(.+)$',
        # "contains X mg/mcg/g of Y" or "containing X mg/mcg/g Y"
        r'^.*?contain(?:s|ing)\s+[\d,.]+\s*(?:mg|mcg|g|iu|µg)\s+(?:of\s+)?(.+)$',
        # "min. X mg Y" or "minimum X mg Y"
        r'^.*?(?:min\.?|minimum)\s+[\d,.]+\s*(?:mg|mcg|g|iu|µg)\s+(?:of\s+)?(.+)$',
        # "standardized to X% Y"
        r'^.*?standardized\s+to\s+[\d,.]+\s*%\s+(?:of\s+)?(.+)$',
        # "standardized for X mg Y"
        r'^.*?standardized\s+for\s+[\d,.]+\s*(?:mg|mcg|g|iu|µg)\s+(?:of\s+)?(.+)$',
        # "equivalent to X mg of Y"
        r'^.*?equivalent\s+to\s+[\d,.]+\s*(?:mg|mcg|g|iu|µg)\s+(?:of\s+)?(.+)$',
        # "with X mg of Y"
        r'^.*?with\s+[\d,.]+\s*(?:mg|mcg|g|iu|µg)\s+(?:of\s+)?(.+)$',
    ]

    for pattern in extraction_patterns:
        match = re.match(pattern, lower_text, re.IGNORECASE)
        if match:
            extracted = match.group(1).strip()
            # Remove trailing punctuation and parentheses
            extracted = extracted.rstrip('.,;:()[]')
            if extracted:
                return extracted

    # No pattern matched, return original (stripped)
    return text.strip()


def validate_normalized_key(key: str) -> Tuple[bool, str]:
    """
    Validate that a string is a valid normalized_key format.

    Valid keys:
    - Only contain lowercase letters, numbers, and underscores
    - Do not start or end with underscores
    - Do not contain consecutive underscores

    Returns: (is_valid, error_message_or_empty)
    """
    if not key:
        return False, "empty key"

    # Check for valid characters
    if not re.match(r'^[a-z0-9_]+$', key):
        return False, "contains invalid characters (only a-z, 0-9, _ allowed)"

    # Check for leading/trailing underscores
    if key.startswith('_') or key.endswith('_'):
        return False, "starts or ends with underscore"

    # Check for consecutive underscores
    if '__' in key:
        return False, "contains consecutive underscores"

    return True, ""


def normalize_exact_text(text: str) -> str:
    """
    Minimal normalization for exact matching.
    Only lowercase and trim to preserve punctuation and symbols.

    Used when punctuation-sensitive matching is needed.
    """
    if not text:
        return ""
    return text.strip().lower()


# Module-level cache clear function for testing
def clear_caches():
    """Clear all LRU caches. Useful for testing."""
    normalize_text.cache_clear()
    make_normalized_key.cache_clear()
    normalize_company_name.cache_clear()
    normalize_for_skip_matching.cache_clear()
    preprocess_text.cache_clear()
    strip_extraction_noise.cache_clear()
