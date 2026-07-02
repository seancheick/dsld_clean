#!/usr/bin/env python3
"""
DSLD Supplement Enrichment System v3.0.0
=========================================
Lean, focused enrichment pipeline that collects data for scoring.
NO scoring calculations - only data collection and organization.

Architecture: Modular "pipe and filter" pattern with separation of concerns.
- Each collector method gathers data from specific databases
- No score calculations (scoring script handles all math)
- Clear output structure designed for scoring consumption

Usage:
    python enrich_supplements_v3.py
    python enrich_supplements_v3.py --config config/enrichment_config.json
    python enrich_supplements_v3.py --dry-run

Author: PharmaGuide Team
Version: 3.0.0
"""

import copy
import json
import os
import sys
import re
import logging
import argparse
import traceback
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

# Optional tqdm import for progress bars
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    tqdm = None

# Optional RapidFuzz for faster/better fuzzy matching
try:
    from rapidfuzz import fuzz as rf_fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    rf_fuzz = None

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from constants import (
    DATA_DIR,
    CERTIFICATION_PATTERNS,
    ALLERGEN_FREE_PATTERNS,
    STANDARDIZATION_PATTERNS,
    VALIDATION_THRESHOLDS,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    CERT_CLAIM_RULES,
    UNIT_CONVERSIONS_DB,
    # Scorable ingredient classification constants
    NON_THERAPEUTIC_PARENT_DENYLIST,
    ADDITIVE_TYPES_SKIP_SCORING,
    BLEND_HEADER_PATTERNS_HIGH_CONFIDENCE,
    BLEND_HEADER_EXACT_NAMES,
    BLEND_HEADER_PATTERNS_LOW_CONFIDENCE,
    EXCIPIENT_NEVER_PROMOTE,
    POTENCY_MARKERS_HIGH_SIGNAL,
    POTENCY_MARKERS_LOW_SIGNAL,
    PSEUDO_UNITS_INVALID,
    ABSORPTION_ENHANCERS_PROMOTE_EXCEPTION,
    SERVING_UNIT_NORMALIZATION_MAP,
    SKIP_REASON_ADDITIVE,
    SKIP_REASON_ADDITIVE_TYPE,
    SKIP_REASON_NESTED_NON_THERAPEUTIC,
    SKIP_REASON_BLEND_HEADER_NO_DOSE,
    SKIP_REASON_BLEND_HEADER_WITH_WEIGHT,
    SKIP_REASON_RECOGNIZED_NON_SCORABLE,
    SKIP_REASON_LABEL_PHRASE,
    SKIP_REASON_NUTRITION_FACT,
    EXCLUDED_LABEL_PHRASES,
    EXCLUDED_NUTRITION_FACTS,
    PROMOTE_REASON_KNOWN_DB,
    PROMOTE_REASON_HAS_DOSE,
    PROMOTE_REASON_PRODUCT_TYPE_RESCUE,
    PROMOTE_REASON_ABSORPTION_ENHANCER,
)

# Import scoring hardening modules
from unit_converter import UnitConverter, ConversionResult
from dosage_normalizer import DosageNormalizer, DosageNormalizationResult
from proprietary_blend_detector import ProprietaryBlendDetector, BlendAnalysisResult
from rda_ul_calculator import RDAULCalculator, NutrientAdequacyResult
import normalization as norm_module  # Single-source normalization
from match_ledger import (
    MatchLedgerBuilder,
    DOMAIN_INGREDIENTS,
    DOMAIN_ADDITIVES,
    DOMAIN_ALLERGENS,
    DOMAIN_MANUFACTURER,
    DOMAIN_DELIVERY,
    DOMAIN_CLAIMS,
    METHOD_EXACT,
    METHOD_NORMALIZED,
    METHOD_PATTERN,
    METHOD_CONTAINS,
    METHOD_FUZZY,
)


class SupplementEnricherV3:
    """
    Lean enrichment system focused on data collection for scoring.

    Design Principles:
    1. NO scoring calculations - only data collection
    2. Modular collectors for each scoring section
    3. Clear separation between enrichment and scoring
    4. Preserve all cleaned data, add enrichment layer
    """

    VERSION = "3.1.0"
    COMPATIBLE_SCORING_VERSIONS = ["3.0.0", "3.0.1", "3.1.0", "3.2.0", "3.3.0"]
    # Allowlist/denylist patterns for banned matching are loaded from config.

    # Required fields for product validation
    # Accept both enrichment-canonical names AND cleaned-output names
    REQUIRED_FIELD_VARIANTS = {
        'dsld_id': ['dsld_id', 'id'],           # enrichment name: [accepted variants]
        'product_name': ['product_name', 'fullName'],
    }
    OPTIONAL_PRODUCT_FIELDS = ['brand_name', 'activeIngredients', 'otherIngredients', 'product_form']

    # Empty schema for validation failures - ensures consistent output structure
    EMPTY_ENRICHMENT_SCHEMA = {
        'ingredient_quality_data': {
            # Schema version
            'quality_data_schema_version': 2,
            # Legacy fields (kept for backward compatibility)
            'ingredients': [], 'premium_form_count': 0, 'unmapped_count': 0,
            'total_active': 0,
            # New two-pass classification fields
            'ingredients_scorable': [],
            'ingredients_skipped': [],
            'unmapped_scorable_count': 0,
            'total_scorable_active_count': 0,
            'skipped_non_scorable_count': 0,
            'skipped_reasons_breakdown': {},
            'promoted_from_inactive': [],
            'blend_only_product': False,
            # Coverage metrics with leak detection
            'total_records_seen': 0,
            'total_ingredients_evaluated': 0,
            'unevaluated_records': 0,
        },
        'delivery_data': {},
        'absorption_data': {},
        'formulation_data': {},
        'contaminant_data': {
            'banned_found': [], 'harmful_found': [], 'allergen_risks': [],
            'allergens': {'found': False, 'allergens': []}
        },
        'compliance_data': {},
        'certification_data': {'certifications_found': []},
        'evidence_data': {},
        'manufacturer_data': {},
        'probiotic_data': {'is_probiotic_product': False},
        'dietary_sensitivity_data': {},
        'rda_ul_data': {},
        'prenatal_coverage': {},
        'product_role': {},
        'proprietary_data': {},
        'enrichment_metadata': {'ready_for_scoring': False}
    }

    @staticmethod
    def validate_product(product: Dict) -> Tuple[bool, List[str]]:
        """
        Validate product structure before enrichment.
        Accepts both enrichment-canonical field names (dsld_id, product_name)
        AND cleaned-output field names (id, fullName).
        Returns: (is_valid, list of issues)
        """
        issues = []

        if not isinstance(product, dict):
            return False, ["Product must be a dictionary"]

        # Check required fields - accept any variant name
        for canonical, variants in SupplementEnricherV3.REQUIRED_FIELD_VARIANTS.items():
            found = False
            value = None
            for variant in variants:
                if variant in product:
                    found = True
                    value = product[variant]
                    break
            if not found:
                issues.append(f"Missing required field: {canonical} (or {variants})")
            elif value is None or value == '':
                issues.append(f"Empty required field: {canonical}")

        # Validate activeIngredients structure if present
        active_ings = product.get('activeIngredients')
        if active_ings is not None:
            if not isinstance(active_ings, list):
                issues.append("activeIngredients must be a list")
            else:
                for i, ing in enumerate(active_ings):
                    if not isinstance(ing, dict):
                        issues.append(f"activeIngredients[{i}] must be a dictionary")

        return len(issues) == 0, issues

    @staticmethod
    def _atomic_write_json(file_path: str, data: Any, indent: int = 2) -> None:
        """
        Write JSON data atomically using tmp file + os.replace().
        Prevents partial writes on crash/interrupt.
        """
        tmp_path = file_path + '.tmp'
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            os.replace(tmp_path, file_path)
        except Exception:
            # Clean up tmp file on failure
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _write_quarantine(self, output_dir: str, file_path: str, error_type: str,
                          message: str, stage: str = "enrichment",
                          traceback_str: str = None) -> None:
        """
        Write structured error record to quarantine directory.
        Used when a batch file fails to parse or process.
        """
        quarantine_dir = os.path.join(output_dir, "quarantine")
        os.makedirs(quarantine_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        quarantine_file = os.path.join(quarantine_dir, f"{base_name}_error.json")

        error_record = {
            "original_file": file_path,
            "error_type": error_type,
            "error_message": message,
            "stage": stage,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "enrichment_version": self.VERSION,
        }
        if traceback_str:
            error_record["traceback"] = traceback_str

        try:
            self._atomic_write_json(quarantine_file, error_record)
            self.logger.warning(f"Quarantine record written: {quarantine_file}")
        except Exception as e:
            self.logger.error(f"Failed to write quarantine: {e}")

    def __init__(self, config_path: str = "config/enrichment_config.json"):
        """Initialize enrichment system with configuration"""
        self.logger = self._setup_logging()
        self.config = self._load_config(config_path)
        self.databases = {}
        self._load_all_databases()
        self._compile_patterns()

        # Track unmapped ingredients across batch
        self.unmapped_tracker = {}
        self.match_counters = {
            "pattern_match_wins_count": 0,
            "contains_match_wins_count": 0,
            "parent_fallback_count": 0
        }
        # Track unmapped forms for database expansion
        # Key: raw_form_text, Value: {count, examples, base_names}
        self.unmapped_forms_tracker = {}
        self._rda_ul_warning_count = 0
        self._ambiguity_warning_count = 0
        self._parent_fallback_info_count = 0

        # Initialize scoring hardening modules
        self._init_scoring_modules()

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT,
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        return logging.getLogger(__name__)

    def _init_scoring_modules(self):
        """Initialize scoring hardening modules for evidence collection."""
        try:
            # Unit converter for dosage normalization
            self.unit_converter = UnitConverter()
            self.logger.info("UnitConverter initialized")

            # Dosage normalizer for serving basis
            self.dosage_normalizer = DosageNormalizer(self.unit_converter)
            self.logger.info("DosageNormalizer initialized")

            # Proprietary blend detector
            self.blend_detector = ProprietaryBlendDetector()
            self.logger.info("ProprietaryBlendDetector initialized")

            # RDA/UL calculator
            self.rda_calculator = RDAULCalculator()
            self.logger.info("RDAULCalculator initialized")

        except Exception as e:
            self.logger.warning(
                f"Failed to initialize scoring modules: {e}. "
                "Evidence collection will use fallback methods."
            )
            self.unit_converter = None
            self.dosage_normalizer = None
            self.blend_detector = None
            self.rda_calculator = None

    def _load_config(self, config_path: str) -> Dict:
        """Load enrichment configuration"""
        try:
            # Handle relative paths
            if not os.path.isabs(config_path):
                script_dir = Path(__file__).parent
                config_path = script_dir / config_path

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.logger.info(f"Configuration loaded from {config_path}")
            return config
        except FileNotFoundError:
            self.logger.warning(f"Config not found at {config_path}, using defaults")
            return self._default_config()
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in config file {config_path}: {e}")
            return self._default_config()
        except PermissionError as e:
            self.logger.error(f"Permission denied reading config {config_path}: {e}")
            return self._default_config()
        except (IOError, OSError) as e:
            self.logger.error(f"Failed to read config file {config_path}: {e}")
            return self._default_config()

    def _default_config(self) -> Dict:
        """Return default configuration"""
        return {
            "paths": {
                "input_directory": "output_Lozenges/cleaned",
                "output_directory": "output_Lozenges_enriched",
                "reference_data": "data"
            },
            "processing_config": {
                "batch_size": 100,
                "max_workers": 4,
                "collect_rda_ul_data": True
            },
            "validation": {
                "strict_db_validation": False,
                "_strict_db_validation_note": "Set True in CI to fail-fast on DB key violations"
            },
            "ui": {
                "show_progress_bar": True
            }
        }

    def _load_all_databases(self):
        """Load all reference databases with fail-fast on critical databases"""
        db_paths = self.config.get('database_paths', {})

        # Validate database_paths key exists
        if not db_paths:
            self.logger.warning("No 'database_paths' key in config - using defaults")
            db_paths = {
                "ingredient_quality_map": "data/ingredient_quality_map.json",
                "absorption_enhancers": "data/absorption_enhancers.json",
                "enhanced_delivery": "data/enhanced_delivery.json",
                "standardized_botanicals": "data/standardized_botanicals.json",
                "synergy_cluster": "data/synergy_cluster.json",
                "banned_recalled_ingredients": "data/banned_recalled_ingredients.json",
                "banned_match_allowlist": "data/banned_match_allowlist.json",
                "harmful_additives": "data/harmful_additives.json",
                "allergens": "data/allergens.json",
                "backed_clinical_studies": "data/backed_clinical_studies.json",
                "top_manufacturers_data": "data/top_manufacturers_data.json",
                "manufacturer_violations": "data/manufacturer_violations.json",
                "rda_optimal_uls": "data/rda_optimal_uls.json",
                "clinically_relevant_strains": "data/clinically_relevant_strains.json",
                "color_indicators": "data/color_indicators.json",
                "cert_claim_rules": "data/cert_claim_rules.json",
                # Tiered matching: other_ingredients for recognized-but-non-scorable
                "other_ingredients": "data/other_ingredients.json",
            }

        # Add clinically_relevant_strains if not present
        if "clinically_relevant_strains" not in db_paths:
            db_paths["clinically_relevant_strains"] = "data/clinically_relevant_strains.json"
        if "banned_match_allowlist" not in db_paths:
            db_paths["banned_match_allowlist"] = "data/banned_match_allowlist.json"

        # Define critical databases that must exist
        critical_dbs = {
            "ingredient_quality_map", "harmful_additives",
            "allergens", "banned_recalled_ingredients", "color_indicators"
        }

        script_dir = Path(__file__).parent
        missing_critical = []

        def _db_entry_count(payload: Any) -> int:
            """Return a meaningful entry count for mixed JSON schemas."""
            if isinstance(payload, list):
                return len(payload)
            if isinstance(payload, dict):
                preferred_list_keys = (
                    "ingredients",
                    "allergens",
                    "common_allergens",
                    "harmful_additives",
                    "absorption_enhancers",
                    "botanical_ingredients",
                    "other_ingredients",
                    "nutrient_recommendations",
                    "therapeutic_dosing",
                    "standardized_botanicals",
                    "synergy_clusters",
                    "top_manufacturers",
                    "manufacturer_violations",
                    "proprietary_blend_concerns",
                    "clinically_relevant_strains",
                    "backed_clinical_studies",
                    "studies",
                    "manufacturers",
                    "allowlist",
                    "denylist",
                    "entries",
                )
                for key in preferred_list_keys:
                    value = payload.get(key)
                    if isinstance(value, list):
                        return len(value)
                return len(payload)
            return 0

        for db_name, db_path in db_paths.items():
            try:
                # Handle relative paths
                if not os.path.isabs(db_path):
                    full_path = script_dir / db_path
                else:
                    full_path = Path(db_path)

                if full_path.exists():
                    with open(full_path, 'r', encoding='utf-8') as f:
                        self.databases[db_name] = json.load(f)
                    self.logger.info(f"Loaded {db_name}: {_db_entry_count(self.databases[db_name])} entries")
                else:
                    self.databases[db_name] = {}
                    if db_name in critical_dbs:
                        missing_critical.append(f"{db_name}: {full_path}")
                    else:
                        self.logger.warning(f"Database not found: {db_path}")
            except json.JSONDecodeError as e:
                self.databases[db_name] = {}
                if db_name in critical_dbs:
                    missing_critical.append(f"{db_name}: Invalid JSON - {e}")
                else:
                    self.logger.warning(f"Invalid JSON in {db_name} at {db_path}: {e}")
            except PermissionError as e:
                self.databases[db_name] = {}
                if db_name in critical_dbs:
                    missing_critical.append(f"{db_name}: Permission denied - {e}")
                else:
                    self.logger.warning(f"Permission denied reading {db_name}: {e}")
            except (IOError, OSError) as e:
                self.databases[db_name] = {}
                if db_name in critical_dbs:
                    missing_critical.append(f"{db_name}: {e}")
                else:
                    self.logger.warning(f"Failed to load {db_name}: {e}")

        # FAIL-FAST: Critical database files missing
        if missing_critical:
            raise FileNotFoundError(
                f"CRITICAL: Required database files not found or unreadable:\n"
                + "\n".join(f"  - {m}" for m in missing_critical) +
                f"\n\nEnsure database_paths in config point to valid files."
            )

        # POST-LOAD VALIDATION: Check critical vs recommended databases
        self._validate_loaded_databases()

        self.logger.info(f"Enrichment system initialized with {len(self.databases)} databases")

    def _validate_loaded_databases(self):
        """Validate that required databases are loaded. Critical = fail-fast."""
        critical_dbs = [
            "ingredient_quality_map", "harmful_additives",
            "allergens", "banned_recalled_ingredients",
            "color_indicators",  # P0.5: Required for natural/artificial color classification
        ]
        recommended_dbs = [
            "absorption_enhancers", "standardized_botanicals", "synergy_cluster",
            "backed_clinical_studies", "top_manufacturers_data", "manufacturer_violations",
            "rda_optimal_uls", "clinically_relevant_strains", "enhanced_delivery",
            "cert_claim_rules",  # Required for evidence-based claims detection
            "banned_match_allowlist",
        ]

        # Log reference data versions for auditability
        self._log_reference_versions()

        missing_critical = [db for db in critical_dbs
                           if not self.databases.get(db) or len(self.databases.get(db, {})) == 0]
        if missing_critical:
            raise RuntimeError(
                f"CRITICAL: Required databases missing: {', '.join(missing_critical)}. "
                f"Cannot produce safe enrichment. Ensure files exist in data/"
            )

        missing_recommended = [db for db in recommended_dbs
                               if not self.databases.get(db) or len(self.databases.get(db, {})) == 0]
        if missing_recommended:
            self.logger.warning("RECOMMENDED databases missing: %s", ", ".join(missing_recommended))

        # Validate snake_case key convention for ingredient_quality_map
        quality_map = self.databases.get('ingredient_quality_map', {})
        self._validate_snake_case_keys(quality_map, 'ingredient_quality_map')
        self._validate_banned_match_allowlist()

        # Special validation for cert_claim_rules - claims hardening depends on it
        cert_rules = self.databases.get('cert_claim_rules', {})
        if not cert_rules or len(cert_rules) == 0:
            self.logger.warning(
                "CLAIMS HARDENING DISABLED: cert_claim_rules database is empty or missing. "
                "Evidence-based claim detection will not produce results. "
                "Add 'cert_claim_rules' to database_paths in enrichment_config.json"
            )
        elif 'third_party_programs' not in cert_rules.get('rules', {}):
            self.logger.warning(
                "CLAIMS HARDENING INCOMPLETE: cert_claim_rules missing third_party_programs. "
                "Certification evidence will not be collected."
            )

    def _log_reference_versions(self):
        """Log versions of reference databases for auditability."""
        self.reference_versions = {}

        # Track color_indicators version
        color_db = self.databases.get('color_indicators', {})
        db_info = color_db.get('_metadata', {})
        if db_info:
            version = db_info.get('schema_version', db_info.get('version', 'unknown'))
            last_updated = db_info.get('last_updated', 'unknown')
            self.reference_versions['color_indicators'] = {
                'version': version,
                'last_updated': last_updated
            }
            self.logger.info(
                f"Reference data: color_indicators v{version} (updated: {last_updated})"
            )

        # Track cert_claim_rules version
        cert_rules_db = self.databases.get('cert_claim_rules', {})
        cert_db_info = cert_rules_db.get('_metadata', {})
        if cert_db_info:
            version = cert_db_info.get('schema_version', cert_db_info.get('version', 'unknown'))
            last_updated = cert_db_info.get('last_updated', 'unknown')
            self.reference_versions['cert_claim_rules'] = {
                'version': version,
                'last_updated': last_updated
            }
            self.logger.info(
                f"Reference data: cert_claim_rules v{version} (updated: {last_updated})"
            )

        # Track other versioned databases
        versioned_dbs = [
            'harmful_additives', 'allergens', 'ingredient_quality_map', 'banned_match_allowlist'
        ]
        for db_name in versioned_dbs:
            db = self.databases.get(db_name, {})
            db_info = db.get('_metadata', {})
            if db_info:
                version = db_info.get('version', db_info.get('schema_version', 'unknown'))
                self.reference_versions[db_name] = {'version': version}

    def _validate_banned_match_allowlist(self):
        """
        Validate banned match allowlist/denylist against banned catalog.

        Enforces:
        - Each entry must reference a canonical banned id.
        - Canonical id must exist in banned_recalled_ingredients.
        """
        allowlist_db = self.databases.get('banned_match_allowlist', {}) or {}
        if not allowlist_db:
            return

        banned_db = self.databases.get('banned_recalled_ingredients', {}) or {}
        banned_ids = set()
        for section_data in banned_db.values():
            if isinstance(section_data, list):
                for item in section_data:
                    if isinstance(item, dict) and item.get('id'):
                        banned_ids.add(item['id'])

        errors = []
        for section_key in ('allowlist', 'denylist'):
            for entry in allowlist_db.get(section_key, []) or []:
                entry_id = entry.get('id', 'unknown')
                canonical_id = entry.get('canonical_id')
                if not canonical_id:
                    errors.append(f"{section_key}:{entry_id} missing canonical_id")
                elif canonical_id not in banned_ids:
                    errors.append(
                        f"{section_key}:{entry_id} canonical_id not found: {canonical_id}"
                    )

        if errors:
            message = (
                "BANNED_MATCH_ALLOWLIST validation errors:\n  - " +
                "\n  - ".join(errors)
            )
            strict = self.config.get('validation', {}).get('strict_db_validation', False)
            if strict:
                raise ValueError(message)
            self.logger.warning(message)

    def _validate_snake_case_keys(self, db: Dict, db_name: str):
        """
        Validate database keys follow snake_case convention.

        Enforces:
        - No spaces in keys (use underscores)
        - No duplicate keys (case-insensitive)
        - In strict mode (CI): raises ValueError on violations
        - In normal mode: logs errors for visibility
        """
        if not db:
            return

        # Check if strict validation is enabled (default: False)
        strict_mode = self.config.get('validation', {}).get('strict_db_validation', False)

        invalid_keys = []
        seen_normalized = {}  # normalized_key -> original_key

        for key in db.keys():
            # Skip metadata keys
            if key.startswith('_'):
                continue

            # Check for spaces (should use underscores)
            if ' ' in key:
                invalid_keys.append((key, "contains spaces"))

            # Check for case-insensitive duplicates
            normalized = key.lower().replace(' ', '_')
            if normalized in seen_normalized:
                self.logger.warning(
                    f"{db_name}: Possible duplicate key detected: "
                    f"'{key}' and '{seen_normalized[normalized]}' normalize to same value"
                )
            seen_normalized[normalized] = key

        if invalid_keys:
            violations = "; ".join([f"'{k}' ({reason})" for k, reason in invalid_keys])
            error_msg = (
                f"{db_name}: Key naming convention violations detected: {violations}. "
                f"Keys must use snake_case (underscores, not spaces)."
            )

            if strict_mode:
                # Fail-fast in CI/strict mode
                raise ValueError(error_msg)
            else:
                # Log error for visibility in normal mode
                self.logger.error(error_msg)

    def _compile_patterns(self):
        """Compile regex patterns for performance"""
        self.compiled_patterns = {
            # Organic certification patterns
            'usda_organic': re.compile(r'\bUSDA\s*Organic\b', re.I),
            'certified_organic': re.compile(r'\bcertified\s+organic\b', re.I),
            'organic_100': re.compile(r'\b100%?\s*organic\b', re.I),
            'made_with_organic': re.compile(r'\bmade\s+with\s+organic\s+ingredients\b', re.I),

            # GMP patterns
            'gmp': re.compile(r'\b(c?GMP|GMP)\s*(certified|compliant|registered|facility)?\b', re.I),
            'nsf_gmp': re.compile(r'\bNSF\s*GMP\b', re.I),
            'fda_registered': re.compile(r'\bFDA[-\s]?registered\s+facility\b', re.I),

            # Batch traceability
            'coa': re.compile(r'\b(certificate\s+of\s+analysis|COA)\b', re.I),
            'qr_code': re.compile(r'\bQR\s*code\b', re.I),
            'batch_lookup': re.compile(r'\b(batch|lot)\s+(lookup|search|verify)\b', re.I),

            # Country of origin
            'made_usa': re.compile(r'\b(made|manufactured|produced)\s+in\s+(the\s+)?USA\b', re.I),
            'made_eu': re.compile(r'\b(made|manufactured|produced)\s+in\s+(the\s+)?(EU|European\s+Union|Germany|France|Italy|Netherlands|Sweden|Denmark|Switzerland)\b', re.I),

            # Physician formulated
            'physician': re.compile(r'\b(doctor|physician|md)[-\s]?formulated\b', re.I),

            # Sustainability
            'sustainability': re.compile(r'\b(glass\s+(bottle|jar|container)|recyclable|recycled|compostable|biodegradable|eco[-\s]?friendly|plastic[-\s]?free)\b', re.I),

            # CFU extraction for probiotics
            'cfu_billion': re.compile(r'(\d+(?:\.\d+)?)\s*billion\s*(CFU|cfus|cfu|live|bacteria|cultures)?', re.I),
            'cfu_billion_abbrev': re.compile(r'(\d+(?:\.\d+)?)\s*B\s*(CFU|cfus|cfu)\b', re.I),  # "1.5 B CFU" format
            'cfu_million': re.compile(r'(\d+(?:\.\d+)?)\s*million\s*(CFU|cfus|cfu|live|bacteria|cultures)?', re.I),
            'cfu_expiration': re.compile(r'(until\s+expiration|through\s+shelf\s+life|at\s+expiration|guaranteed\s+through)', re.I),
            'cfu_manufacture': re.compile(r'(at\s+manufacture|when\s+manufactured|at\s+time\s+of\s+manufacture)', re.I),

            # Standardization percentage
            'standardized_pct': re.compile(r'standardized\s+to\s+(\d+(?:\.\d+)?)\s*%', re.I),
            'pct_compound': re.compile(r'(\d+(?:\.\d+)?)\s*%\s*([a-zA-Z\s]+)', re.I),

            # Unsubstantiated claims (egregious only)
            'disease_claims': re.compile(r'\b(treats?|cures?|prevents?|heals?|eliminates?|reverses?)\s+(cancer|diabetes|alzheimer|arthritis|covid|hypertension|heart\s+disease|depression|anxiety)\b', re.I),
            'miracle_claims': re.compile(r'\b(miracle|instant\s+(cure|healing)|100\s*%\s*(cure|effective)|guaranteed\s+results)\b', re.I),
            'fda_approved': re.compile(r'\b(FDA\s+approved|approved\s+by\s+(the\s+)?FDA)\b(?!.*facility)', re.I)
        }

    # =========================================================================
    # CORE MATCHING UTILITIES
    # =========================================================================

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for matching.

        Delegates to normalization module for consistent behavior across pipeline.

        Handles:
        - Case normalization (lowercase)
        - Greek beta (β): Only in known supplement compounds
        - Micro sign (µ): Only before gram units (µg → mcg)
        - Em-dashes, en-dashes → regular hyphen
        - Numeric slashes (1/2 → 1 2)
        - Commas, middle dots → space
        - Trademark/copyright symbols removed
        - Whitespace collapsed
        """
        return norm_module.normalize_text(text)

    def _normalize_exact_text(self, text: str) -> str:
        """
        Minimal normalization for exact matching.
        Only lowercase and trim to preserve punctuation and symbols.

        Delegates to normalization module for consistency.
        """
        return norm_module.normalize_exact_text(text)

    def _normalize_company_name(self, name: str) -> str:
        """
        Normalize company name for matching.
        Removes common suffixes like LLC, Inc, Corp, etc.

        Delegates to normalization module for consistency.
        """
        return norm_module.normalize_company_name(name)

    def _extract_form_from_label(self, label: str) -> Dict[str, Any]:
        """
        Extract base ingredient name and form specifications from complex labels.

        Handles patterns like:
        - "Vitamin A (as retinyl palmitate and 50% B-carotene)"
        - "Vitamin C (as ascorbic acid)"
        - "Vitamin D (as AlgeD3® cholecalciferol [D3] from algae)"
        - "Vitamin B6 (as pyridoxal 5'-phosphate monohydrate [P-5-P])"
        - "Vitamin B12 (as adenosylcobalamin and methylcobalamin)"

        Returns dict with:
        - original: The original label text (immutable)
        - base_name: The ingredient name before parentheses (e.g., "Vitamin A")
        - extracted_forms: List of form info dicts with:
            - raw_form_text: exact extracted string (immutable)
            - match_candidates: list of strings to try for matching (includes bracket tokens)
            - display_form: human-readable cleaned version
            - percent_share: float or None (e.g., 0.50 for "50%")
        - is_dual_form: True if multiple forms detected
        - form_extraction_success: True if any forms were extracted
        - has_form_evidence: True if label has "(as ...)" or bracket forms (mapping should not downgrade to unspecified)
        """
        result = {
            'original': label,
            'base_name': None,
            'extracted_forms': [],
            'is_dual_form': False,
            'form_extraction_success': False,
            'has_form_evidence': False
        }

        if not label:
            return result

        # Extract base name (before parentheses or brackets)
        base_match = re.match(r'^([^(\[]+)', label)
        if base_match:
            result['base_name'] = base_match.group(1).strip()

        # Check for form evidence patterns
        has_as_pattern = bool(re.search(r'\(as\s+', label, re.IGNORECASE))
        has_bracket_form = bool(re.search(r'\[[A-Z0-9\-]+\]', label))
        result['has_form_evidence'] = has_as_pattern or has_bracket_form

        # Extract bracket tokens BEFORE cleaning (these are valuable match candidates)
        bracket_tokens = re.findall(r'\[([^\]]+)\]', label)
        # Filter out vitamin identity brackets like "[Vitamin B1]"
        form_bracket_tokens = [
            t for t in bracket_tokens
            if not re.match(r'^Vitamin\s+[A-Z]\d*$', t, re.IGNORECASE)
        ]

        # Extract '(as ...)' form specification - common pattern
        as_match = re.search(r'\(as\s+(.+?)\)(?:\s*$|\s*,|\s*\[)', label, re.IGNORECASE)
        if not as_match:
            # Try without trailing boundary
            as_match = re.search(r'\(as\s+(.+)\)', label, re.IGNORECASE)

        if as_match:
            form_text = as_match.group(1).strip()

            # Check for dual forms (e.g., "retinyl palmitate and 50% B-carotene")
            if ' and ' in form_text.lower():
                result['is_dual_form'] = True
                parts = re.split(r'\s+and\s+', form_text, flags=re.IGNORECASE)
                total_explicit_percent = 0.0
                forms_with_percent = []

                for part in parts:
                    form_info = self._parse_single_form(part, form_bracket_tokens)
                    if form_info:
                        forms_with_percent.append(form_info)
                        if form_info['percent_share'] is not None:
                            total_explicit_percent += form_info['percent_share']

                # Distribute remaining percentage if needed
                if forms_with_percent:
                    forms_without_percent = [f for f in forms_with_percent if f['percent_share'] is None]
                    if forms_without_percent and total_explicit_percent < 1.0:
                        remaining = 1.0 - total_explicit_percent
                        # Check for weird percentages
                        if total_explicit_percent > 1.0:
                            # Fallback to equal weight and log
                            self.logger.warning(
                                f"Percentage sum > 100% in label '{label}', using equal weight"
                            )
                            equal_share = 1.0 / len(forms_with_percent)
                            for f in forms_with_percent:
                                f['percent_share'] = equal_share
                        else:
                            per_form = remaining / len(forms_without_percent)
                            for f in forms_without_percent:
                                f['percent_share'] = per_form
                    elif not forms_without_percent and abs(total_explicit_percent - 1.0) > 0.01:
                        # All have percentages but don't sum to 100 - normalize
                        if total_explicit_percent > 0:
                            for f in forms_with_percent:
                                if f['percent_share'] is not None:
                                    f['percent_share'] /= total_explicit_percent

                result['extracted_forms'] = forms_with_percent
            else:
                # Single form
                form_info = self._parse_single_form(form_text, form_bracket_tokens)
                if form_info:
                    form_info['percent_share'] = 1.0  # Single form = 100%
                    result['extracted_forms'] = [form_info]

        result['form_extraction_success'] = len(result['extracted_forms']) > 0
        return result

    def _parse_single_form(self, form_text: str, bracket_tokens: List[str]) -> Optional[Dict]:
        """
        Parse a single form specification into structured data.

        Returns dict with:
        - raw_form_text: exact extracted string (immutable)
        - match_candidates: list of strings to try for matching
        - display_form: human-readable cleaned version
        - percent_share: float or None
        """
        if not form_text or not form_text.strip():
            return None

        raw_text = form_text.strip()

        # Extract percentage if present (e.g., "50% B-carotene")
        percent_share = None
        percent_match = re.match(r'^(\d+(?:\.\d+)?)\s*%\s*(.+)$', raw_text)
        if percent_match:
            percent_share = float(percent_match.group(1)) / 100.0
            raw_text = percent_match.group(2).strip()

        # Build match candidates (preserve bracket tokens!)
        match_candidates = []

        # 1. Original text (with TM removed but brackets preserved)
        candidate1 = re.sub(r'[®™]', '', raw_text).strip()
        if candidate1:
            match_candidates.append(candidate1)

        # 2. Text with brackets removed (for display matching)
        candidate2 = re.sub(r'\s*\[[^\]]*\]', '', candidate1).strip()
        if candidate2 and candidate2 != candidate1:
            match_candidates.append(candidate2)

        # 3. Add bracket tokens as separate candidates (e.g., "P-5-P", "D3", "L-5-MTHF Ca")
        for token in bracket_tokens:
            token_clean = token.strip()
            if token_clean and token_clean.lower() not in [c.lower() for c in match_candidates]:
                match_candidates.append(token_clean)

        # 4. Extract bracket content from this specific form text
        local_brackets = re.findall(r'\[([^\]]+)\]', raw_text)
        for token in local_brackets:
            token_clean = token.strip()
            if token_clean and token_clean.lower() not in [c.lower() for c in match_candidates]:
                match_candidates.append(token_clean)

        # 5. Add hyphen variants (e.g., "P-5-P" -> "P5P")
        for candidate in list(match_candidates):
            no_hyphen = candidate.replace('-', '')
            if no_hyphen != candidate and no_hyphen.lower() not in [c.lower() for c in match_candidates]:
                match_candidates.append(no_hyphen)

        # 6. Remove "from X" suffix for additional candidate
        from_removed = re.sub(r'\s+from\s+\w+\s*$', '', candidate2, flags=re.IGNORECASE).strip()
        if from_removed and from_removed != candidate2 and from_removed.lower() not in [c.lower() for c in match_candidates]:
            match_candidates.append(from_removed)

        # Display form: cleaned for human readability
        display_form = re.sub(r'[®™]', '', raw_text)
        display_form = re.sub(r'\s*\[[^\]]*\]', '', display_form).strip()
        display_form = re.sub(r'\s+from\s+\w+\s*$', '', display_form, flags=re.IGNORECASE).strip()

        return {
            'raw_form_text': raw_text,
            'match_candidates': match_candidates,
            'display_form': display_form,
            'percent_share': percent_share
        }

    def _fuzzy_company_match(self, name1: str, name2: str, threshold: float = 0.85) -> Tuple[bool, float]:
        """
        Fuzzy match company names using best available method.
        Returns (is_match, similarity_score).

        Handles common cases like:
        - "Healthy Directions" vs "Healthy Directions, LLC"
        - "Dr. David Williams" vs "David Williams"
        - "Thorne" vs "Thorne Research"

        Containment alone is NOT identity: substring/partial scoring is
        deliberately avoided because it cross-matches distinct companies that
        share a generic token ("HUM Nutrition" vs "Goli Nutrition", brand
        "Country Life ..." vs "Garden of Life"). Match paths:
        1. normalized-equal -> 1.0
        2. multi-token strict subset (suffix/prefix variations of the same
           name, e.g. "Dr. David Williams" ~ "David Williams")
        3. single-token subset only for a distinctive leading brand token
           ("Thorne" ~ "Thorne Research"), never possessives ("Nature's")
        4. otherwise plain similarity, near-exact only (typo tolerance)
        """
        if not name1 or not name2:
            return False, 0.0

        # Normalize company names (removes LLC, Inc, etc.)
        norm1 = self._normalize_company_name(name1)
        norm2 = self._normalize_company_name(name2)

        # Exact match after normalization
        if norm1 == norm2:
            return True, 1.0

        # Empty after normalization
        if not norm1 or not norm2:
            return False, 0.0

        if RAPIDFUZZ_AVAILABLE:
            score = rf_fuzz.WRatio(norm1, norm2) / 100.0
        else:
            score = SequenceMatcher(None, norm1, norm2).ratio()

        tokens1 = norm1.split()
        tokens2 = norm2.split()
        set1, set2 = set(tokens1), set(tokens2)

        if set1 != set2 and (set1 < set2 or set2 < set1):
            # One name's tokens are a strict subset of the other's.
            smaller_tokens, larger_tokens = (
                (tokens1, tokens2) if len(set1) < len(set2) else (tokens2, tokens1)
            )
            if len(smaller_tokens) >= 2:
                # Multi-token subset: same name with words added/removed
                # ("dr david williams" ~ "david williams").
                return score >= 0.75, score
            # Single shared token is containment, not identity, unless it is
            # the distinctive leading brand token ("thorne" ~ "thorne research").
            # Generic/possessive fragments ("life", "pure", "nature's") fail.
            token = smaller_tokens[0]
            is_leading_brand_token = (
                larger_tokens[0] == token
                and len(token) >= 6
                and not token.endswith("'s")
            )
            return (is_leading_brand_token and score >= threshold), score

        # No containment relationship: require near-exact similarity
        # (typo tolerance), regardless of the caller-supplied base threshold.
        return score >= max(threshold, 0.90), score

    def _fuzzy_ingredient_match(
        self,
        ingredient_name: str,
        target_name: str,
        aliases: List[str],
        threshold: float = 0.85,
        review_threshold: float = 0.90
    ) -> Optional[Dict]:
        """
        Fuzzy match ingredient names as a FALLBACK for quality matching.

        NOT USED FOR: Banned substance detection (safety-critical - use exact only)
        USED FOR: Ingredient quality/form matching where typos may occur

        Args:
            ingredient_name: The ingredient name to match
            target_name: The canonical target name
            aliases: List of known aliases
            threshold: Minimum score (0-1) to accept match (default 0.85)
            review_threshold: Matches below this score are flagged for review

        Returns:
            Dict with match details or None if no match above threshold.
            Includes: method, matched_alias, score, needs_review
        """
        if not ingredient_name or not target_name:
            return None

        ing_norm = self._normalize_text(ingredient_name)
        if not ing_norm:
            return None

        candidates = [target_name] + aliases
        best_match = None
        best_score = 0.0

        for candidate in candidates:
            cand_norm = self._normalize_text(candidate)
            if not cand_norm:
                continue

            if RAPIDFUZZ_AVAILABLE:
                # Use token_sort_ratio for word order flexibility
                # "Vitamin B12" should match "B12 Vitamin"
                score = rf_fuzz.token_sort_ratio(ing_norm, cand_norm) / 100.0
            else:
                # Fallback to difflib
                score = SequenceMatcher(None, ing_norm, cand_norm).ratio()

            if score > best_score:
                best_score = score
                best_match = candidate

        if best_score < threshold:
            return None

        return {
            "method": "fuzzy",
            "matched_alias": best_match if best_match != target_name else None,
            "score": best_score,
            "needs_review": best_score < review_threshold
        }

    def _exact_match(self, ingredient_name: str, target_name: str, aliases: List[str]) -> bool:
        """Perform exact matching against name and aliases"""
        if not ingredient_name or not target_name:
            return False

        ing_norm = self._normalize_text(ingredient_name)
        target_norm = self._normalize_text(target_name)

        # Direct match
        if ing_norm == target_norm:
            return True

        # Check aliases
        for alias in aliases:
            if ing_norm == self._normalize_text(alias):
                return True

        return False

    def _check_additive_match(
        self,
        ing_name: str,
        std_name: str,
        target_name: str,
        aliases: List[str]
    ) -> Optional[Dict]:
        """
        Check if ingredient matches additive and return match details.

        Returns dict with match_method and matched_alias for provenance tracking,
        or None if no match.

        LABEL NAME PRESERVATION: This method tracks HOW a match occurred
        so we can show the user the canonical name while preserving the
        original label text for audit.
        """
        if not ing_name and not std_name:
            return None

        ing_norm = self._normalize_text(ing_name) if ing_name else ""
        std_norm = self._normalize_text(std_name) if std_name else ""
        target_norm = self._normalize_text(target_name)

        # Check direct match against canonical name
        if ing_norm and ing_norm == target_norm:
            return {"method": "exact", "matched_alias": None}
        if std_norm and std_norm == target_norm:
            return {"method": "exact_via_std", "matched_alias": None}

        # Check alias matches
        for alias in aliases:
            alias_norm = self._normalize_text(alias)
            if ing_norm and ing_norm == alias_norm:
                return {"method": "alias", "matched_alias": alias}
            if std_norm and std_norm == alias_norm:
                return {"method": "alias_via_std", "matched_alias": alias}

        return None

    def _token_bounded_match(
        self, ingredient_name: str, target_name: str, aliases: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Match target/aliases as whole tokens within ingredient string.
        Prevents substring collisions while allowing bounded matches in longer strings.
        """
        if not ingredient_name or not target_name:
            return False, None

        ing_norm = self._normalize_text(ingredient_name)
        if not ing_norm:
            return False, None

        candidates = [target_name] + aliases
        for candidate in candidates:
            cand_norm = self._normalize_text(candidate)
            if not cand_norm:
                continue
            if ing_norm == cand_norm:
                return True, candidate
            pattern = r'(?<![a-z0-9])' + re.escape(cand_norm) + r'(?![a-z0-9])'
            if re.search(pattern, ing_norm):
                return True, candidate

        return False, None

    def _is_low_precision_token_alias(self, alias: str) -> bool:
        """
        Reject low-information aliases for token-bounded matching.

        These phrases are too generic and create false positives
        (e.g. "mushroom extract", "disodium salt").
        """
        alias_norm = self._normalize_text(alias)
        if not alias_norm:
            return True

        explicit_deny = {
            "disodium salt",
            "mushroom extract",
            "functional mushroom blend",
            "extract",
            "blend",
            "powder",
            "oil",
            "salt",
        }
        if alias_norm in explicit_deny:
            return True

        generic_tokens = {
            "functional", "proprietary", "natural", "organic",
            "extract", "blend", "powder", "oil", "salt",
            "disodium", "sodium",
        }
        tokens = [t for t in re.split(r"[\s/-]+", alias_norm) if t]
        if not tokens:
            return True

        informative = [
            t for t in tokens
            if len(t) >= 4 and t not in generic_tokens and not t.isdigit()
        ]
        return len(informative) == 0

    def _filter_safe_token_aliases(self, target_name: str, aliases: List[str]) -> List[str]:
        """Return aliases safe for token-bounded matching."""
        safe = []
        for alias in aliases:
            if not self._is_low_precision_token_alias(alias):
                safe.append(alias)

        # Always include canonical target if present.
        if target_name:
            safe.insert(0, target_name)
        return safe

    def _token_match_has_required_context(
        self,
        ingredient_name: str,
        banned_item: Dict[str, Any],
        matched_variant: Optional[str],
    ) -> bool:
        """
        Require domain context for high-collision categories (e.g. colorants).
        """
        ingredient_norm = self._normalize_text(ingredient_name)
        category = self._normalize_text(banned_item.get("category", ""))
        class_tags = [self._normalize_text(t) for t in banned_item.get("class_tags", []) if isinstance(t, str)]
        banned_name = self._normalize_text(banned_item.get("standard_name", ""))
        matched_norm = self._normalize_text(matched_variant or "")

        is_colorant = (
            "color" in category
            or "colour" in category
            or any("color" in t or "colour" in t for t in class_tags)
            or banned_name in {"orange b", "red 40", "blue 1"}
        )
        if not is_colorant:
            return True

        # If we matched the canonical banned color token itself, allow.
        if matched_norm and matched_norm == banned_name:
            return True

        # Otherwise require explicit color context in label ingredient text.
        return bool(
            re.search(r"(?<![a-z0-9])(dye|color|colour|fd\s*&\s*c|fdc|lake|pigment)(?![a-z0-9])", ingredient_norm)
        )

    def _hyphen_space_token_pattern(self, variant: str) -> Optional[re.Pattern]:
        """Build a token-bounded regex that tolerates hyphens/spaces between tokens."""
        norm = self._normalize_text(variant)
        if not norm:
            return None
        tokens = [t for t in re.split(r'[\s-]+', norm) if t]
        if not tokens:
            return None
        pattern = r'(?<![a-z0-9])' + r'[-\s]+'.join(map(re.escape, tokens)) + r'(?![a-z0-9])'
        return re.compile(pattern)

    def _allowlist_match(self, ingredient_name: str, allowlist_entries: List[Dict]) -> Optional[Dict]:
        """Match against explicit banned allowlist rules with bounded policies."""
        if not ingredient_name:
            return None

        ing_norm = self._normalize_text(ingredient_name)
        if not ing_norm:
            return None

        for entry in allowlist_entries:
            policy = entry.get("match_policy", "token_bounded")
            variants = entry.get("variants", []) or []
            variants_regex = entry.get("variants_regex", []) or []

            if policy == "token_bounded_hyphen_space":
                for variant in variants:
                    pattern = self._hyphen_space_token_pattern(variant)
                    if pattern and pattern.search(ing_norm):
                        return {
                            "match_method": f"allowlist_{policy}",
                            "matched_variant": variant,
                            "allowlist_id": entry.get("id", ""),
                        }
            elif policy == "token_bounded_regex":
                for pattern in variants_regex:
                    if re.search(pattern, ing_norm):
                        return {
                            "match_method": f"allowlist_{policy}",
                            "matched_variant": pattern,
                            "allowlist_id": entry.get("id", ""),
                        }
            else:
                for variant in variants:
                    matched, matched_variant = self._token_bounded_match(ingredient_name, variant, [])
                    if matched:
                        return {
                            "match_method": "allowlist_token_bounded",
                            "matched_variant": matched_variant or variant,
                            "allowlist_id": entry.get("id", ""),
                        }

        return None

    def _denylist_match(self, ingredient_name: str, denylist_entries: List[Dict]) -> Optional[Dict]:
        """Match against explicit denylist rules to prevent false positives."""
        if not ingredient_name:
            return None

        ing_norm = self._normalize_text(ingredient_name)
        if not ing_norm:
            return None

        for entry in denylist_entries:
            policy = entry.get("match_policy", "token_bounded")
            pattern = entry.get("pattern")
            variants = entry.get("variants", []) or []

            if pattern:
                if re.search(pattern, ing_norm):
                    return {
                        "denylist_id": entry.get("id", ""),
                        "matched_pattern": pattern,
                    }
            elif policy == "token_bounded_hyphen_space":
                for variant in variants:
                    compiled = self._hyphen_space_token_pattern(variant)
                    if compiled and compiled.search(ing_norm):
                        return {
                            "denylist_id": entry.get("id", ""),
                            "matched_pattern": variant,
                        }
            else:
                for variant in variants:
                    matched, matched_variant = self._token_bounded_match(ingredient_name, variant, [])
                    if matched:
                        return {
                            "denylist_id": entry.get("id", ""),
                            "matched_pattern": matched_variant or variant,
                        }

        return None

    def _strain_match(self, strain_name: str, target_name: str, aliases: List[str]) -> bool:
        """
        Match probiotic strain names with support for:
        - Genus abbreviations (L. reuteri = Lactobacillus reuteri)
        - Genus name changes (Limosilactobacillus reuteri = Lactobacillus reuteri)
        - Strain IDs (ATCC PTA 5289, DSM 17938)
        """
        if not strain_name or not target_name:
            return False

        # First try exact match
        if self._exact_match(strain_name, target_name, aliases):
            return True

        # Normalize for comparison
        strain_norm = self._normalize_text(strain_name)

        # Map of genus name variations (old/new nomenclature)
        genus_mappings = {
            'limosilactobacillus': ['lactobacillus', 'l'],
            'lactobacillus': ['limosilactobacillus', 'l'],
            'lacticaseibacillus': ['lactobacillus', 'l'],
            'lactiplantibacillus': ['lactobacillus', 'l'],
            'bifidobacterium': ['b'],
            'streptococcus': ['s'],
            'bacillus': ['b'],
            'saccharomyces': ['s'],
        }

        # Extract strain ID patterns (e.g., "ATCC PTA 5289", "DSM 17938", "K12", "M18")
        strain_id_pattern = re.compile(r'(atcc\s*(?:pta\s*)?[\d]+|dsm\s*[\d]+|ncfm|gg|k12|m18|bb-?12|bb536|hn019|bi-?07|de111|299v)', re.IGNORECASE)
        strain_ids = strain_id_pattern.findall(strain_norm)

        # Extract species name (second word, e.g., "reuteri", "rhamnosus")
        words = strain_norm.split()
        species = words[1] if len(words) > 1 else None

        # Check all aliases with genus normalization
        all_targets = [target_name] + aliases
        for target in all_targets:
            target_norm = self._normalize_text(target)
            target_words = target_norm.split()
            target_species = target_words[1] if len(target_words) > 1 else None

            # If species match, check genus compatibility
            if species and target_species and species == target_species:
                # Check if strain IDs match (if present in both)
                target_ids = strain_id_pattern.findall(target_norm)
                if strain_ids and target_ids:
                    # Normalize IDs for comparison
                    strain_ids_norm = {re.sub(r'\s+', '', sid.lower()) for sid in strain_ids}
                    target_ids_norm = {re.sub(r'\s+', '', tid.lower()) for tid in target_ids}
                    if strain_ids_norm & target_ids_norm:  # If any ID matches
                        return True
                elif not strain_ids and not target_ids:
                    # No strain IDs in either - match on genus/species
                    strain_genus = words[0] if words else ''
                    target_genus = target_words[0] if target_words else ''

                    # Direct genus match or abbreviated match
                    if strain_genus == target_genus:
                        return True
                    # Check if abbreviated (e.g., "l" matches "lactobacillus")
                    if target_genus in genus_mappings.get(strain_genus, []):
                        return True
                    if strain_genus in genus_mappings.get(target_genus, []):
                        return True

            # Check for substring match with strain ID
            if strain_ids:
                for sid in strain_ids:
                    sid_norm = re.sub(r'\s+', '', sid.lower())
                    if sid_norm in re.sub(r'\s+', '', target_norm):
                        # Also verify species matches
                        if species and species in target_norm:
                            return True

        return False

    def _get_safe_text_field(self, product: Dict, field: str) -> str:
        """Safely extract text from field that may be string or dict."""
        value = product.get(field, '')
        if isinstance(value, dict):
            return value.get('raw', '') or value.get('text', '') or ''
        elif isinstance(value, str):
            return value
        return ''

    def _get_all_product_text(self, product: Dict) -> str:
        """Combine all product text fields for pattern matching"""
        texts = [
            product.get('fullName', '') or '',
            product.get('brandName', '') or '',
            self._get_safe_text_field(product, 'labelText')
        ]

        # Handle targetGroups - can be list of strings or dicts
        target_groups = product.get('targetGroups', [])
        if target_groups:
            for tg in target_groups:
                if isinstance(tg, str):
                    texts.append(tg)
                elif isinstance(tg, dict):
                    texts.append(tg.get('text', '') or tg.get('name', '') or '')

        # Handle statements - can be list of dicts with 'notes' or 'text' key
        statements = product.get('statements', [])
        if statements:
            for s in statements:
                if isinstance(s, str):
                    texts.append(s)
                elif isinstance(s, dict):
                    # Try multiple possible text fields
                    text = s.get('text', '') or s.get('notes', '') or s.get('type', '') or ''
                    texts.append(text)

        # Handle claims - can be list of dicts with various text fields
        claims = product.get('claims', [])
        if claims:
            for c in claims:
                if isinstance(c, str):
                    texts.append(c)
                elif isinstance(c, dict):
                    # Try multiple possible text fields
                    text = c.get('text', '') or c.get('langualCodeDescription', '') or c.get('notes', '') or ''
                    texts.append(text)

        # Add ingredient names, form names, and notes.
        # Names and forms are part of the searchable label surface: the
        # delivery DB's detection_note explicitly says to search "ingredient
        # forms + product name" (e.g. "Liposomal Vitamin C" as an ingredient
        # is a tier-1 delivery signal). Previously only notes/harvestMethod
        # were included, so ingredient-level signals were invisible to every
        # pattern scanner.
        for ing in product.get('activeIngredients', []):
            texts.append(ing.get('name', '') or '')
            texts.append(ing.get('notes', '') or '')
            texts.append(ing.get('harvestMethod', '') or '')
            for form in ing.get('forms', []) or []:
                if isinstance(form, dict):
                    texts.append(form.get('name', '') or '')
                elif form:
                    texts.append(str(form))

        return ' '.join(filter(None, texts))

    # =========================================================================
    # SECTION A: INGREDIENT QUALITY DATA COLLECTORS
    # =========================================================================

    def _collect_ingredient_quality_data(self, product: Dict) -> Dict:
        """
        Collect ingredient quality data for scoring Section A1-A2.

        TWO-PASS CLASSIFICATION SYSTEM:
        - Pass 1: Filter activeIngredients into scorable vs skipped (non-scorable)
        - Pass 2: Rescue therapeutic actives from inactiveIngredients

        This prevents inflation of unmapped_count from excipients, sweeteners,
        and blend header rows that should never be quality-scored.

        Returns bio_score, dosage_importance, form matches - NO calculations.
        """
        quality_map = self.databases.get('ingredient_quality_map', {})
        botanicals_db = self.databases.get('standardized_botanicals', {})
        active_ingredients = product.get('activeIngredients', [])
        inactive_ingredients = product.get('inactiveIngredients', [])

        # Track classification results
        ingredients_scorable = []
        ingredients_skipped = []
        promoted_from_inactive = []
        skipped_reasons_breakdown = {}
        blend_header_rows = []

        # Legacy tracking (backward compatibility)
        all_quality_data = []
        premium_form_count = 0
        legacy_unmapped_count = 0

        # New scorable-only tracking
        unmapped_scorable_count = 0
        recognized_non_scorable_count = 0  # Tiered matching: recognized but not therapeutic
        pattern_match_wins_count = 0
        contains_match_wins_count = 0
        parent_fallback_count = 0

        # =================================================================
        # PASS 1: Classify activeIngredients as scorable or skipped
        # =================================================================
        for ingredient in active_ingredients:
            # Use branded_token_extracted for matching if present (e.g., "KSM-66" from "KSM-66 Ashwagandha Root Extract")
            ing_name = ingredient.get('branded_token_extracted') or ingredient.get('name', '')
            std_name = ingredient.get('standardName', '') or ing_name
            quantity = ingredient.get('quantity', 0)
            unit = ingredient.get('unit', '')
            hierarchy_type = ingredient.get('hierarchyType')

            # Check for skip conditions
            skip_reason = self._should_skip_from_scoring(ingredient, quality_map, botanicals_db)

            if skip_reason:
                # Track skip reason breakdown
                skipped_reasons_breakdown[skip_reason] = skipped_reasons_breakdown.get(skip_reason, 0) + 1

                # Track blend headers separately for blend-only detection
                if skip_reason == SKIP_REASON_BLEND_HEADER_NO_DOSE:
                    blend_header_rows.append(ing_name)

                recognition_info = None
                if skip_reason == SKIP_REASON_RECOGNIZED_NON_SCORABLE:
                    recognition_info = self._is_recognized_non_scorable(ing_name, std_name)
                    if recognition_info:
                        recognized_non_scorable_count += 1

                has_dose, _ = self._has_valid_therapeutic_dose(ingredient)
                unit_normalized = self._normalize_unit_for_signal(unit)
                is_excipient, never_promote_reason = self._compute_excipient_flags(ingredient)
                blend_flags = self._compute_blend_flags(ingredient, skip_reason)

                # LABEL NAME PRESERVATION: Track raw label text for skipped items
                raw_source_text = ingredient.get('raw_source_text') or ing_name
                ingredients_skipped.append({
                    # LABEL NAME PRESERVATION:
                    "name": ing_name,  # Label-facing name
                    "raw_source_text": raw_source_text,  # Exact label text (provenance)
                    "standard_name": std_name,
                    "skip_reason": skip_reason,
                    "quantity": quantity,
                    "unit": unit,
                    "unit_normalized": unit_normalized,
                    "has_dose": has_dose,
                    "is_blend_header": blend_flags["is_blend_header"],
                    "is_proprietary_blend": blend_flags["is_proprietary_blend"],
                    "blend_total_weight_only": blend_flags["blend_total_weight_only"],
                    "blend_disclosed_components_count": blend_flags["blend_disclosed_components_count"],
                    "is_excipient": is_excipient,
                    "never_promote_reason": never_promote_reason,
                    "recognition_source": (recognition_info or {}).get("recognition_source"),
                    "recognition_reason": (recognition_info or {}).get("recognition_reason"),
                    "recognition_type": (recognition_info or {}).get("recognition_type"),
                    "recognized_entry_id": (recognition_info or {}).get("matched_entry_id"),
                    "recognized_entry_name": (recognition_info or {}).get("matched_entry_name"),
                    "mapped_identity": bool(recognition_info) or bool(is_excipient),
                    "scoreable_identity": False,
                    "role_classification": "inactive_non_scorable",
                    "identity_confidence": 1.0 if (recognition_info or is_excipient) else 0.0,
                    "identity_decision_reason": skip_reason,
                    "certificates": [],
                    "source_section": "active",
                    "hierarchyType": hierarchy_type
                })
                # DO NOT track as unmapped - these are intentionally not scored
                continue

            # Scorable ingredient - try to match against quality map
            # Pass cleaned forms[] to enable form-aware matching (P0 form-loss fix)
            ingredient_forms = ingredient.get('forms') or []
            match_result = self._match_quality_map(
                ing_name, std_name, quality_map, cleaned_forms=ingredient_forms
            )
            quality_entry = self._build_quality_entry(
                ingredient, match_result, hierarchy_type, source_section="active"
            )
            is_quality_match = bool(
                match_result and isinstance(match_result, dict) and match_result.get("match_status") != "FORM_UNMAPPED"
            )

            if is_quality_match:
                match_tier = match_result.get('match_tier')
                if match_tier == "pattern":
                    pattern_match_wins_count += 1
                elif match_tier == "contains":
                    contains_match_wins_count += 1
                if match_result.get('fallback_form_selected'):
                    parent_fallback_count += 1
                if match_result.get('bio_score', 0) > 12:
                    premium_form_count += 1
            else:
                # TIERED MATCHING (per dev feedback):
                # Before marking as unmapped, check if recognized in other databases
                recognition = self._is_recognized_non_scorable(ing_name, std_name)
                if recognition:
                    # Recognized but non-scorable - don't count as unmapped
                    # Mark in quality_entry for transparency
                    quality_entry['recognized_non_scorable'] = True
                    quality_entry['recognition_source'] = recognition.get('recognition_source')
                    quality_entry['recognition_reason'] = recognition.get('recognition_reason')
                    quality_entry['recognition_type'] = recognition.get('recognition_type')
                    quality_entry['matched_entry_id'] = recognition.get('matched_entry_id')
                    quality_entry['matched_entry_name'] = recognition.get('matched_entry_name')
                    quality_entry['mapped_identity'] = True
                    quality_entry['scoreable_identity'] = False
                    quality_entry['role_classification'] = 'recognized_non_scorable'
                    quality_entry['identity_confidence'] = 1.0
                    quality_entry['identity_decision_reason'] = recognition.get('recognition_reason') or 'recognized_non_scorable'
                    # Track for coverage metrics (separate from unmapped)
                    recognized_non_scorable_count += 1
                else:
                    # Truly unmapped - track as before
                    unmapped_scorable_count += 1
                    legacy_unmapped_count += 1
                    self._track_unmapped(ing_name, 'active')

            ingredients_scorable.append(quality_entry)
            all_quality_data.append(quality_entry)

        # =================================================================
        # PASS 2: Rescue therapeutic actives from inactiveIngredients
        # =================================================================
        for ingredient in inactive_ingredients:
            # Use branded_token_extracted for matching if present
            ing_name = ingredient.get('branded_token_extracted') or ingredient.get('name', '')
            std_name = ingredient.get('standardName', '') or ing_name
            quantity = ingredient.get('quantity', 0)
            unit = ingredient.get('unit', '')
            hierarchy_type = ingredient.get('hierarchyType')

            # Check promotion eligibility
            promotion_result = self._should_promote_to_scorable(
                ingredient, quality_map, botanicals_db, len(ingredients_scorable)
            )

            if promotion_result:
                promotion_reason = promotion_result.get('reason')
                promotion_confidence = promotion_result.get('confidence', 'MEDIUM')
                dose_present = bool(quantity and unit)

                ingredient_forms = ingredient.get('forms') or []
                match_result = self._match_quality_map(
                    ing_name, std_name, quality_map, cleaned_forms=ingredient_forms
                )
                quality_entry = self._build_quality_entry(
                    ingredient, match_result, hierarchy_type,
                    source_section="inactive_promoted",
                    promotion_reason=promotion_reason,
                    promotion_confidence=promotion_confidence,
                    dose_present=dose_present
                )
                is_quality_match = bool(
                    match_result and isinstance(match_result, dict) and match_result.get("match_status") != "FORM_UNMAPPED"
                )

                if is_quality_match:
                    match_tier = match_result.get('match_tier')
                    if match_tier == "pattern":
                        pattern_match_wins_count += 1
                    elif match_tier == "contains":
                        contains_match_wins_count += 1
                    if match_result.get('fallback_form_selected'):
                        parent_fallback_count += 1
                    if match_result.get('bio_score', 0) > 12:
                        premium_form_count += 1
                else:
                    # Apply the same identity fallback used in pass-1 actives.
                    # Promoted inactives can be therapeutically relevant botanicals
                    # that are recognized in non-quality DBs.
                    recognition = self._is_recognized_non_scorable(ing_name, std_name)
                    if recognition:
                        quality_entry['recognized_non_scorable'] = True
                        quality_entry['recognition_source'] = recognition.get('recognition_source')
                        quality_entry['recognition_reason'] = recognition.get('recognition_reason')
                        quality_entry['recognition_type'] = recognition.get('recognition_type')
                        quality_entry['matched_entry_id'] = recognition.get('matched_entry_id')
                        quality_entry['matched_entry_name'] = recognition.get('matched_entry_name')
                        quality_entry['mapped_identity'] = True
                        quality_entry['scoreable_identity'] = False
                        quality_entry['role_classification'] = 'recognized_non_scorable'
                        quality_entry['identity_confidence'] = 1.0
                        quality_entry['identity_decision_reason'] = (
                            recognition.get('recognition_reason') or 'recognized_non_scorable'
                        )
                        recognized_non_scorable_count += 1
                    else:
                        unmapped_scorable_count += 1
                        legacy_unmapped_count += 1
                        self._track_unmapped(ing_name, 'active_promoted')

                ingredients_scorable.append(quality_entry)
                all_quality_data.append(quality_entry)
                # LABEL NAME PRESERVATION
                raw_source_text = ingredient.get('raw_source_text') or ing_name
                promoted_from_inactive.append({
                    "name": ing_name,  # Label-facing name
                    "raw_source_text": raw_source_text,  # Exact label text
                    "promotion_reason": promotion_reason,
                    "promotion_confidence": promotion_confidence,
                    "dose_present": dose_present
                })

        # =================================================================
        # BLEND-ONLY PRODUCT DETECTION
        # =================================================================
        total_scorable = len(ingredients_scorable)
        blend_only_product = (
            total_scorable <= 1 and
            len(blend_header_rows) >= 1 and
            len(active_ingredients) > 1
        )

        # =================================================================
        # BUILD NORMALIZED NAMES SET FOR QUICK LOOKUPS
        # =================================================================
        # Used by scoring for synergy detection, absorption enhancer pairing,
        # and cross-section linking without recomputing normalization
        scorable_names_normalized = set()
        for ing in ingredients_scorable:
            std_name = ing.get('standard_name', '')
            if std_name:
                scorable_names_normalized.add(self._normalize_text(std_name))
            # Also add original name normalized
            orig_name = ing.get('name', '')
            if orig_name:
                scorable_names_normalized.add(self._normalize_text(orig_name))

        # =================================================================
        # COVERAGE METRICS WITH LEAK DETECTION
        # =================================================================
        # Records seen = what entered pass 1 classification (active ingredients)
        total_records_seen = len(active_ingredients)
        total_skipped = len(ingredients_skipped)
        total_promoted = len(promoted_from_inactive)

        # Scorable from pass 1 = total scorable minus promoted from inactive
        scorable_from_pass1 = total_scorable - total_promoted

        # Invariant check: all active records must end up classified
        # scorable_from_pass1 + skipped should equal total_records_seen
        unevaluated_records = total_records_seen - (scorable_from_pass1 + total_skipped)

        # Total evaluated = scorable + skipped (includes promoted in scorable)
        total_ingredients_evaluated = total_scorable + total_skipped

        return {
            # Schema version for forward compatibility
            "quality_data_schema_version": 2,

            # Legacy fields (backward compatibility)
            "ingredients": all_quality_data,
            "premium_form_count": premium_form_count,
            "unmapped_count": legacy_unmapped_count,
            "total_active": len(active_ingredients),

            # New two-pass classification fields
            "ingredients_scorable": ingredients_scorable,
            "ingredients_skipped": ingredients_skipped,
            "unmapped_scorable_count": unmapped_scorable_count,
            "total_scorable_active_count": total_scorable,
            "skipped_non_scorable_count": total_skipped,
            "skipped_reasons_breakdown": skipped_reasons_breakdown,
            "promoted_from_inactive": promoted_from_inactive,
            "blend_only_product": blend_only_product,
            "blend_header_rows": blend_header_rows,

            # Coverage metrics with leak detection
            "total_records_seen": total_records_seen,
            "total_ingredients_evaluated": total_ingredients_evaluated,
            "unevaluated_records": unevaluated_records,  # Should be 0
            "pattern_match_wins_count": pattern_match_wins_count,
            "contains_match_wins_count": contains_match_wins_count,
            "parent_fallback_count": parent_fallback_count,

            # Quick-lookup normalized names for scoring efficiency
            "scorable_ingredient_names_normalized": list(scorable_names_normalized),
        }

    def _has_valid_therapeutic_dose(self, ingredient: Dict) -> Tuple[bool, bool]:
        """
        Validate if ingredient has a valid therapeutic dose.

        Handles edge cases:
        - Quantity as string "0" or "0.0"
        - Unit as whitespace or pseudo-unit ("serving", "n/a", etc.)
        - Unit missing entirely

        Returns:
            (has_dose: bool, is_blend_header_weight: bool)
            - has_dose: True if quantity > 0 AND unit is a valid therapeutic unit
            - is_blend_header_weight: True if has numeric value but might be blend total
        """
        quantity = ingredient.get('quantity')
        unit = ingredient.get('unit', '')

        # Normalize unit
        unit_normalized = (str(unit) if unit is not None else '').strip().lower()

        # Check for pseudo-units (not valid therapeutic doses)
        if unit_normalized in PSEUDO_UNITS_INVALID:
            return (False, False)

        # Empty unit after normalization = no dose
        if not unit_normalized:
            return (False, False)

        # Check quantity is present and meaningful
        if quantity is None:
            return (False, False)

        # Handle string quantities
        if isinstance(quantity, str):
            try:
                quantity = float(quantity.strip())
            except (ValueError, AttributeError):
                return (False, False)

        # Zero or negative quantity = no dose
        if quantity <= 0:
            return (False, False)

        # Valid therapeutic dose found
        return (True, True)

    def _normalize_unit_for_signal(self, unit: Any) -> str:
        """Normalize unit for ingredient-level signals."""
        if unit is None:
            return ""
        unit_normalized = str(unit).strip().lower()
        unit_normalized = unit_normalized.replace('µg', 'mcg').replace('μg', 'mcg')
        unit_normalized = unit_normalized.replace(' ', '')
        return unit_normalized

    def _compute_excipient_flags(self, ingredient: Dict) -> Tuple[bool, Optional[str]]:
        """Determine excipient status for ingredient-level signals."""
        ing_name = (ingredient.get('name', '') or '').strip().lower()
        std_name = (ingredient.get('standardName', '') or ing_name).strip().lower()

        if ingredient.get('isAdditive', False):
            return True, SKIP_REASON_ADDITIVE

        additive_type = ingredient.get('additiveType', '')
        if additive_type and additive_type.lower() in ADDITIVE_TYPES_SKIP_SCORING:
            return True, SKIP_REASON_ADDITIVE_TYPE

        if ing_name in EXCIPIENT_NEVER_PROMOTE or std_name in EXCIPIENT_NEVER_PROMOTE:
            return True, "excipient_never_promote"

        for excipient in EXCIPIENT_NEVER_PROMOTE:
            if excipient in ing_name or excipient in std_name:
                return True, "excipient_never_promote"

        return False, None

    def _compute_blend_flags(self, ingredient: Dict, skip_reason: Optional[str]) -> Dict:
        """Compute blend-related flags for ingredient-level signals."""
        nested = ingredient.get('nestedIngredients') or []
        is_proprietary_blend = bool(
            ingredient.get('proprietaryBlend', False) or ingredient.get('isProprietaryBlend', False)
        )
        is_blend_header = skip_reason in (
            SKIP_REASON_BLEND_HEADER_NO_DOSE,
            SKIP_REASON_BLEND_HEADER_WITH_WEIGHT
        )
        blend_total_weight_only = skip_reason == SKIP_REASON_BLEND_HEADER_WITH_WEIGHT

        return {
            "is_blend_header": is_blend_header,
            "is_proprietary_blend": is_proprietary_blend,
            "blend_total_weight_only": blend_total_weight_only,
            "blend_disclosed_components_count": len(nested) if isinstance(nested, list) else 0
        }

    def _normalize_exclusion_text(self, value: str) -> str:
        """Normalize label text for robust exclusion checks."""
        text = (value or "").lower().strip()
        text = re.sub(r"\s+", " ", text)
        text = text.rstrip(":;,")
        return text

    def _excluded_text_reason(self, value: str) -> Optional[str]:
        """
        Return exclusion reason if text is a known label/header or nutrition rollup.

        Protects against punctuation/casing variants like:
        - "Less than 2%:"
        - "Contains < 2%"
        - "May also contain <2% of:"
        """
        text = self._normalize_exclusion_text(value)
        if not text:
            return None

        if text in EXCLUDED_LABEL_PHRASES:
            return SKIP_REASON_LABEL_PHRASE
        if text in EXCLUDED_NUTRITION_FACTS:
            return SKIP_REASON_NUTRITION_FACT

        # Header/label phrase variants that are never ingredients.
        if re.match(r"^(contains|may also contain)\s*(less than|<)\s*\d+\s*%(\s*of)?", text):
            return SKIP_REASON_LABEL_PHRASE
        if re.match(r"^contains?\s+\d+\s*percent\s+or\s+less(\s+of)?", text):
            return SKIP_REASON_LABEL_PHRASE
        if re.match(r"^less than\s*\d+\s*%(\s*of)?", text):
            return SKIP_REASON_LABEL_PHRASE
        if re.match(r"^<\s*\d+\s*%\s*of", text):
            return SKIP_REASON_LABEL_PHRASE
        # Spec-string fragments emitted by parser; these are not standalone ingredients.
        if re.match(r"^\s*min\.\s*\d+", text):
            return SKIP_REASON_LABEL_PHRASE
        if re.match(r"^\s*providing(?:\s+minimum)?\s+\d+", text):
            return SKIP_REASON_LABEL_PHRASE
        if re.match(r"^\s*standardized\s+to\s+contain(?:ing)?\s+\d+", text):
            return SKIP_REASON_LABEL_PHRASE
        if re.match(r"^\s*from\s+\d+(?:,\d{3})?(?:\.\d+)?\s*(mg|mcg|g|iu|billion|million)\b", text):
            return SKIP_REASON_LABEL_PHRASE

        # Nutrition rollup variants.
        if re.match(r"^other omega[- ]\d+\s+fatty acids$", text):
            return SKIP_REASON_NUTRITION_FACT
        if re.match(r"^other omega\s+fatty acids$", text):
            return SKIP_REASON_NUTRITION_FACT

        return None

    def _should_skip_from_scoring(self, ingredient: Dict, quality_map: Dict, botanicals_db: Dict) -> Optional[str]:
        """
        Determine if an ingredient should be SKIPPED from quality scoring.

        Skip Group Z (unconditional, before any override):
        - Exact match in BLEND_HEADER_EXACT_NAMES
        - Exact match in EXCLUDED_LABEL_PHRASES (e.g., "Contains less than 2%")
        - Exact match in EXCLUDED_NUTRITION_FACTS (e.g., "Other Omega-3 Fatty Acids")

        Skip Group A (high confidence):
        - isAdditive == true
        - additiveType is present
        - isNestedIngredient under non-therapeutic parent

        Skip Group B (header rows):
        - Matches blend/proprietary header patterns AND has no dosage
        - Matches blend/proprietary header patterns AND has only total weight
        - proprietaryBlend == true + LOW-CONFIDENCE pattern match (even with dose)

        Override (keep scorable):
        - Exists in quality_map or botanicals_db
        - Has potency markers

        Returns skip_reason string if should skip, None if scorable.
        """
        ing_name = ingredient.get('name', '')
        std_name = ingredient.get('standardName', '') or ing_name
        name_lower = ing_name.lower().strip()
        std_lower = std_name.lower().strip()
        name_norm = self._normalize_exclusion_text(ing_name)
        std_norm = self._normalize_exclusion_text(std_name)
        raw_source = ingredient.get('raw_source_text', '')

        # =================================================================
        # GROUP Z: Unconditional skips — these are NEVER real ingredients.
        # No quality_map / potency override can rescue them.
        # =================================================================

        # Z1: Known label-level blend names should always be treated as headers.
        if name_norm in BLEND_HEADER_EXACT_NAMES or std_norm in BLEND_HEADER_EXACT_NAMES:
            return SKIP_REASON_BLEND_HEADER_WITH_WEIGHT

        # Z2/Z3: Excluded label phrases and nutrition-fact rollups.
        for text in (ing_name, std_name, raw_source, name_lower, std_lower):
            exclusion_reason = self._excluded_text_reason(text)
            if exclusion_reason:
                return exclusion_reason

        # =================================================================
        # OVERRIDE CHECK: If known in quality map or botanicals, always score
        # =================================================================
        if self._is_known_therapeutic(ing_name, std_name, quality_map, botanicals_db):
            return None

        # Deterministic role split: recognized non-scorable identities are skipped.
        # This prevents excipients/label technologies from inflating unmapped actives.
        recognized = self._is_recognized_non_scorable(ing_name, std_name)
        if recognized:
            return SKIP_REASON_RECOGNIZED_NON_SCORABLE

        # OVERRIDE CHECK: If has potency markers in name, always score
        if self._has_potency_markers(ing_name):
            return None

        # =================================================================
        # GROUP A: Structural flags from cleaning
        # =================================================================

        # A1: Check isAdditive flag
        if ingredient.get('isAdditive', False):
            return SKIP_REASON_ADDITIVE

        # A2: Check additiveType
        additive_type = ingredient.get('additiveType', '')
        if additive_type and additive_type.lower() in ADDITIVE_TYPES_SKIP_SCORING:
            return SKIP_REASON_ADDITIVE_TYPE

        # A3: Check nested under non-therapeutic parent
        if ingredient.get('isNestedIngredient', False):
            parent_blend = ingredient.get('parentBlend', '')
            if parent_blend and parent_blend.lower().strip() in NON_THERAPEUTIC_PARENT_DENYLIST:
                return SKIP_REASON_NESTED_NON_THERAPEUTIC
            # Nested rows inside proprietary blends without dose are usually label artifacts.
            has_dose_nested, _ = self._has_valid_therapeutic_dose(ingredient)
            ingredient_group = (ingredient.get('ingredientGroup', '') or '').lower()
            if not has_dose_nested and (
                ingredient.get('proprietaryBlend', False)
                or ('blend' in ingredient_group)
                or bool(parent_blend)
            ):
                return SKIP_REASON_NESTED_NON_THERAPEUTIC

        # =================================================================
        # GROUP B: Blend header pattern matching
        # =================================================================
        has_dose, is_blend_weight = self._has_valid_therapeutic_dose(ingredient)

        # B1: Structured blend headers with nested components should never be scored.
        ingredient_group = (ingredient.get('ingredientGroup', '') or '').lower()
        nested = ingredient.get('nestedIngredients') or []
        if isinstance(nested, list) and nested and ('blend' in ingredient_group):
            return SKIP_REASON_BLEND_HEADER_WITH_WEIGHT if has_dose else SKIP_REASON_BLEND_HEADER_NO_DOSE

        # B2: HIGH-CONFIDENCE patterns: skip regardless of dose
        for pattern in BLEND_HEADER_PATTERNS_HIGH_CONFIDENCE:
            if re.search(pattern, name_lower, re.IGNORECASE):
                if not has_dose:
                    return SKIP_REASON_BLEND_HEADER_NO_DOSE
                else:
                    return SKIP_REASON_BLEND_HEADER_WITH_WEIGHT

        # B3: LOW-CONFIDENCE patterns — skip if no dose
        if not has_dose:
            for pattern in BLEND_HEADER_PATTERNS_LOW_CONFIDENCE:
                if re.search(pattern, name_lower, re.IGNORECASE):
                    return SKIP_REASON_BLEND_HEADER_NO_DOSE

        # B4: LOW-CONFIDENCE patterns WITH dose — skip if structural evidence
        # says this is a blend header carrying total weight, not a real active.
        # Evidence: proprietaryBlend flag, ingredientGroup contains "blend",
        # or hierarchyType indicates summary/header.
        is_structural_blend = (
            ingredient.get('proprietaryBlend', False)
            or ingredient.get('isProprietaryBlend', False)
            or ('blend' in ingredient_group and 'blend' not in name_lower.split()[-1:])
        )
        hierarchy_type = ingredient.get('hierarchyType', '')
        is_header_hierarchy = hierarchy_type in ('summary', 'source', 'blend_header')

        if has_dose and (is_structural_blend or is_header_hierarchy):
            for pattern in BLEND_HEADER_PATTERNS_LOW_CONFIDENCE:
                if re.search(pattern, name_lower, re.IGNORECASE):
                    return SKIP_REASON_BLEND_HEADER_WITH_WEIGHT

        return None

    def _should_promote_to_scorable(self, ingredient: Dict, quality_map: Dict,
                                     botanicals_db: Dict,
                                     current_scorable_count: int) -> Optional[Dict]:
        """
        Determine if an inactive ingredient should be PROMOTED to scorable.

        TWO-FACTOR PROMOTION (prevents excipient backdoors):
        - RULE A: Known therapeutic (single factor - high confidence)
        - RULE B: Has dose AND therapeutic signal (two factors required)
        - RULE C: Absorption enhancer exception (specific allowlist)
        - RULE D: Product-type rescue (very conservative, low confidence)

        Hard exclusions:
        - Label phrases and nutrition facts (never real ingredients)
        - Blend header exact names
        - Common excipients (EXCIPIENT_NEVER_PROMOTE)
        - isAdditive == true

        Returns dict with {reason, confidence} if should promote, None otherwise.
        """
        ing_name = ingredient.get('name', '')
        std_name = ingredient.get('standardName', '') or ing_name
        name_lower = ing_name.lower().strip()
        std_lower = std_name.lower().strip()
        name_norm = self._normalize_exclusion_text(ing_name)
        std_norm = self._normalize_exclusion_text(std_name)
        raw_source = ingredient.get('raw_source_text', '')

        # HARD EXCLUSION: Label phrases, nutrition facts, blend headers
        # These are never real ingredients — block before any promotion rule.
        for text in (ing_name, std_name, raw_source, name_lower, std_lower):
            if self._excluded_text_reason(text):
                return None
        if name_norm in BLEND_HEADER_EXACT_NAMES or std_norm in BLEND_HEADER_EXACT_NAMES:
            return None
        for pattern in BLEND_HEADER_PATTERNS_HIGH_CONFIDENCE:
            if re.search(pattern, name_lower, re.IGNORECASE):
                return None

        # RULE C: Absorption enhancer exception (checked BEFORE hard exclusions)
        # These are therapeutically relevant even without dose
        is_absorption_enhancer = self._is_absorption_enhancer(name_lower, std_lower)
        if is_absorption_enhancer:
            return {
                "reason": PROMOTE_REASON_ABSORPTION_ENHANCER,
                "confidence": "LOW"  # Low confidence because no dose specified
            }

        # HARD EXCLUSION: isAdditive flag
        if ingredient.get('isAdditive', False):
            return None

        # HARD EXCLUSION: Known excipients
        if name_lower in EXCIPIENT_NEVER_PROMOTE:
            return None
        if std_lower in EXCIPIENT_NEVER_PROMOTE:
            return None

        # Check for partial matches in excipient list
        for excipient in EXCIPIENT_NEVER_PROMOTE:
            if excipient in name_lower or excipient in std_lower:
                return None

        # RULE A: Known therapeutic ingredient (single factor - high confidence)
        is_known = self._is_known_therapeutic(
            ing_name, std_name, quality_map, botanicals_db
        )
        if is_known:
            return {
                "reason": PROMOTE_REASON_KNOWN_DB,
                "confidence": "HIGH"
            }

        # RULE B: TWO-FACTOR - Has dose AND therapeutic signal
        # Dose alone is not sufficient (prevents "2g sorbitol" backdoor)
        # Use validated dose check instead of simple truthiness
        has_dose, _ = self._has_valid_therapeutic_dose(ingredient)
        has_high_signal = self._has_high_signal_potency(ing_name)
        has_therapeutic_signal = self._has_therapeutic_signal(ing_name, std_name)

        if has_dose and (has_high_signal or has_therapeutic_signal):
            return {
                "reason": PROMOTE_REASON_HAS_DOSE,
                "confidence": "MEDIUM"
            }

        # High-signal markers alone (without explicit dose) - still decent signal
        if has_high_signal:
            return {
                "reason": PROMOTE_REASON_HAS_DOSE,
                "confidence": "LOW"
            }

        # RULE D: Product-type rescue (only when scorable count is very low)
        # More restrictive: must look like a specific botanical, not just "extract"
        if current_scorable_count <= 1:
            botanical_parts = [
                'root', 'leaf', 'herb', 'flower', 'berry',
                'fruit', 'seed', 'bark', 'rhizome', 'bulb'
            ]
            # Must have a plant part indicator, not just "extract"
            if any(part in name_lower for part in botanical_parts):
                return {
                    "reason": PROMOTE_REASON_PRODUCT_TYPE_RESCUE,
                    "confidence": "LOW"
                }

        return None

    def _is_absorption_enhancer(self, name_lower: str, std_lower: str) -> bool:
        """
        Check if ingredient is a known absorption enhancer.

        These are therapeutically relevant for bioavailability and
        should be promoted even without explicit dose.
        """
        # Check exact matches
        if name_lower in ABSORPTION_ENHANCERS_PROMOTE_EXCEPTION:
            return True
        if std_lower in ABSORPTION_ENHANCERS_PROMOTE_EXCEPTION:
            return True

        # Check partial matches for common absorption enhancers
        # (e.g., "BioPerine® black pepper extract" should match "black pepper extract")
        for enhancer in ABSORPTION_ENHANCERS_PROMOTE_EXCEPTION:
            # Only check if enhancer is a multi-word term (avoid false positives)
            if ' ' in enhancer:
                if enhancer in name_lower or enhancer in std_lower:
                    return True

        # Check for specific branded absorption enhancers
        branded_enhancers = ['bioperine', 'piperine']
        for brand in branded_enhancers:
            if brand in name_lower or brand in std_lower:
                return True

        return False

    def _has_therapeutic_signal(self, ing_name: str, std_name: str) -> bool:
        """
        Check if ingredient has signals indicating it's therapeutic, not excipient.
        Used as second factor for promotion decisions.
        """
        text = f"{ing_name} {std_name}".lower()

        # Botanical/therapeutic indicators (excluding bare "extract")
        therapeutic_patterns = [
            r'\b(vitamin|mineral|amino\s*acid|probiotic|enzyme)\b',
            r'\b(root|leaf|herb|flower|berry|fruit|seed|bark)\b',
            r'\b(powder|capsule|tablet)\s+(of|from)\b',
            r'\b(standardized|concentrated)\b',
            r'\b\d+:\d+\b',  # Extract ratios
        ]

        for pattern in therapeutic_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def _is_known_therapeutic(self, ing_name: str, std_name: str,
                               quality_map: Dict, botanicals_db: Dict) -> bool:
        """Check if ingredient exists in therapeutic databases."""
        # Check quality map
        quality_match = self._match_quality_map(ing_name, std_name, quality_map)
        if quality_match and quality_match.get("match_status") != "FORM_UNMAPPED":
            return True

        # Check botanicals database
        # IMPORTANT: Normalize BOTH input and DB values consistently
        # to handle trademarks, whitespace, etc.
        ing_norm = self._normalize_text(ing_name)
        std_norm = self._normalize_text(std_name)

        botanicals_list = None
        if isinstance(botanicals_db, dict):
            botanicals_list = botanicals_db.get('standardized_botanicals')

        if isinstance(botanicals_list, list):
            for data in botanicals_list:
                if not isinstance(data, dict):
                    continue
                # Normalize DB values the same way as input
                bot_name = self._normalize_text(data.get('standard_name', ''))
                aliases = [self._normalize_text(a) for a in data.get('aliases', [])]

                if ing_norm == bot_name or std_norm == bot_name:
                    return True
                if ing_norm in aliases or std_norm in aliases:
                    return True
            return False

        # Fallback: iterate dict directly (legacy DB format)
        if isinstance(botanicals_db, dict):
            for key, data in botanicals_db.items():
                if key.startswith("_") or not isinstance(data, dict):
                    continue

                bot_name = self._normalize_text(data.get('standard_name', key))
                aliases = [self._normalize_text(a) for a in data.get('aliases', [])]

                if ing_norm == bot_name or std_norm == bot_name:
                    return True
                if ing_norm in aliases or std_norm in aliases:
                    return True

        return False

    def _is_recognized_non_scorable(self, ing_name: str, std_name: str) -> Optional[Dict]:
        """
        Check if ingredient is recognized in non-scorable databases.

        TIERED MATCHING (per dev feedback):
        - Tier 1: quality_map → scorable bioactive
        - Tier 2: botanicals → recognized (scorable if modeled)
        - Tier 3: other_ingredients → recognized_non_scorable (THIS METHOD)
        - Tier 4: excipient_list → recognized_non_scorable
        - Tier 5: unmatched

        This prevents oils, food powders, and carriers from counting as
        "unmapped ingredients" and inflating the unmapped count.

        Returns:
            Dict with recognition_source and reason if recognized, None otherwise.
        """
        def _variants(value: str) -> List[str]:
            base = self._normalize_text(value)
            pre = norm_module.preprocess_text(value)
            variants = {base, self._normalize_text(pre)}
            # Strip percentage + "whole" prefix commonly found in fruit extracts.
            variants.add(re.sub(r'^\d+(?:\.\d+)?%\s*whole\s+', '', base).strip())
            variants.add(re.sub(r'^\d+(?:\.\d+)?%\s*whole\s+', '', self._normalize_text(pre)).strip())
            # Strip benign qualifiers for identity-only recognition.
            variants.add(re.sub(r'^(?:organic|natural|raw|pure)\s+', '', base).strip())
            variants.add(re.sub(r'^(?:organic|natural|raw|pure)\s+', '', self._normalize_text(pre)).strip())
            # Strip common processing qualifiers that should not block identity matching.
            for v in list(variants):
                stripped = re.sub(
                    r'\b(cold[-\s]?pressed|extra virgin|unrefined|certified organic|virgin)\b',
                    '',
                    v,
                    flags=re.IGNORECASE
                ).strip()
                variants.add(re.sub(r'\s+', ' ', stripped).strip())
            # Reorder comma suffix qualifiers: "pumpkin seed oil, cold-pressed" -> "cold-pressed pumpkin seed oil"
            for v in list(variants):
                if ',' not in v:
                    continue
                parts = [p.strip() for p in v.split(',') if p and p.strip()]
                if len(parts) >= 2:
                    variants.add(' '.join(parts[1:] + parts[:1]))
            # Strip common botanical plant-part suffixes for identity-only recognition.
            for v in list(variants):
                variants.add(re.sub(r'\b(root|leaf|fruit|seed|flower|bark)\b', '', v).strip())
            return [v for v in variants if v]

        candidates = set(_variants(ing_name) + _variants(std_name))

        # Check other_ingredients.json
        other_db = self.databases.get('other_ingredients', {})
        other_list = other_db.get('other_ingredients', []) if isinstance(other_db, dict) else []

        for entry in other_list:
            if not isinstance(entry, dict):
                continue
            entry_name = self._normalize_text(entry.get('standard_name', ''))
            entry_aliases = [self._normalize_text(a) for a in entry.get('aliases', [])]
            entry_variants = set(_variants(entry.get('standard_name', '')))
            for alias in entry.get('aliases', []):
                entry_variants.update(_variants(alias))

            if entry_name in candidates or any(v in candidates for v in entry_variants):
                return {
                    "recognition_source": "other_ingredients",
                    "recognition_reason": entry.get('category', 'other_ingredient'),
                    "matched_entry_id": entry.get('id'),
                    "matched_entry_name": entry.get('standard_name'),
                    "recognition_type": "non_scorable",
                }

        # Check harmful_additives DB for known additive identities.
        harmful_db = self.databases.get('harmful_additives', {})
        harmful_list = harmful_db.get('harmful_additives', []) if isinstance(harmful_db, dict) else []
        for entry in harmful_list:
            if not isinstance(entry, dict):
                continue
            entry_variants = set(_variants(entry.get('standard_name', '')))
            for alias in entry.get('aliases', []):
                entry_variants.update(_variants(alias))
            if any(v in candidates for v in entry_variants):
                return {
                    "recognition_source": "harmful_additives",
                    "recognition_reason": entry.get('severity_level', 'known_additive'),
                    "matched_entry_id": entry.get('id'),
                    "matched_entry_name": entry.get('standard_name'),
                    "recognition_type": "non_scorable",
                }

        # Check botanical identity DB (recognized identity, but not quality-scored yet).
        botanical_db = self.databases.get('botanical_ingredients', {})
        botanical_list = botanical_db.get('botanical_ingredients', []) if isinstance(botanical_db, dict) else []
        for entry in botanical_list:
            if not isinstance(entry, dict):
                continue
            entry_variants = set(_variants(entry.get('standard_name', '')))
            for alias in entry.get('aliases', []):
                entry_variants.update(_variants(alias))
            if any(v in candidates for v in entry_variants):
                return {
                    "recognition_source": "botanical_ingredients",
                    "recognition_reason": entry.get('category', 'botanical'),
                    "matched_entry_id": entry.get('id'),
                    "matched_entry_name": entry.get('standard_name'),
                    "recognition_type": "botanical_unscored",
                }

        # Check standardized_botanicals DB as identity-only fallback.
        standardized_db = self.databases.get('standardized_botanicals', {})
        standardized_list = standardized_db.get('standardized_botanicals', []) if isinstance(standardized_db, dict) else []
        for entry in standardized_list:
            if not isinstance(entry, dict):
                continue
            entry_variants = set(_variants(entry.get('standard_name', '')))
            for alias in entry.get('aliases', []):
                entry_variants.update(_variants(alias))
            if any(v in candidates for v in entry_variants):
                return {
                    "recognition_source": "standardized_botanicals",
                    "recognition_reason": "botanical_identity",
                    "matched_entry_id": entry.get('id'),
                    "matched_entry_name": entry.get('standard_name'),
                    "recognition_type": "botanical_unscored",
                }

        # Check banned_recalled_ingredients DB for identity-only recognition.
        # Prevents banned items from inflating the unmapped count.
        banned_db = self.databases.get('banned_recalled_ingredients', {})
        banned_list = banned_db.get('ingredients', []) if isinstance(banned_db, dict) else []
        for entry in banned_list:
            if not isinstance(entry, dict):
                continue
            # Skip non-matchable entity types (products, classes, threats)
            entity_type = entry.get('entity_type', 'ingredient')
            if entity_type not in {'ingredient', 'contaminant', None, ''}:
                continue
            entry_variants = set(_variants(entry.get('standard_name', '')))
            for alias in entry.get('aliases', []):
                entry_variants.update(_variants(alias))
            if any(v in candidates for v in entry_variants):
                return {
                    "recognition_source": "banned_recalled_ingredients",
                    "recognition_reason": entry.get('severity_level', 'banned'),
                    "matched_entry_id": entry.get('id'),
                    "matched_entry_name": entry.get('standard_name'),
                    "recognition_type": "non_scorable",
                }

        # Check against EXCIPIENT_NEVER_PROMOTE constant list
        # These are explicitly known non-therapeutic ingredients
        name_lower = ing_name.lower().strip()
        std_lower = std_name.lower().strip()

        if name_lower in EXCIPIENT_NEVER_PROMOTE or std_lower in EXCIPIENT_NEVER_PROMOTE:
            return {
                "recognition_source": "excipient_list",
                "recognition_reason": "known_excipient",
                "matched_entry_id": None,
                "matched_entry_name": name_lower if name_lower in EXCIPIENT_NEVER_PROMOTE else std_lower,
                "recognition_type": "non_scorable",
            }

        # Check for partial matches (e.g., "organic sunflower oil" matches "sunflower oil")
        for excipient in EXCIPIENT_NEVER_PROMOTE:
            if excipient in name_lower or excipient in std_lower:
                return {
                    "recognition_source": "excipient_list",
                    "recognition_reason": "known_excipient_partial",
                    "matched_entry_id": None,
                    "matched_entry_name": excipient,
                    "recognition_type": "non_scorable",
                }

        return None

    def _has_high_signal_potency(self, text: str) -> bool:
        """
        Check if text contains HIGH-SIGNAL potency markers.
        These are strong indicators of therapeutic ingredients.
        """
        text_lower = text.lower()
        for pattern in POTENCY_MARKERS_HIGH_SIGNAL:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False

    def _has_potency_markers(self, text: str) -> bool:
        """
        Check if text contains any potency/dose markers (high or low signal).
        Used for skip override decisions in Pass 1.
        """
        # High-signal markers are always valid
        if self._has_high_signal_potency(text):
            return True

        # Low-signal markers only count with additional context
        # (handled by caller with _has_therapeutic_signal)
        return False

    def _build_quality_entry(self, ingredient: Dict, match_result: Optional[Dict],
                              hierarchy_type: Optional[str], source_section: str = "active",
                              promotion_reason: str = None, promotion_confidence: str = None,
                              dose_present: bool = None) -> Dict:
        """Build a quality data entry for an ingredient.

        LABEL NAME PRESERVATION:
        - raw_source_text: Exact label text (provenance)
        - name: User-facing label name (may be slightly cleaned)
        - standard_name: Canonical name from database (internal matching)
        """
        ing_name = ingredient.get('name', '')
        std_name = ingredient.get('standardName', '') or ing_name
        # LABEL NAME PRESERVATION: Track exact label text for audit
        raw_source_text = ingredient.get('raw_source_text') or ing_name
        quantity = ingredient.get('quantity', 0)
        unit = ingredient.get('unit', '')
        has_dose, _ = self._has_valid_therapeutic_dose(ingredient)
        unit_normalized = self._normalize_unit_for_signal(unit)
        is_excipient, never_promote_reason = self._compute_excipient_flags(ingredient)
        blend_flags = self._compute_blend_flags(ingredient, None)
        is_form_unmapped = bool(
            match_result and isinstance(match_result, dict) and match_result.get("match_status") == "FORM_UNMAPPED"
        )

        if is_form_unmapped:
            entry = {
                "name": ing_name,
                "raw_source_text": raw_source_text,
                "standard_name": match_result.get("base_name", std_name),
                "matched_form": None,
                "canonical_id": None,
                "form_id": None,
                "match_tier": None,
                "matched_alias": None,
                "matched_target": None,
                "match_ambiguity_candidates": [],
                "bio_score": None,
                "natural": None,
                "score": 9,
                "absorption": None,
                "notes": None,
                "dosage_importance": 1.0,
                "category": ingredient.get('category', 'unknown'),
                "quantity": quantity,
                "unit": unit,
                "unit_normalized": unit_normalized,
                "has_dose": has_dose,
                "is_blend_header": blend_flags["is_blend_header"],
                "is_proprietary_blend": blend_flags["is_proprietary_blend"],
                "blend_total_weight_only": blend_flags["blend_total_weight_only"],
                "blend_disclosed_components_count": blend_flags["blend_disclosed_components_count"],
                "is_excipient": is_excipient,
                "never_promote_reason": never_promote_reason,
                "certificates": [],
                "mapped": False,
                "mapped_identity": False,
                "scoreable_identity": False,
                "role_classification": "active_unmapped",
                "identity_confidence": 0.0,
                "identity_decision_reason": "form_unmapped",
                "hierarchyType": hierarchy_type,
                "source_section": source_section,
                "form_extraction_used": True,
                "is_dual_form": bool(match_result.get("is_dual_form")),
                "original_label": match_result.get("original_label"),
                "extracted_forms": match_result.get("extracted_forms", []),
                "matched_forms": [],
                "unmapped_forms": match_result.get("unmapped_forms", []),
                "aggregation_method": None,
                "final_form_bio_score": None,
                "additional_forms": [],
                "form_source": match_result.get("form_source"),
            }
        elif match_result:
            bio_score = match_result.get('bio_score', 5)
            natural = match_result.get('natural', False)
            score = match_result.get('score', bio_score + (3 if natural else 0))
            used_form_fallback = match_result.get('match_status') == 'FORM_UNMAPPED_FALLBACK'

            entry = {
                # LABEL NAME PRESERVATION:
                "name": ing_name,  # Label-facing name (user-visible)
                "raw_source_text": raw_source_text,  # Exact label text (provenance)
                "standard_name": match_result.get('standard_name', std_name),  # Canonical
                "matched_form": match_result.get('form_name', 'standard'),
                "canonical_id": match_result.get('canonical_id'),
                "form_id": match_result.get('form_id'),
                "match_tier": match_result.get('match_tier'),
                "matched_alias": match_result.get('matched_alias'),
                "matched_target": match_result.get('matched_target'),
                "match_ambiguity_candidates": match_result.get('match_ambiguity_candidates', []),
                "bio_score": bio_score,
                "natural": natural,
                "score": score,
                "absorption": match_result.get('absorption'),
                "notes": match_result.get('notes'),
                "dosage_importance": match_result.get('dosage_importance', 1.0),
                "category": match_result.get('category', 'other'),
                "quantity": quantity,
                "unit": unit,
                "unit_normalized": unit_normalized,
                "has_dose": has_dose,
                "is_blend_header": blend_flags["is_blend_header"],
                "is_proprietary_blend": blend_flags["is_proprietary_blend"],
                "blend_total_weight_only": blend_flags["blend_total_weight_only"],
                "blend_disclosed_components_count": blend_flags["blend_disclosed_components_count"],
                "is_excipient": is_excipient,
                "never_promote_reason": never_promote_reason,
                "certificates": [],
                "mapped": True,
                "mapped_identity": True,
                "scoreable_identity": True,
                "role_classification": "active_scorable",
                "identity_confidence": 0.8 if used_form_fallback else (1.0 if match_result.get('match_tier') == "exact" else 0.9),
                "identity_decision_reason": "form_unmapped_fallback" if used_form_fallback else "quality_map_match",
                "hierarchyType": hierarchy_type,
                "source_section": source_section,
                # Multi-form contract fields (if present)
                "form_extraction_used": match_result.get('form_extraction_used', False),
                "is_dual_form": match_result.get('is_dual_form', False),
                "original_label": match_result.get('original_label'),
                "extracted_forms": match_result.get('extracted_forms', []),
                "matched_forms": match_result.get('matched_forms', []),
                "unmapped_forms": match_result.get('unmapped_forms', []),
                "aggregation_method": match_result.get('aggregation_method'),
                "final_form_bio_score": match_result.get('final_form_bio_score'),
                "additional_forms": match_result.get('additional_forms', []),
                "form_source": match_result.get('form_source'),
                "form_unmapped": bool(used_form_fallback),
            }
        else:
            entry = {
                # LABEL NAME PRESERVATION:
                "name": ing_name,  # Label-facing name (user-visible)
                "raw_source_text": raw_source_text,  # Exact label text (provenance)
                "standard_name": std_name,  # No canonical match
                "matched_form": None,
                "canonical_id": None,
                "form_id": None,
                "match_tier": None,
                "matched_alias": None,
                "matched_target": None,
                "match_ambiguity_candidates": [],
                "bio_score": None,
                "natural": None,
                "score": 9,  # Neutral midpoint fallback for unmapped
                "absorption": None,
                "notes": None,
                "dosage_importance": 1.0,
                "category": ingredient.get('category', 'unknown'),
                "quantity": quantity,
                "unit": unit,
                "unit_normalized": unit_normalized,
                "has_dose": has_dose,
                "is_blend_header": blend_flags["is_blend_header"],
                "is_proprietary_blend": blend_flags["is_proprietary_blend"],
                "blend_total_weight_only": blend_flags["blend_total_weight_only"],
                "blend_disclosed_components_count": blend_flags["blend_disclosed_components_count"],
                "is_excipient": is_excipient,
                "never_promote_reason": never_promote_reason,
                "certificates": [],
                "mapped": False,
                "mapped_identity": False,
                "scoreable_identity": False,
                "role_classification": "active_unmapped",
                "identity_confidence": 0.0,
                "identity_decision_reason": "no_quality_map_match",
                "hierarchyType": hierarchy_type,
                "source_section": source_section
            }

        # Add promotion metadata if applicable
        if promotion_reason:
            entry["promotion_reason"] = promotion_reason
            entry["promotion_confidence"] = promotion_confidence
            entry["dose_present"] = dose_present

        return entry

    def _match_multi_form(self, form_info: Dict, quality_map: Dict) -> Optional[Dict]:
        """
        Match multiple extracted forms and aggregate scores using weighted average.

        Multi-Form Contract:
        - extracted_forms: list of form info dicts from extraction
        - matched_forms: list of {form_key, bio_score, natural, match_method, percent_share}
        - unmapped_forms: list of raw strings that failed to match
        - aggregation_method: 'weighted' | 'equal' | 'single'
        - final_form_bio_score: numeric (0-15) - the aggregated score

        Returns None if no forms match successfully.
        """
        extracted_forms = form_info.get('extracted_forms', [])
        if not extracted_forms:
            return None

        matched_forms = []
        unmapped_forms = []
        generic_form_tokens = []

        for form_data in extracted_forms:
            match_candidates = form_data.get('match_candidates', [])
            percent_share = form_data.get('percent_share', 1.0 / len(extracted_forms))
            raw_form_text = form_data.get('raw_form_text', '')

            # Try each match candidate until one succeeds
            form_match = None
            matched_candidate = None
            matched_unspecified = False
            for candidate in match_candidates:
                form_match = self._match_quality_map(
                    candidate, candidate, quality_map, _form_extraction_attempt=True
                )
                if form_match:
                    form_id = form_match.get('form_id', '')
                    # Accept if it's a specific form (not unspecified)
                    if form_id and 'unspecified' not in form_id.lower():
                        matched_candidate = candidate
                        break
                    else:
                        # Generic/source descriptors frequently resolve to
                        # unspecified forms (e.g., "fish oil" for DHA/EPA).
                        # Track these separately to avoid false form-loss flags.
                        matched_unspecified = True
                        form_match = None

            if form_match and matched_candidate:
                bio_score = form_match.get('bio_score', 5)
                natural = form_match.get('natural', False)
                # Use pre-computed score from database, fall back to calculation only if missing
                score = form_match.get('score', bio_score + (3 if natural else 0))
                matched_forms.append({
                    'form_key': form_match.get('form_id'),
                    'canonical_id': form_match.get('canonical_id'),
                    'bio_score': bio_score,
                    'natural': natural,
                    'score': score,  # Pre-computed from database
                    'match_method': form_match.get('match_tier', 'unknown'),
                    'matched_candidate': matched_candidate,
                    'percent_share': percent_share,
                    'raw_form_text': raw_form_text,
                    'full_match_data': form_match
                })
            else:
                if matched_unspecified:
                    generic_form_tokens.append(raw_form_text)
                else:
                    unmapped_forms.append(raw_form_text)
                    # Track unmapped form for database expansion
                    base_name = form_info.get('base_name', '')
                    original_label = form_info.get('original', '')
                    if raw_form_text:
                        self._track_unmapped_form(raw_form_text, base_name, original_label)

        # If no forms matched, return None (let caller handle FORM_UNMAPPED)
        if not matched_forms:
            if generic_form_tokens and not unmapped_forms:
                # All form tokens were generic/source descriptors that only
                # resolved to unspecified forms; treat as no actionable form
                # evidence and continue with parent matching.
                return {
                    'all_forms_generic': True,
                    'generic_form_tokens': generic_form_tokens,
                    'unmapped_forms': [],
                    'form_extraction_used': True,
                }
            return None

        # Determine aggregation method
        if len(matched_forms) == 1:
            aggregation_method = 'single'
        elif any(f.get('percent_share') != matched_forms[0].get('percent_share') for f in matched_forms):
            aggregation_method = 'weighted'
        else:
            aggregation_method = 'equal'

        # Calculate weighted average of bio_score and score
        total_weight = sum(f['percent_share'] for f in matched_forms)
        if total_weight > 0:
            final_bio_score = sum(
                f['bio_score'] * f['percent_share'] for f in matched_forms
            ) / total_weight
            # Use pre-computed score from database (weighted average)
            final_score = sum(
                f['score'] * f['percent_share'] for f in matched_forms
            ) / total_weight
        else:
            final_bio_score = sum(f['bio_score'] for f in matched_forms) / len(matched_forms)
            final_score = sum(f['score'] for f in matched_forms) / len(matched_forms)

        # Round to 1 decimal place for consistency
        final_bio_score = round(final_bio_score, 1)
        final_score = round(final_score, 1)

        # Use primary form (first matched) as the base for canonical fields
        primary_match = matched_forms[0]['full_match_data']

        # Build result with multi-form contract
        result = {
            # Standard match fields (from primary)
            'canonical_id': primary_match.get('canonical_id'),
            'form_id': primary_match.get('form_id'),
            'standard_name': primary_match.get('standard_name'),
            'form_name': primary_match.get('form_name'),
            'category': primary_match.get('category'),
            'absorption': primary_match.get('absorption'),
            'notes': primary_match.get('notes'),
            'dosage_importance': primary_match.get('dosage_importance', 1.0),
            'match_tier': primary_match.get('match_tier'),
            'matched_alias': primary_match.get('matched_alias'),
            'matched_target': primary_match.get('matched_target'),

            # Aggregated scores (using pre-computed scores from database)
            'bio_score': final_bio_score,
            'natural': any(f['natural'] for f in matched_forms),  # Natural if any form is natural
            'score': final_score,  # Pre-computed weighted average from database scores

            # Multi-form contract fields
            'form_extraction_used': True,
            'original_label': form_info.get('original'),
            'is_dual_form': form_info.get('is_dual_form', False),
            'extracted_forms': form_info.get('extracted_forms', []),
            'matched_forms': [
                {
                    'form_key': f['form_key'],
                    'canonical_id': f['canonical_id'],
                    'bio_score': f['bio_score'],
                    'natural': f['natural'],
                    'score': f['score'],  # Pre-computed from database
                    'match_method': f['match_method'],
                    'percent_share': f['percent_share'],
                    'raw_form_text': f['raw_form_text'],
                    'matched_candidate': f['matched_candidate']
                }
                for f in matched_forms
            ],
            'unmapped_forms': unmapped_forms,
            'aggregation_method': aggregation_method,
            'final_form_bio_score': final_bio_score,

            # Additional forms beyond primary (for transparency)
            'additional_forms': [
                {
                    'form_key': f['form_key'],
                    'bio_score': f['bio_score'],
                    'score': f['score'],  # Pre-computed from database
                    'percent_share': f['percent_share']
                }
                for f in matched_forms[1:]
            ] if len(matched_forms) > 1 else []
        }

        return result

    def _build_form_info_from_cleaned(self, ing_name: str, cleaned_forms: List[Dict]) -> Optional[Dict]:
        """
        Build a form_info dict from the cleaning stage's structured forms[] array.

        This bridges the gap between the cleaning stage (which parses
        "Vitamin A (as Retinyl Palmitate)" into forms[]) and the enricher's
        _match_multi_form() which expects a form_info dict.

        Args:
            ing_name: The ingredient name (e.g., "Vitamin A")
            cleaned_forms: List of form dicts from cleaning, e.g.:
                [{"name": "Retinyl Palmitate", "percent": null, "order": 1}]

        Returns:
            form_info dict compatible with _match_multi_form(), or None if
            cleaned_forms has no usable entries.
        """
        if not cleaned_forms:
            return None

        extracted_forms = []
        for form in cleaned_forms:
            form_name = form.get('name', '')
            if not form_name or not form_name.strip():
                continue

            # Build match candidates: the form name itself + common variations
            match_candidates = [form_name]
            # Also try lowercase and stripped version
            stripped = form_name.strip()
            if stripped != form_name:
                match_candidates.append(stripped)
            # Normalize wrapper punctuation often emitted by cleaning.
            unwrapped = re.sub(r'[\{\}\[\]]', '', stripped)
            unwrapped = re.sub(r'\(([^)]+)\)', r'\1', unwrapped)
            unwrapped = re.sub(r'\s+', ' ', unwrapped).strip()
            if unwrapped and unwrapped not in match_candidates:
                match_candidates.append(unwrapped)

            # Convert percent field: cleaning uses None or a float (0-100)
            percent_raw = form.get('percent')
            percent_share = None
            if percent_raw is not None:
                try:
                    percent_share = float(percent_raw) / 100.0
                except (TypeError, ValueError):
                    pass

            extracted_forms.append({
                'raw_form_text': form_name,
                'match_candidates': match_candidates,
                'display_form': form_name,
                'percent_share': percent_share,
            })

        if not extracted_forms:
            return None

        # Compute equal shares for forms without explicit percentages
        forms_without_pct = [f for f in extracted_forms if f['percent_share'] is None]
        forms_with_pct = [f for f in extracted_forms if f['percent_share'] is not None]
        total_explicit = sum(f['percent_share'] for f in forms_with_pct)
        remaining = max(0.0, 1.0 - total_explicit)

        if forms_without_pct:
            equal_share = remaining / len(forms_without_pct)
            for f in forms_without_pct:
                f['percent_share'] = equal_share

        return {
            'original': ing_name,
            'base_name': ing_name,
            'extracted_forms': extracted_forms,
            'is_dual_form': len(extracted_forms) > 1,
            'form_extraction_success': True,
            'has_form_evidence': True,
        }

    def _match_quality_map(self, ing_name: str, std_name: str, quality_map: Dict,
                           _form_extraction_attempt: bool = False,
                           cleaned_forms: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        Match ingredient against quality map using explicit precedence rules.

        Precedence (highest to lowest):
        1. Form-level exact match (name/alias)
        2. Parent-level exact match (name/alias)
        3. Form-level normalized match
        4. Parent-level normalized match
        5. Form-level pattern/contains match (if present in DB)
        6. Parent-level pattern/contains match (if present in DB)

        Tie-breakers (within same tier):
        1. Longest matched alias wins
        2. Form-level outranks parent-level (if applicable)
        3. Canonical key alphabetical
        4. Form key alphabetical

        Multi-Form Enhancement:
        - Uses pre-parsed cleaned_forms[] from cleaning stage when available
        - Falls back to label text extraction via _extract_form_from_label()
        - For dual-form ingredients, matches ALL forms and uses weighted average
        - Preserves bracket tokens as match candidates
        - If form evidence exists but mapping fails, marks as FORM_UNMAPPED (not unspecified)

        Args:
            ing_name: Ingredient name from label
            std_name: Standardized name
            quality_map: Quality map database
            _form_extraction_attempt: Internal flag to prevent recursion
            cleaned_forms: Pre-parsed forms[] from cleaning stage, e.g.
                           [{"name": "Retinyl Palmitate", "percent": None, ...}]

        Logs structured warnings when multiple candidates exist in the winning tier.
        """
        # MULTI-FORM MATCHING: Try structured cleaned_forms first, then fall back
        # to label text extraction. This fixes the "form loss" issue where cleaning
        # already parsed "Vitamin A (as Retinyl Palmitate)" into forms[] but the
        # enricher was only seeing "Vitamin A".
        if not _form_extraction_attempt:
            # PRIORITY 1: Use cleaned_forms[] from cleaning stage (structured, reliable)
            if cleaned_forms and isinstance(cleaned_forms, list) and len(cleaned_forms) > 0:
                form_info = self._build_form_info_from_cleaned(ing_name, cleaned_forms)
                if form_info and form_info.get('form_extraction_success'):
                    multi_form_result = self._match_multi_form(form_info, quality_map)
                    if multi_form_result:
                        if not multi_form_result.get('all_forms_generic'):
                            return multi_form_result

                    # If form evidence exists but ALL forms failed to match
                    if form_info.get('has_form_evidence') and not (
                        multi_form_result and multi_form_result.get('all_forms_generic')
                    ):
                        # Safe fallback: try parent/base matching so product can still score
                        # conservatively while preserving form-unmapped telemetry.
                        fallback_base = form_info.get('base_name') or ing_name
                        fallback_match = self._match_quality_map(
                            fallback_base, std_name, quality_map, _form_extraction_attempt=True
                        )
                        if fallback_match:
                            fallback = dict(fallback_match)
                            fallback['match_status'] = 'FORM_UNMAPPED_FALLBACK'
                            fallback['has_form_evidence'] = True
                            fallback['original_label'] = ing_name
                            fallback['extracted_forms'] = form_info['extracted_forms']
                            fallback['unmapped_forms'] = [f['raw_form_text'] for f in form_info['extracted_forms']]
                            fallback['base_name'] = form_info['base_name']
                            fallback['form_source'] = 'cleaned_forms'
                            fallback['form_extraction_used'] = True
                            return fallback
                        return {
                            'match_status': 'FORM_UNMAPPED',
                            'has_form_evidence': True,
                            'original_label': ing_name,
                            'extracted_forms': form_info['extracted_forms'],
                            'unmapped_forms': [f['raw_form_text'] for f in form_info['extracted_forms']],
                            'base_name': form_info['base_name'],
                            'form_source': 'cleaned_forms',
                        }

            # PRIORITY 2: Fall back to label text extraction (for labels with "(as ...)")
            form_info = self._extract_form_from_label(ing_name)
            if form_info['form_extraction_success']:
                multi_form_result = self._match_multi_form(form_info, quality_map)
                if multi_form_result:
                    if not multi_form_result.get('all_forms_generic'):
                        return multi_form_result

                # If form evidence exists but ALL forms failed to match, mark as FORM_UNMAPPED
                if form_info['has_form_evidence'] and not (
                    multi_form_result and multi_form_result.get('all_forms_generic')
                ):
                    fallback_base = form_info.get('base_name') or ing_name
                    fallback_match = self._match_quality_map(
                        fallback_base, std_name, quality_map, _form_extraction_attempt=True
                    )
                    if fallback_match:
                        fallback = dict(fallback_match)
                        fallback['match_status'] = 'FORM_UNMAPPED_FALLBACK'
                        fallback['has_form_evidence'] = True
                        fallback['original_label'] = ing_name
                        fallback['extracted_forms'] = form_info['extracted_forms']
                        fallback['unmapped_forms'] = [f['raw_form_text'] for f in form_info['extracted_forms']]
                        fallback['base_name'] = form_info['base_name']
                        fallback['form_source'] = 'label_extraction'
                        fallback['form_extraction_used'] = True
                        return fallback
                    return {
                        'match_status': 'FORM_UNMAPPED',
                        'has_form_evidence': True,
                        'original_label': ing_name,
                        'extracted_forms': form_info['extracted_forms'],
                        'unmapped_forms': [f['raw_form_text'] for f in form_info['extracted_forms']],
                        'base_name': form_info['base_name'],
                        'form_source': 'label_extraction',
                    }

        ing_exact = self._normalize_exact_text(ing_name)
        std_exact = self._normalize_exact_text(std_name)
        ing_norm = self._normalize_text(ing_name)
        std_norm = self._normalize_text(std_name)

        # Also try base name without parenthetical content or trailing dosages for matching
        # This handles labels like:
        # - "Vitamin K1 (Phylloquinone)" where form extraction doesn't trigger (no "as" keyword)
        # - "Beta-Glucan 250mg" where there's a trailing dosage
        base_name = None
        if not _form_extraction_attempt:
            form_info = self._extract_form_from_label(ing_name)
            base_name = form_info.get('base_name')

            # Also strip trailing dosage/percentage patterns if base_name still has them
            # Patterns like "250mg", "500 mg", "1000mcg", "5g", "98%", "10 Billion CFU", etc.
            if base_name:
                # First strip dosage with units
                stripped = re.sub(
                    r'\s+\d+(?:\.\d+)?\s*(?:mg|mcg|ug|µg|g|kg|ml|l|iu|billion|million|cfu)\s*$',
                    '', base_name, flags=re.IGNORECASE
                ).strip()
                # Also strip trailing percentage (e.g., "98%", "80%")
                stripped = re.sub(r'\s+\d+(?:\.\d+)?\s*%\s*$', '', stripped).strip()
                if stripped and stripped != base_name:
                    base_name = stripped

        # If base name is different from full name, include it in matching candidates
        base_exact = self._normalize_exact_text(base_name) if base_name else None
        base_norm = self._normalize_text(base_name) if base_name else None

        candidates = []
        seen = set()

        def _strip_parenthesis_chars(value: str) -> str:
            # Keep parenthetical content but remove bracket characters.
            # Example: "Oregano (Origanum vulgare) (leaf)" -> "Oregano Origanum vulgare leaf"
            return re.sub(r"[()\[\]]", " ", value or "")

        def _comma_reorder(value: str) -> str:
            # Handle qualifier suffixes like "Garlic Bulb Extract, Odorless"
            # so they can match aliases like "Odorless Garlic Bulb Extract".
            text = value or ""
            if "," not in text:
                return text
            parts = [p.strip() for p in text.split(",") if p and p.strip()]
            if len(parts) < 2:
                return text
            return " ".join(parts[1:] + parts[:1])

        def _build_exact_candidates() -> List[Tuple[str, int]]:
            out: Dict[str, int] = {}

            def add(value: Optional[str], source: int):
                if not value:
                    return
                normed = self._normalize_exact_text(value)
                if not normed:
                    return
                if normed not in out or source < out[normed]:
                    out[normed] = source

            add(ing_name, 0)
            add(std_name, 1)
            add(base_name, 2)
            return sorted(out.items(), key=lambda item: item[1])

        def _build_normalized_candidates() -> List[Tuple[str, int]]:
            out: Dict[str, int] = {}

            def add(value: Optional[str], source: int):
                if not value:
                    return
                variants = {value}
                variants.add(_strip_parenthesis_chars(value))
                for v in list(variants):
                    variants.add(_comma_reorder(v))
                for v in variants:
                    normed = self._normalize_text(v)
                    if not normed:
                        continue
                    if normed not in out or source < out[normed]:
                        out[normed] = source

            add(ing_name, 0)
            add(std_name, 1)
            add(base_name, 2)
            return sorted(out.items(), key=lambda item: item[1])

        exact_candidates = _build_exact_candidates()
        normalized_candidates = _build_normalized_candidates()

        def alias_length(match_type: str, alias: str) -> int:
            if match_type == "exact":
                return len(self._normalize_exact_text(alias))
            return len(self._normalize_text(alias))

        def build_form_match_data(
            parent_key: str, parent_data: Dict, form_name: str, form_data: Dict
        ) -> Dict:
            bio_score = form_data.get('bio_score', 5)
            natural = form_data.get('natural', False)
            score = form_data.get('score', bio_score + (3 if natural else 0))
            return {
                "canonical_id": parent_key,
                "form_id": form_name,
                "standard_name": parent_data.get('standard_name', parent_key),
                "form_name": form_name,
                "bio_score": bio_score,
                "natural": natural,
                "score": score,
                "absorption": form_data.get('absorption'),
                "notes": form_data.get('notes'),
                "dosage_importance": form_data.get('dosage_importance', 1.0),
                "category": parent_data.get('category', 'other'),
            }

        def build_parent_match_data(parent_key: str, parent_data: Dict) -> Tuple[Dict, bool, Optional[str]]:
            forms = parent_data.get('forms', {})
            if forms:
                def _norm(value: str) -> str:
                    return str(value or "").strip().lower()

                def _select_conservative_parent_form(forms_dict: Dict) -> Tuple[str, Dict]:
                    """
                    Select a conservative fallback form for parent-level matches.

                    Best-practice policy:
                    1) Prefer explicit unspecified/default forms when actual form is unknown.
                    2) Otherwise choose the lowest-score form to avoid premium over-credit.
                    """
                    preferred_tokens = ("unspecified", "unknown", "generic", "default", "standard")

                    for form_name, form_data in forms_dict.items():
                        normalized = _norm(form_name)
                        if any(token in normalized for token in preferred_tokens):
                            return form_name, form_data

                    def _score_key(item: Tuple[str, Dict]) -> Tuple[float, str]:
                        form_name, form_data = item
                        score = form_data.get("score")
                        bio = form_data.get("bio_score")
                        try:
                            numeric = float(score if score is not None else bio if bio is not None else 5.0)
                        except (TypeError, ValueError):
                            numeric = 5.0
                        return numeric, _norm(form_name)

                    return min(forms_dict.items(), key=_score_key)

                selected_form_name, selected_form = _select_conservative_parent_form(forms)
                return (
                    build_form_match_data(parent_key, parent_data, selected_form_name, selected_form),
                    True,
                    selected_form_name
                )
            return (
                {
                    "canonical_id": parent_key,
                    "form_id": None,
                    "standard_name": parent_data.get('standard_name', parent_key),
                    "form_name": "standard",
                    "bio_score": 5,
                    "natural": False,
                    "score": 5,
                    "absorption": None,
                    "notes": None,
                    "dosage_importance": 1.0,
                    "category": parent_data.get('category', 'other'),
                },
                False,
                None
            )

        def add_candidate(candidate: Dict):
            key = (
                candidate["parent_key"],
                candidate["form_key"],
                candidate["matched_alias"],
                candidate["match_type"],
                candidate["tier"],
            )
            if key in seen:
                return
            seen.add(key)
            candidates.append(candidate)

        def collect_alias_matches(
            candidate_values: List[Tuple[str, int]],
            target_name: str,
            aliases: List[str],
            normalize_fn,
            match_type: str,
            match_scope: str,
        ) -> List[Dict]:
            matches = []

            if target_name:
                target_norm = normalize_fn(target_name)
                if target_norm:
                    source_hits = [source for value, source in candidate_values if value == target_norm]
                    if source_hits:
                        matches.append({
                            "matched_alias": target_name,
                            "matched_on": f"{match_scope}_name",
                            "alias_len": alias_length(match_type, target_name),
                            "match_source": min(source_hits),
                        })
            for alias in aliases:
                alias_norm = normalize_fn(alias)
                if not alias_norm:
                    continue
                source_hits = [source for value, source in candidate_values if value == alias_norm]
                if source_hits:
                    matches.append({
                        "matched_alias": alias,
                        "matched_on": f"{match_scope}_alias",
                        "alias_len": alias_length(match_type, alias),
                        "match_source": min(source_hits),
                    })
            return matches

        def collect_pattern_matches(
            ing_text: str,
            std_text: str,
            ing_norm_text: str,
            std_norm_text: str,
            pattern_aliases: List[str],
            contains_aliases: List[str],
            match_scope: str,
        ) -> List[Dict]:
            matches = []
            if pattern_aliases:
                for pattern in pattern_aliases:
                    try:
                        if re.search(pattern, ing_text, re.I) or re.search(pattern, std_text, re.I):
                            matches.append({
                                "matched_alias": pattern,
                                "matched_on": f"{match_scope}_pattern",
                                "alias_len": alias_length("pattern", pattern),
                            })
                    except re.error:
                        self.logger.warning(f"Invalid regex pattern '{pattern}' in {match_scope} pattern aliases")
            if contains_aliases:
                for phrase in contains_aliases:
                    phrase_norm = self._normalize_text(phrase)
                    if not phrase_norm:
                        continue
                    if phrase_norm in ing_norm_text or phrase_norm in std_norm_text:
                        matches.append({
                            "matched_alias": phrase,
                            "matched_on": f"{match_scope}_contains",
                            "alias_len": alias_length("pattern", phrase),
                        })
            return matches

        for parent_key, parent_data in quality_map.items():
            if parent_key.startswith("_") or not isinstance(parent_data, dict):
                continue

            # Extract match_rules for this parent
            match_rules = parent_data.get('match_rules', {})
            parent_priority = match_rules.get('priority', 1)  # Default to secondary priority
            parent_match_mode = match_rules.get('match_mode', 'alias_and_fuzzy')
            parent_exclusions = match_rules.get('exclusions', [])

            # Check exclusions: skip this parent when the input is ONLY
            # exclusion terms (prevents false positives on bare descriptors
            # without dropping labels that also carry a real identifier)
            if parent_exclusions:
                # MATCHING_PRECEDENCE.md "Exclusion Processing": skip a parent
                # only when the label consists of ONLY exclusion terms
                # ("Natural flavoring" must not match, but "Curcumin Natural"
                # still matches curcumin). Skipping on ANY exclusion hit would
                # drop valid labels like "Turmeric Extract" the moment
                # descriptors such as "extract" are added to exclusions[].
                input_text_lower = f"{ing_name} {std_name}".lower()
                remaining_text = input_text_lower
                for exclusion in parent_exclusions:
                    excl_lower = exclusion.lower()
                    # Token-bounded removal: word boundary match
                    remaining_text = re.sub(
                        r'\b' + re.escape(excl_lower) + r'\b', ' ', remaining_text
                    )
                has_meaningful_identifier = any(
                    re.search(r'[a-z]', token)
                    for token in re.split(r'[^a-z0-9]+', remaining_text)
                    if token
                )
                if parent_exclusions and not has_meaningful_identifier:
                    continue  # Label is only exclusion terms - skip this parent

            # match_mode gates which tiers are allowed
            # exact: only tier 1,2 (exact matches)
            # normalized: tier 1,2,3,4 (exact + normalized)
            # alias_and_fuzzy: all tiers (exact + normalized + contains/pattern)
            allowed_tiers = {1, 2, 3, 4, 5, 6}  # Default: all
            if parent_match_mode == 'exact':
                allowed_tiers = {1, 2}
            elif parent_match_mode == 'normalized':
                allowed_tiers = {1, 2, 3, 4}
            # alias_and_fuzzy allows all tiers (default)

            forms = parent_data.get('forms', {})
            parent_std_name = parent_data.get('standard_name', parent_key)
            parent_aliases = parent_data.get('aliases', [])
            parent_pattern_aliases = parent_data.get('pattern_aliases', [])
            parent_contains_aliases = parent_data.get('contains_aliases', [])

            # Form-level matches
            for form_name, form_data in forms.items():
                form_aliases = form_data.get('aliases', [])
                form_pattern_aliases = form_data.get('pattern_aliases', [])
                form_contains_aliases = form_data.get('contains_aliases', [])

                exact_matches = collect_alias_matches(
                    exact_candidates, form_name, form_aliases,
                    self._normalize_exact_text, "exact", "form"
                )
                for match in exact_matches:
                    if 1 in allowed_tiers:  # Tier gate
                        add_candidate({
                            "parent_key": parent_key,
                            "form_key": form_name,
                            "matched_on": match["matched_on"],
                            "matched_alias": match["matched_alias"],
                            "match_type": "exact",
                            "tier": 1,
                            "alias_len": match["alias_len"],
                            "match_source": match.get("match_source", 1),
                            "priority": parent_priority,  # From match_rules
                            "fallback_form_selected": False,
                            "fallback_form_name": None,
                            "match_data": build_form_match_data(parent_key, parent_data, form_name, form_data),
                        })

                normalized_matches = collect_alias_matches(
                    normalized_candidates, form_name, form_aliases,
                    self._normalize_text, "normalized", "form"
                )
                for match in normalized_matches:
                    if 3 in allowed_tiers:  # Tier gate
                        add_candidate({
                            "parent_key": parent_key,
                            "form_key": form_name,
                            "matched_on": match["matched_on"],
                            "matched_alias": match["matched_alias"],
                            "match_type": "normalized",
                            "tier": 3,
                            "alias_len": match["alias_len"],
                            "match_source": match.get("match_source", 1),
                            "priority": parent_priority,  # From match_rules
                            "fallback_form_selected": False,
                            "fallback_form_name": None,
                            "match_data": build_form_match_data(parent_key, parent_data, form_name, form_data),
                        })

                pattern_matches = collect_pattern_matches(
                    ing_name, std_name, ing_norm, std_norm,
                    form_pattern_aliases, form_contains_aliases, "form"
                )
                for match in pattern_matches:
                    if 5 in allowed_tiers:  # Tier gate
                        add_candidate({
                            "parent_key": parent_key,
                            "form_key": form_name,
                            "matched_on": match["matched_on"],
                            "matched_alias": match["matched_alias"],
                            "match_type": "pattern",
                            "tier": 5,
                            "alias_len": match["alias_len"],
                            "priority": parent_priority,  # From match_rules
                            "fallback_form_selected": False,
                            "fallback_form_name": None,
                            "match_data": build_form_match_data(parent_key, parent_data, form_name, form_data),
                        })

            # Parent-level matches
            exact_matches = collect_alias_matches(
                exact_candidates, parent_std_name, parent_aliases,
                self._normalize_exact_text, "exact", "parent"
            )
            for match in exact_matches:
                if 2 in allowed_tiers:  # Tier gate
                    match_data, fallback_selected, fallback_form = build_parent_match_data(parent_key, parent_data)
                    add_candidate({
                        "parent_key": parent_key,
                        "form_key": None,
                        "matched_on": match["matched_on"],
                        "matched_alias": match["matched_alias"],
                        "match_type": "exact",
                        "tier": 2,
                        "alias_len": match["alias_len"],
                        "match_source": match.get("match_source", 1),
                        "priority": parent_priority,  # From match_rules
                        "fallback_form_selected": fallback_selected,
                        "fallback_form_name": fallback_form,
                        "match_data": match_data,
                    })

            normalized_matches = collect_alias_matches(
                normalized_candidates, parent_std_name, parent_aliases,
                self._normalize_text, "normalized", "parent"
            )
            for match in normalized_matches:
                if 4 in allowed_tiers:  # Tier gate
                    match_data, fallback_selected, fallback_form = build_parent_match_data(parent_key, parent_data)
                    add_candidate({
                        "parent_key": parent_key,
                        "form_key": None,
                        "matched_on": match["matched_on"],
                        "matched_alias": match["matched_alias"],
                        "match_type": "normalized",
                        "tier": 4,
                        "alias_len": match["alias_len"],
                        "match_source": match.get("match_source", 1),
                        "priority": parent_priority,  # From match_rules
                        "fallback_form_selected": fallback_selected,
                        "fallback_form_name": fallback_form,
                        "match_data": match_data,
                    })

            pattern_matches = collect_pattern_matches(
                ing_name, std_name, ing_norm, std_norm,
                parent_pattern_aliases, parent_contains_aliases, "parent"
            )
            for match in pattern_matches:
                if 6 in allowed_tiers:  # Tier gate
                    match_data, fallback_selected, fallback_form = build_parent_match_data(parent_key, parent_data)
                    add_candidate({
                        "parent_key": parent_key,
                        "form_key": None,
                        "matched_on": match["matched_on"],
                        "matched_alias": match["matched_alias"],
                        "match_type": "pattern",
                        "tier": 6,
                        "priority": parent_priority,  # From match_rules
                        "alias_len": match["alias_len"],
                        "fallback_form_selected": fallback_selected,
                        "fallback_form_name": fallback_form,
                        "match_data": match_data,
                    })

        if not candidates:
            return None

        def candidate_sort_key(candidate: Dict) -> Tuple:
            return (
                candidate["tier"],                      # 1. Tier (exact > normalized > contains/pattern)
                candidate.get("match_source", 1),       # 2. Match source (raw > std > base)
                candidate.get("priority", 1),           # 3. Priority from match_rules (0 > 1 > 2)
                -candidate["alias_len"],                # 4. Longer alias wins within same priority
                0 if candidate["form_key"] else 1,      # 5. Form-level beats parent-level
                candidate["parent_key"],                # 6. Alphabetical parent key
                candidate["form_key"] or "",            # 7. Alphabetical form key
            )

        candidates.sort(key=candidate_sort_key)
        best = candidates[0]

        winning_tier = best["tier"]
        winning_candidates = [c for c in candidates if c["tier"] == winning_tier]

        match_tier = best["match_type"]
        if best["match_type"] == "pattern":
            if best["matched_on"].endswith("_contains"):
                match_tier = "contains"
            elif best["matched_on"].endswith("_pattern"):
                match_tier = "pattern"

        ambiguity_candidates = []
        if len(winning_candidates) > 1:
            reasons = ["tier"]
            best_match_source = best.get("match_source", 1)
            if any(c.get("match_source", 1) != best_match_source for c in winning_candidates):
                reasons.append("raw_name_priority")  # Raw input match beats std/base match
            else:
                best_priority = best.get("priority", 1)
                if any(c.get("priority", 1) != best_priority for c in winning_candidates):
                    reasons.append("match_rules_priority")  # Priority from match_rules
                else:
                    best_alias_len = best["alias_len"]
                    if any(c["alias_len"] != best_alias_len for c in winning_candidates):
                        reasons.append("longest_alias")
                    else:
                        best_form_rank = 0 if best["form_key"] else 1
                        if any((0 if c["form_key"] else 1) != best_form_rank for c in winning_candidates):
                            reasons.append("form_over_parent")
                        else:
                            best_parent_key = best["parent_key"]
                            if any(c["parent_key"] != best_parent_key for c in winning_candidates):
                                reasons.append("alphabetical_parent_key")
                            else:
                                best_form_key = best["form_key"] or ""
                                if any((c["form_key"] or "") != best_form_key for c in winning_candidates):
                                    reasons.append("alphabetical_form_key")
                                else:
                                    reasons.append("alphabetical_fallback")

            payload = {
                "ingredient_raw": ing_name,
                "ingredient_normalized": ing_norm,
                "candidates": [
                    {
                        "parent_key": c["parent_key"],
                        "form_key": c["form_key"],
                        "matched_alias": c["matched_alias"],
                        "matched_on": c["matched_on"],
                        "match_type": c["match_type"],
                        "tier": c["tier"],
                        "alias_len": c["alias_len"],
                    }
                    for c in winning_candidates
                ],
                "chosen": {
                    "parent_key": best["parent_key"],
                    "form_key": best["form_key"],
                    "matched_alias": best["matched_alias"],
                    "matched_on": best["matched_on"],
                    "match_type": best["match_type"],
                    "tier": best["tier"],
                    "alias_len": best["alias_len"],
                },
                "reason": reasons,
            }
            ambiguity_candidates = payload["candidates"]
            # Only warn if not resolved by raw_name_priority (clean resolution via match source)
            # Set ENRICH_DEBUG_AMBIGUITY=1 to see all ambiguity warnings
            if "raw_name_priority" not in reasons or os.environ.get("ENRICH_DEBUG_AMBIGUITY"):
                self._ambiguity_warning_count += 1
                if self._ambiguity_warning_count <= 10:
                    self.logger.warning(f"Ambiguous quality-map match: {json.dumps(payload, sort_keys=True)}")
                elif self._ambiguity_warning_count == 11:
                    self.logger.warning(
                        "Ambiguous quality-map warnings are being suppressed after 10 occurrences; "
                        "set ENRICH_DEBUG_AMBIGUITY=1 to log all details."
                    )
                else:
                    self.logger.debug(f"Ambiguous quality-map match: {json.dumps(payload, sort_keys=True)}")
            else:
                self.logger.debug(f"Ambiguity resolved by raw_name_priority: {json.dumps(payload, sort_keys=True)}")

        best["match_data"]["canonical_id"] = best["parent_key"]
        best["match_data"]["form_id"] = best["form_key"] or best["fallback_form_name"]
        best["match_data"]["match_tier"] = match_tier
        best["match_data"]["matched_alias"] = best["matched_alias"]
        best["match_data"]["matched_target"] = best["matched_on"]
        best["match_data"]["match_ambiguity_candidates"] = ambiguity_candidates
        best["match_data"]["fallback_form_selected"] = best["fallback_form_selected"]
        best["match_data"]["fallback_form_name"] = best["fallback_form_name"]

        if match_tier == "pattern":
            self.match_counters["pattern_match_wins_count"] += 1
        elif match_tier == "contains":
            self.match_counters["contains_match_wins_count"] += 1

        if best["fallback_form_selected"]:
            self.match_counters["parent_fallback_count"] += 1
            payload = {
                "ingredient_raw": ing_name,
                "ingredient_normalized": ing_norm,
                "parent_key": best["parent_key"],
                "fallback_form_name": best["fallback_form_name"],
                "match_type": best["match_type"],
                "tier": best["tier"],
            }
            self._parent_fallback_info_count += 1
            if self._parent_fallback_info_count <= 10:
                self.logger.info(f"Parent fallback form selected: {json.dumps(payload, sort_keys=True)}")
            elif self._parent_fallback_info_count == 11:
                self.logger.info(
                    "Parent fallback logs are being suppressed after 10 occurrences; "
                    "enable DEBUG logs for full detail."
                )
            else:
                self.logger.debug(f"Parent fallback form selected: {json.dumps(payload, sort_keys=True)}")

        return best["match_data"]

    def _collect_delivery_data(self, product: Dict) -> Dict:
        """
        Collect enhanced delivery system data for scoring Section A3.
        """
        delivery_db = self.databases.get('enhanced_delivery', {})
        all_text = self._get_all_product_text(product).lower()
        physical_state = product.get('physicalState', {}).get('langualCodeDescription', '').lower()

        # Word-boundary matching: raw substring matching false-positives on
        # short DB keys ("raw" inside "strawberry", "drops" inside
        # "gumdrops"). Patterns are compiled once per enricher instance.
        if not hasattr(self, '_delivery_patterns'):
            self._delivery_patterns = {}
            for key, data in delivery_db.items():
                if key.startswith("_") or not isinstance(data, dict):
                    continue
                self._delivery_patterns[key] = re.compile(
                    r'(?<!\w)' + re.escape(key.lower()) + r'(?!\w)'
                )

        matched_systems = []

        for delivery_name, delivery_data in delivery_db.items():
            if delivery_name.startswith("_") or not isinstance(delivery_data, dict):
                continue

            pattern = self._delivery_patterns.get(delivery_name)
            if pattern is None:
                continue

            # Check if delivery system mentioned in product
            # LABEL NAME PRESERVATION: Track WHERE the match was found
            match_source = None
            if pattern.search(all_text):
                match_source = "product_text"
            elif pattern.search(physical_state):
                match_source = "physical_state"

            if match_source:
                matched_systems.append({
                    # LABEL NAME PRESERVATION:
                    "name": delivery_name,  # Canonical from DB (used for scoring)
                    "canonical_name": delivery_name,  # Explicit canonical field
                    "raw_source_text": delivery_name.lower(),  # What was matched in product
                    "match_source": match_source,  # Where it was found
                    "tier": delivery_data.get('tier', 3),
                    "category": delivery_data.get('category', 'delivery'),
                    "description": delivery_data.get('description', '')
                })

        # Check physical state for lozenge (use data from JSON if available)
        if 'lozenge' in physical_state and not any(s['name'].lower() == 'lozenge' for s in matched_systems):
            lozenge_data = delivery_db.get('lozenge', {})
            matched_systems.append({
                # LABEL NAME PRESERVATION:
                "name": "lozenge",  # Canonical from DB
                "canonical_name": "lozenge",  # Explicit canonical field
                "raw_source_text": "lozenge",  # What was matched in physical state
                "match_source": "physical_state",  # Where it was found
                "tier": lozenge_data.get('tier', 2),
                "category": lozenge_data.get('category', 'delivery'),
                "description": lozenge_data.get('description', 'Lozenge delivery form')
            })

        delivery_data = {
            "matched": len(matched_systems) > 0,
            "systems": matched_systems,
            "highest_tier": min([s['tier'] for s in matched_systems]) if matched_systems else None
        }
        self._last_delivery_data = delivery_data
        return delivery_data

    def _collect_absorption_data(self, product: Dict) -> Dict:
        """
        Collect absorption enhancer data for scoring Section A4.
        Award bonus only if enhancer AND enhanced nutrient BOTH present.
        """
        enhancers_db = self.databases.get('absorption_enhancers', {})
        enhancers_list = enhancers_db.get('absorption_enhancers', [])

        # v3.0 scoring contract: enhancer pairing is ACTIVE-ONLY.
        all_ingredients = product.get('activeIngredients', [])

        # Build ingredient name set for quick lookup
        ingredient_names = set()
        for ing in all_ingredients:
            ingredient_names.add(self._normalize_text(ing.get('name', '')))
            ingredient_names.add(self._normalize_text(ing.get('standardName', '')))

        found_enhancers = []
        enhanced_nutrients_present = []

        for enhancer in enhancers_list:
            # DB schema uses 'standard_name'; keep 'name' as a fallback for robustness.
            # (Previously read only 'name', which is absent from the DB, so the target
            #  string was always empty and no enhancer ever matched -> A4 was unreachable.)
            enhancer_name = enhancer.get('standard_name') or enhancer.get('name', '')
            enhancer_aliases = enhancer.get('aliases', [])

            # Check if enhancer present
            enhancer_found = False
            for ing in all_ingredients:
                if self._exact_match(ing.get('name', ''), enhancer_name, enhancer_aliases) or \
                   self._exact_match(ing.get('standardName', ''), enhancer_name, enhancer_aliases):
                    enhancer_found = True
                    break

            if enhancer_found:
                # Check which enhanced nutrients are present
                enhances = enhancer.get('enhances', [])
                nutrients_found = []

                for nutrient in enhances:
                    nutrient_norm = self._normalize_text(nutrient)
                    if nutrient_norm in ingredient_names:
                        nutrients_found.append(nutrient)

                if nutrients_found:
                    enhanced_nutrients_present.extend(nutrients_found)

                found_enhancers.append({
                    "name": enhancer_name,
                    "id": enhancer.get('id', ''),
                    "enhances": enhances,
                    "nutrients_found_in_product": nutrients_found
                })

        # Qualify for bonus only if both enhancer AND enhanced nutrient present
        qualifies = len(found_enhancers) > 0 and len(enhanced_nutrients_present) > 0

        return {
            "enhancer_present": len(found_enhancers) > 0,
            "enhancers": found_enhancers,
            "enhanced_nutrients_present": list(set(enhanced_nutrients_present)),
            "qualifies_for_bonus": qualifies
        }

    def _collect_formulation_data(self, product: Dict) -> Dict:
        """
        Collect formulation excellence data for scoring Section A5.
        - Organic certification
        - Standardized botanicals
        - Synergy clusters
        """
        all_text = self._get_all_product_text(product)

        return {
            "organic": self._collect_organic_data(product, all_text),
            "standardized_botanicals": self._collect_standardized_botanicals(product),
            "synergy_clusters": self._collect_synergy_data(product)
        }

    def _collect_organic_data(self, product: Dict, all_text: str) -> Dict:
        """Collect organic certification data"""
        # LEGACY: Check for USDA Organic (product-level, not ingredient-level)
        usda_verified = bool(self.compiled_patterns['usda_organic'].search(all_text))
        certified_organic = bool(self.compiled_patterns['certified_organic'].search(all_text))
        organic_100 = bool(self.compiled_patterns['organic_100'].search(all_text))

        # Exclusion: "made with organic ingredients" doesn't count as certified
        made_with_organic = bool(self.compiled_patterns['made_with_organic'].search(all_text))

        claimed = usda_verified or certified_organic or organic_100

        # Determine claim text
        claim_text = ""
        if usda_verified:
            claim_text = "USDA Organic"
        elif certified_organic:
            claim_text = "Certified Organic"
        elif organic_100:
            claim_text = "100% Organic"

        # ENHANCED (v1.0.0): Evidence-based organic detection
        organic_evidence = self._collect_claims_from_rules_db(product, 'organic_certifications')

        return {
            # Legacy format for backward compatibility
            "claimed": claimed and not made_with_organic,
            "usda_verified": usda_verified,
            "claim_text": claim_text,
            "exclusion_matched": made_with_organic,
            # ENHANCED: Evidence-based detection (for hardened scoring)
            "evidence_based": {
                "organic_certifications": organic_evidence,
                "rules_db_version": self.reference_versions.get('cert_claim_rules', {}).get('version', 'unknown')
            }
        }

    def _collect_standardized_botanicals(self, product: Dict) -> List[Dict]:
        """Collect standardized botanical data"""
        botanicals_db = self.databases.get('standardized_botanicals', {})
        botanicals_list = botanicals_db.get('standardized_botanicals', [])

        active_ingredients = product.get('activeIngredients', [])
        all_text = self._get_all_product_text(product)

        found_botanicals = []

        for ingredient in active_ingredients:
            ing_name = ingredient.get('name', '')
            std_name = ingredient.get('standardName', '') or ing_name
            notes = ingredient.get('notes', '') or ''

            for botanical in botanicals_list:
                bot_name = botanical.get('standard_name', '')
                bot_aliases = botanical.get('aliases', [])

                if self._exact_match(ing_name, bot_name, bot_aliases) or \
                   self._exact_match(std_name, bot_name, bot_aliases):

                    # Extract standardization percentage
                    markers = botanical.get('markers', [])
                    min_threshold = botanical.get('min_threshold')
                    percentage = self._extract_percentage(notes + ' ' + all_text, markers)

                    # Determine if meets threshold
                    # Both percentage and min_threshold are stored as raw percentages
                    # e.g., percentage=5.0 means 5%, min_threshold=50 means 50%
                    meets_threshold = False
                    if min_threshold is not None:
                        if percentage > 0:
                            # Direct comparison - both are raw percentage values
                            meets_threshold = percentage >= min_threshold
                        else:
                            # No explicit percentage on label — fall through to
                            # marker word evidence (branded extracts like Longvida,
                            # Meriva, KSM-66 may not restate percentage)
                            meets_threshold = self._has_marker_word_match(
                                markers, notes + ' ' + all_text
                            )
                    else:
                        # No threshold - check for standardization evidence
                        # Use word boundary matching to avoid false positives like
                        # "De-Glycyrrhizinated" matching "glycyrrhizin"
                        meets_threshold = percentage > 0 or self._has_marker_word_match(
                            markers, notes + ' ' + all_text
                        )

                    found_botanicals.append({
                        "name": ing_name,
                        "botanical_id": botanical.get('id', ''),
                        "standard_name": bot_name,
                        "markers": markers,
                        "percentage_found": percentage,
                        "min_threshold": min_threshold,
                        "meets_threshold": meets_threshold
                    })
                    break  # One match per ingredient

        return found_botanicals

    def _extract_percentage(self, text: str, markers: List[str]) -> float:
        """Extract standardization percentage from text"""
        if not text:
            return 0.0

        text_lower = text.lower()

        # Try standardized pattern first
        match = self.compiled_patterns['standardized_pct'].search(text_lower)
        if match:
            return float(match.group(1))

        # Try marker-specific patterns
        for marker in markers:
            marker_lower = marker.lower()
            pattern = rf'(\d+(?:\.\d+)?)\s*%\s*{re.escape(marker_lower)}'
            match = re.search(pattern, text_lower)
            if match:
                return float(match.group(1))

        return 0.0

    def _has_marker_word_match(self, markers: List[str], text: str) -> bool:
        """
        Check if any marker appears as a whole word in text.

        Uses word boundary matching to avoid false positives like:
        - "De-Glycyrrhizinated" should NOT match "glycyrrhizin"
        - "glycyrrhizin content" SHOULD match "glycyrrhizin"

        Args:
            markers: List of marker compound names to search for
            text: Text to search within

        Returns:
            True if any marker is found as a word boundary match
        """
        if not text or not markers:
            return False

        text_lower = text.lower()

        for marker in markers:
            marker_lower = marker.lower()
            # Use word boundary regex to ensure we match whole words
            # \b matches word boundaries (start/end of word)
            pattern = rf'\b{re.escape(marker_lower)}\b'
            if re.search(pattern, text_lower):
                return True

        return False

    def _collect_synergy_data(self, product: Dict) -> List[Dict]:
        """Collect synergy cluster data"""
        synergy_db = self.databases.get('synergy_cluster', {})
        clusters = synergy_db.get('synergy_clusters', [])

        active_ingredients = product.get('activeIngredients', [])

        # Build ingredient lookup
        ingredient_info = {}
        for ing in active_ingredients:
            key = self._normalize_text(ing.get('standardName', '') or ing.get('name', ''))
            ingredient_info[key] = {
                "name": ing.get('name', ''),
                "quantity": ing.get('quantity', 0),
                "unit": ing.get('unit', '')
            }

        matched_clusters = []

        for cluster in clusters:
            cluster_ingredients = cluster.get('ingredients', [])
            min_doses = cluster.get('min_effective_doses', {})

            matched_ings = []
            doses_adequate = []

            for cluster_ing in cluster_ingredients:
                cluster_ing_norm = self._normalize_text(cluster_ing)

                # Check if this cluster ingredient is in product
                for ing_key, ing_data in ingredient_info.items():
                    # Prefer exact match to avoid false positives (e.g. "EPA" in "HEPATIC")
                    is_match = False
                    if cluster_ing_norm == ing_key:
                        is_match = True
                    # Allow substring match only for terms >= 6 chars
                    elif len(cluster_ing_norm) >= 6 and len(ing_key) >= 6:
                        if cluster_ing_norm in ing_key or ing_key in cluster_ing_norm:
                            is_match = True

                    if is_match:
                        # Found match
                        quantity = ing_data['quantity']
                        min_dose = min_doses.get(cluster_ing_norm, min_doses.get(cluster_ing, 0))

                        meets_min = quantity >= min_dose if min_dose > 0 else True

                        matched_ings.append({
                            "ingredient": ing_data['name'],
                            "cluster_ingredient": cluster_ing,
                            "quantity": quantity,
                            "unit": ing_data['unit'],
                            "min_effective_dose": min_dose,
                            "meets_minimum": meets_min
                        })
                        doses_adequate.append(meets_min)
                        break

            # Need at least 2 ingredients for synergy
            if len(matched_ings) >= 2:
                matched_clusters.append({
                    "cluster_id": cluster.get('id', ''),
                    "cluster_name": cluster.get('standard_name', ''),
                    "evidence_tier": cluster.get('evidence_tier', 3),
                    "matched_ingredients": matched_ings,
                    "match_count": len(matched_ings),
                    "doses_adequate": doses_adequate,
                    "all_adequate": all(doses_adequate) if doses_adequate else False
                })

        return matched_clusters

    # =========================================================================
    # SECTION B: SAFETY & PURITY DATA COLLECTORS
    # =========================================================================

    def _collect_contaminant_data(self, product: Dict) -> Dict:
        """
        Collect contaminant data for scoring Section B1.
        - Banned substances
        - Harmful additives
        - Allergens
        """
        all_ingredients = product.get('activeIngredients', []) + product.get('inactiveIngredients', [])

        return {
            "banned_substances": self._check_banned_substances(all_ingredients, product),
            "harmful_additives": self._check_harmful_additives(all_ingredients),
            "allergens": self._check_allergens(all_ingredients, product)
        }

    def _check_banned_substances(self, ingredients: List[Dict], product: Optional[Dict] = None) -> Dict:
        """Check for banned/recalled substances.

        Supports both legacy (category-based) and v3 (ingredients[]) structures.
        Implements negative_match_terms filtering and entity_type filtering.
        """
        banned_db = self.databases.get('banned_recalled_ingredients', {})
        allowlist_db = self.databases.get('banned_match_allowlist', {}) or {}
        allowlist_entries = allowlist_db.get('allowlist', []) or []
        denylist_entries = allowlist_db.get('denylist', []) or []
        allowlist_version = allowlist_db.get('_metadata', {}).get('version', 'unknown')
        found = []

        allowlist_by_id = {}
        for entry in allowlist_entries:
            canonical_id = entry.get('canonical_id')
            if canonical_id:
                allowlist_by_id.setdefault(canonical_id, []).append(entry)

        denylist_by_id = {}
        for entry in denylist_entries:
            canonical_id = entry.get('canonical_id')
            if canonical_id:
                denylist_by_id.setdefault(canonical_id, []).append(entry)

        # Collect banned items from either structure
        banned_items_with_category = []

        # v3 structure: single ingredients[] list
        if 'ingredients' in banned_db and isinstance(banned_db['ingredients'], list):
            for item in banned_db['ingredients']:
                if isinstance(item, dict):
                    # Use source_category or class_tags for category
                    category = item.get('source_category', '')
                    if not category and item.get('class_tags'):
                        category = item['class_tags'][0] if item['class_tags'] else ''
                    banned_items_with_category.append((category, item))
        else:
            # Legacy structure: category-based
            for section_key, section_data in banned_db.items():
                if section_key.startswith("_") or not isinstance(section_data, list):
                    continue
                for item in section_data:
                    if isinstance(item, dict):
                        banned_items_with_category.append((section_key, item))

        # Entity types that should be matched against ingredient labels
        # Classes and threats should NOT match via fuzzy/token matching
        # Products are now matchable with brand-qualified aliases and negative_match_terms
        MATCHABLE_ENTITY_TYPES = {'ingredient', 'contaminant', 'product', None, ''}

        product_name = ""
        brand_name = ""
        if isinstance(product, dict):
            product_name = (
                product.get('product_name')
                or product.get('fullName')
                or ""
            )
            brand_name = (
                product.get('brandName')
                or product.get('brand_name')
                or ""
            )

        scan_ingredients = ingredients if ingredients else [{}]

        for ing_idx, ingredient in enumerate(scan_ingredients):
            ing_name = ingredient.get('name', '')
            std_name = ingredient.get('standardName', '') or ing_name
            ing_name_lower = ing_name.lower()

            for section_key, banned_item in banned_items_with_category:
                if not isinstance(banned_item, dict):
                    continue

                # P0: Filter by entity_type - skip products/classes/threats
                entity_type = banned_item.get('entity_type', 'ingredient')
                if entity_type not in MATCHABLE_ENTITY_TYPES:
                    continue

                # Product-level recalls/bans should match product identity
                # (full name / brand), not ingredient labels.
                candidate_ing_name = ing_name
                candidate_std_name = std_name
                if entity_type == 'product':
                    if ing_idx > 0:
                        continue
                    candidate_ing_name = product_name or ing_name
                    candidate_std_name = brand_name or std_name
                candidate_ing_name_lower = candidate_ing_name.lower()

                banned_name = banned_item.get('standard_name', '')
                banned_aliases = banned_item.get('aliases', [])
                all_aliases = list(set(banned_aliases))

                banned_id = banned_item.get('id')
                allowlist_for = allowlist_by_id.get(banned_id, [])
                denylist_for = denylist_by_id.get(banned_id, [])

                # Check denylist first
                deny_hit = self._denylist_match(candidate_ing_name, denylist_for) or \
                    self._denylist_match(candidate_std_name, denylist_for)
                if deny_hit:
                    continue

                # P0: Check negative_match_terms (reduces false positives)
                match_rules = banned_item.get('match_rules', {})
                negative_terms = match_rules.get('negative_match_terms', [])
                if negative_terms and self._has_negative_match_term(candidate_ing_name_lower, negative_terms):
                    continue

                match_method = None
                matched_variant = None
                allowlist_id = None

                # Prefer strict exact/alias classification when available.
                # This supports B0 confidence gating in scoring without
                # relying on token-bounded fallback for every hit.
                direct_match = self._check_additive_match(
                    candidate_ing_name, candidate_std_name, banned_name, all_aliases
                )
                if direct_match:
                    method = str(direct_match.get("method", "")).lower()
                    if "alias" in method:
                        match_method = "alias"
                        matched_variant = direct_match.get("matched_alias")
                    else:
                        match_method = "exact"
                        matched_variant = banned_name

                if not match_method:
                    safe_token_aliases = self._filter_safe_token_aliases(banned_name, all_aliases)
                    matched, matched_variant = self._token_bounded_match(
                        candidate_ing_name, banned_name, safe_token_aliases
                    )
                    if matched:
                        if self._token_match_has_required_context(candidate_ing_name, banned_item, matched_variant):
                            match_method = "token_bounded"
                    else:
                        matched, matched_variant = self._token_bounded_match(
                            candidate_std_name, banned_name, safe_token_aliases
                        )
                        if matched:
                            if self._token_match_has_required_context(candidate_std_name, banned_item, matched_variant):
                                match_method = "token_bounded"

                if not match_method and allowlist_for:
                    allowlist_match = self._allowlist_match(candidate_ing_name, allowlist_for)
                    if not allowlist_match:
                        allowlist_match = self._allowlist_match(candidate_std_name, allowlist_for)
                    if allowlist_match:
                        match_method = allowlist_match.get("match_method")
                        matched_variant = allowlist_match.get("matched_variant")
                        allowlist_id = allowlist_match.get("allowlist_id")

                if match_method:
                    match_type = match_method
                    if match_type not in {"exact", "alias", "token_bounded"}:
                        mm = str(match_method).lower()
                        if "exact" in mm:
                            match_type = "exact"
                        elif "alias" in mm:
                            match_type = "alias"
                        elif "token" in mm:
                            match_type = "token_bounded"

                    confidence_map = {
                        "exact": 1.0,
                        "alias": 0.9,
                        "token_bounded": 0.7
                    }

                    found.append({
                        "ingredient": candidate_ing_name,
                        "banned_name": banned_name,
                        "banned_id": banned_item.get('id', ''),
                        "category": section_key,
                        "status": banned_item.get('status') or banned_item.get('recall_status'),
                        "severity_level": banned_item.get('severity_level', 'high'),
                        "reason": banned_item.get('reason', ''),
                        "match_type": match_type,
                        "confidence": confidence_map.get(match_type, 0.5),
                        "match_method": match_method,
                        "matched_variant": matched_variant,
                        "allowlist_id": allowlist_id,
                        "allowlist_version": allowlist_version if allowlist_id else None,
                        "entity_type": entity_type,
                        "legal_status_enum": banned_item.get('legal_status_enum'),
                        "clinical_risk_enum": banned_item.get('clinical_risk_enum'),
                    })

        return {
            "found": len(found) > 0,
            "substances": found
        }

    def _has_negative_match_term(self, text: str, negative_terms: List[str]) -> bool:
        """Check if text contains any negative match terms (case-insensitive).

        Used to filter out false positives like 'ephedra-free', 'kava-free', etc.
        """
        text_lower = text.lower()
        for term in negative_terms:
            if term.lower() in text_lower:
                return True
        return False

    @property
    def NATURAL_COLOR_INDICATORS(self) -> List[str]:
        """P0.5: Natural color indicators - loaded from data/color_indicators.json (required)"""
        color_db = self.databases.get('color_indicators', {})
        indicators = color_db.get('natural_indicators', [])
        if not indicators:
            # This should never happen if _validate_loaded_databases passed
            raise RuntimeError("color_indicators.json missing or empty - cannot classify colors")
        return indicators

    @property
    def ARTIFICIAL_COLOR_INDICATORS(self) -> List[str]:
        """P0.5: Artificial color indicators - loaded from data/color_indicators.json (required)"""
        color_db = self.databases.get('color_indicators', {})
        return color_db.get('artificial_indicators', [])

    @property
    def EXPLICIT_NATURAL_DYES(self) -> List[str]:
        """P0.5: Explicit natural dyes - exact match bypasses indicator heuristics"""
        color_db = self.databases.get('color_indicators', {})
        return color_db.get('explicit_natural_dyes', [])

    @property
    def EXPLICIT_ARTIFICIAL_DYES(self) -> List[str]:
        """P0.5: Explicit artificial dyes - exact match bypasses indicator heuristics"""
        color_db = self.databases.get('color_indicators', {})
        return color_db.get('explicit_artificial_dyes', [])

    def _check_harmful_additives(self, ingredients: List[Dict]) -> Dict:
        """
        Check for harmful additives.

        P0.5: Natural colors classification with EXPLICIT DYE PRIORITY:
        1. Check explicit_artificial_dyes FIRST (deterministic) - always flag as artificial
        2. Check explicit_natural_dyes NEXT - never flag as artificial
        3. Fall back to indicator matching for ambiguous "Colors" ingredients
        """
        harmful_db = self.databases.get('harmful_additives', {})
        harmful_list = harmful_db.get('harmful_additives', [])
        found = []

        # Pre-lowercase explicit dye lists for matching
        explicit_artificial = [d.lower() for d in self.EXPLICIT_ARTIFICIAL_DYES]
        explicit_natural = [d.lower() for d in self.EXPLICIT_NATURAL_DYES]

        for ingredient in ingredients:
            ing_name = ingredient.get('name', '')
            std_name = ingredient.get('standardName', '') or ing_name
            ing_forms = ingredient.get('forms', [])
            ing_notes = ingredient.get('notes', '')
            ing_name_lower = ing_name.lower()
            std_name_lower = std_name.lower()

            # P0.5 PRIORITY 1: Check explicit artificial dyes FIRST (deterministic)
            # These ALWAYS get flagged, regardless of context
            is_explicit_artificial = any(
                dye in ing_name_lower or dye in std_name_lower
                for dye in explicit_artificial
            )
            matched_explicit_artificial = None
            if is_explicit_artificial:
                matched_explicit_artificial = next(
                    (dye for dye in self.EXPLICIT_ARTIFICIAL_DYES
                     if dye.lower() in ing_name_lower or dye.lower() in std_name_lower),
                    None
                )

            # P0.5 PRIORITY 2: Check explicit natural dyes NEXT
            # These NEVER get flagged as artificial
            is_explicit_natural = any(
                dye in ing_name_lower or dye in std_name_lower
                for dye in explicit_natural
            )
            matched_explicit_natural = None
            if is_explicit_natural:
                matched_explicit_natural = next(
                    (dye for dye in self.EXPLICIT_NATURAL_DYES
                     if dye.lower() in ing_name_lower or dye.lower() in std_name_lower),
                    None
                )

            # P0.5 PRIORITY 3: Indicator-based matching (fallback for ambiguous terms)
            # Only used if no explicit dye match
            forms_text = ''
            if ing_forms:
                for form in ing_forms:
                    if isinstance(form, dict):
                        form_prefix = form.get('prefix', '') or ''
                        form_name = form.get('name', '') or ''
                        forms_text += ' ' + form_prefix + ' ' + form_name
                    elif isinstance(form, str):
                        forms_text += ' ' + form

            combined_text = (forms_text + ' ' + (ing_notes or '')).lower()
            matched_natural_indicator = None
            matched_artificial_indicator = None

            if not is_explicit_artificial and not is_explicit_natural:
                # Only check indicators if no explicit match
                for ind in self.NATURAL_COLOR_INDICATORS:
                    if ind in combined_text:
                        matched_natural_indicator = ind
                        break
                for ind in self.ARTIFICIAL_COLOR_INDICATORS:
                    if ind in combined_text:
                        matched_artificial_indicator = ind
                        break

            # Determine final classification
            # Priority: explicit_artificial > explicit_natural > artificial_indicator > natural_indicator
            is_natural_color = (
                is_explicit_natural or
                (matched_natural_indicator and not is_explicit_artificial and not matched_artificial_indicator)
            )
            is_artificial_color = is_explicit_artificial or (matched_artificial_indicator and not is_explicit_natural)

            for additive in harmful_list:
                additive_name = additive.get('standard_name', '')
                additive_id = additive.get('id', '')
                additive_aliases = additive.get('aliases', [])
                additive_category = additive.get('category', '')

                # P0.5: Skip "Artificial Colors (General)" for natural colorants
                # BUT always include if this is an explicit artificial dye
                if not is_explicit_artificial and is_natural_color and (
                    additive_id == 'ADD_ARTIFICIAL_COLORS' or
                    'artificial color' in additive_name.lower() or
                    additive_category == 'colorant_artificial'
                ):
                    continue

                # Check for match and track HOW matched for provenance
                match_result = self._check_additive_match(
                    ing_name, std_name, additive_name, additive_aliases
                )
                if match_result:
                    # Build classification evidence
                    classification_evidence = {}
                    if matched_explicit_artificial:
                        classification_evidence['matched_explicit_artificial_dye'] = matched_explicit_artificial
                    if matched_explicit_natural:
                        classification_evidence['matched_explicit_natural_dye'] = matched_explicit_natural
                    if matched_natural_indicator:
                        classification_evidence['matched_natural_indicator'] = matched_natural_indicator
                    if matched_artificial_indicator:
                        classification_evidence['matched_artificial_indicator'] = matched_artificial_indicator

                    found.append({
                        # LABEL NAME PRESERVATION:
                        # - ingredient/raw_source_text: exact label text (user-facing)
                        # - additive_name/canonical_name: database canonical (internal)
                        "ingredient": ing_name,  # Label-facing name
                        "raw_source_text": ing_name,  # Provenance (exact label text)
                        "additive_name": additive_name,  # Canonical from DB
                        "canonical_name": additive_name,  # Explicit canonical field
                        "additive_id": additive_id,  # Canonical ID
                        "match_method": match_result["method"],  # How matched
                        "matched_alias": match_result.get("matched_alias"),  # Which alias if any
                        "severity_level": additive.get('severity_level', 'low'),
                        "category": additive_category,
                        "is_natural_color": is_natural_color if 'color' in ing_name_lower else None,
                        "classification_evidence": classification_evidence if classification_evidence else None
                    })

        return {
            "found": len(found) > 0,
            "additives": found
        }

    # P0.1: Allergen presence type precedence (higher = wins in conflicts)
    ALLERGEN_PRESENCE_PRIORITY = {
        "contains": 5,
        "may_contain": 4,
        "facility_warning": 3,
        "ingredient_list": 2,
        "unknown": 1
    }

    def _extract_allergen_presence_from_text(self, product: Dict) -> List[Dict]:
        """
        P0.1: Extract allergens with presence_type from label text sources.

        Parses:
        - labelText.parsed.allergens (e.g., ["soy", "milk"])
        - labelText.parsed.warnings (e.g., "Contains: Milk")
        - statements[] for "Contains milk and soy", "May contain", "Manufactured in a facility"

        Returns: List of {allergen_id, presence_type, evidence_text, matched_text}
        """
        allergen_db = self.databases.get('allergens', {})
        allergen_list = allergen_db.get('common_allergens', allergen_db.get('allergens', []))

        found = []

        # Build allergen lookup by name/alias
        allergen_lookup = {}
        for allergen in allergen_list:
            allergen_name = allergen.get('standard_name', '').lower()
            allergen_lookup[allergen_name] = allergen
            for alias in allergen.get('aliases', []):
                allergen_lookup[alias.lower()] = allergen

        # Source 1: labelText.parsed.allergens
        label_text = product.get('labelText', {})
        if isinstance(label_text, dict):
            parsed = label_text.get('parsed', {})
            parsed_allergens = parsed.get('allergens', [])

            # CRITICAL FIX: Build set of negated allergen terms from multiple sources
            # This prevents detecting allergens when product claims to be free of them
            # Example: Product with "dairy-free" claim should NOT detect milk allergen
            negated_terms = set()

            # Source 1: labelText.parsed.allergenFree (from upstream parser)
            allergen_free_raw = parsed.get('allergenFree', [])
            for free_claim in allergen_free_raw:
                if isinstance(free_claim, str):
                    negated_terms.add(free_claim.lower().strip())

            # Source 2: compliance_data.allergen_free_claims (authoritative enrichment source)
            # This catches edge cases where parsed allergenFree might be incomplete
            compliance_data = product.get('compliance_data', {})
            for claim in compliance_data.get('allergen_free_claims', []):
                if isinstance(claim, str):
                    negated_terms.add(claim.lower().strip())

            # Source 3: targetGroups for "X Free" claims
            target_groups = product.get('targetGroups', [])
            for tg in target_groups:
                tg_text = tg if isinstance(tg, str) else (tg.get('text', '') if isinstance(tg, dict) else '')
                tg_lower = tg_text.lower()
                # Extract "X" from "X Free" or "X-Free" patterns
                free_match = re.search(r'(\w+)[\s-]*free', tg_lower)
                if free_match:
                    negated_terms.add(free_match.group(1))

            for allergen_text in parsed_allergens:
                if isinstance(allergen_text, str):
                    allergen_lower = allergen_text.lower().strip()
                    if allergen_lower in allergen_lookup:
                        allergen = allergen_lookup[allergen_lower]

                        # Check if this allergen is negated by a "free" claim
                        # Compare against allergen name AND all its aliases
                        allergen_name_lower = allergen.get('standard_name', '').lower()
                        allergen_aliases = [a.lower() for a in allergen.get('aliases', [])]
                        all_allergen_terms = {allergen_lower, allergen_name_lower} | set(allergen_aliases)

                        # If any allergen term matches any negated term, skip this allergen
                        if negated_terms & all_allergen_terms:
                            self.logger.debug(
                                f"Skipping negated allergen '{allergen_text}' "
                                f"(free claims: {negated_terms & all_allergen_terms})"
                            )
                            continue

                        found.append({
                            "allergen_id": allergen.get('id', ''),
                            "allergen_name": allergen.get('standard_name', ''),
                            "presence_type": "contains",  # Parsed allergens imply contains
                            "source": "label_parsed",
                            "evidence": f"labelText.parsed.allergens: {allergen_text}",
                            "matched_text": allergen_text,
                            "severity_level": allergen.get('severity_level', 'low'),
                            "regulatory_status": allergen.get('regulatory_status', ''),
                            "general_handling": allergen.get('general_handling', 'flag_only')
                        })

            # Source 2: labelText.parsed.warnings
            parsed_warnings = parsed.get('warnings', [])
            for warning in parsed_warnings:
                warning_text = warning if isinstance(warning, str) else str(warning)
                self._parse_allergen_statement(warning_text, allergen_lookup, found, "label_warning")

        # Source 3: statements[]
        statements = product.get('statements', [])
        for statement in statements:
            if isinstance(statement, dict):
                statement_text = statement.get('text', '') or statement.get('notes', '') or ''
            else:
                statement_text = str(statement)

            self._parse_allergen_statement(statement_text, allergen_lookup, found, "label_statement")

        return found

    def _parse_allergen_statement(self, text: str, allergen_lookup: Dict, found: List[Dict], source: str) -> None:
        """
        Parse a text statement for allergen declarations.

        Patterns:
        - "Contains: milk, soy" -> presence_type=contains
        - "May contain peanuts" -> presence_type=may_contain
        - "Manufactured in a facility that processes tree nuts" -> presence_type=facility_warning

        IMPORTANT: Negation patterns are SKIPPED:
        - "Contains no milk, soy" -> NOT added (this is an allergen-free claim)
        - "Free from milk and soy" -> NOT added
        - "Does not contain milk" -> NOT added
        """
        text_lower = text.lower()

        # CRITICAL: Check for negation patterns FIRST - skip entire statement if negated
        # These statements list allergens the product is FREE FROM, not containing
        negation_patterns = [
            r'contains?\s+no\s+',           # "Contains no milk"
            r'does\s+not\s+contain',        # "Does not contain milk"
            r'free\s+(?:from|of)\s+',       # "Free from milk"
            r'without\s+',                  # "Without milk"
            r'no\s+added\s+',               # "No added milk"
        ]
        for neg_pattern in negation_patterns:
            if re.search(neg_pattern, text_lower):
                self.logger.debug(f"Skipping negated allergen statement: {text[:80]}...")
                return  # Skip this entire statement - it's declaring what product is FREE FROM

        # Pattern 1: "Contains X" / "Contains: X, Y"
        contains_patterns = [
            r'contains[:\s]+([^.]+)',
            r'contains\s+(\w+(?:\s+and\s+\w+)*)',
        ]
        for pattern in contains_patterns:
            match = re.search(pattern, text_lower)
            if match:
                allergen_text = match.group(1)
                self._extract_allergens_from_text(allergen_text, allergen_lookup, found,
                                                   "contains", source, text)

        # Pattern 2: "May contain X"
        may_contain_patterns = [
            r'may\s+contain[:\s]+([^.]+)',
            r'may\s+contain\s+(\w+(?:\s+and\s+\w+)*)',
        ]
        for pattern in may_contain_patterns:
            match = re.search(pattern, text_lower)
            if match:
                allergen_text = match.group(1)
                self._extract_allergens_from_text(allergen_text, allergen_lookup, found,
                                                   "may_contain", source, text)

        # Pattern 3: Facility warnings
        facility_patterns = [
            r'manufactured\s+in\s+a\s+facility\s+(?:that\s+)?(?:also\s+)?(?:processes|handles|produces)[:\s]+([^.]+)',
            r'produced\s+in\s+a\s+facility\s+(?:that\s+)?(?:also\s+)?(?:processes|handles)[:\s]+([^.]+)',
            r'made\s+in\s+a\s+facility\s+that\s+(?:also\s+)?(?:processes|handles)[:\s]+([^.]+)',
        ]
        for pattern in facility_patterns:
            match = re.search(pattern, text_lower)
            if match:
                allergen_text = match.group(1)
                self._extract_allergens_from_text(allergen_text, allergen_lookup, found,
                                                   "facility_warning", source, text)

    def _extract_allergens_from_text(self, text: str, allergen_lookup: Dict, found: List[Dict],
                                      presence_type: str, source: str, evidence: str) -> None:
        """Extract individual allergens from a comma/and-separated text."""
        # Split on comma, "and", "&"
        parts = re.split(r'[,&]|\band\b', text.lower())

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Check if this matches any allergen
            if part in allergen_lookup:
                allergen = allergen_lookup[part]
                found.append({
                    "allergen_id": allergen.get('id', ''),
                    "allergen_name": allergen.get('standard_name', ''),
                    "presence_type": presence_type,
                    "source": source,
                    "evidence": evidence,
                    "matched_text": part,
                    "severity_level": allergen.get('severity_level', 'low'),
                    "regulatory_status": allergen.get('regulatory_status', ''),
                    "general_handling": allergen.get('general_handling', 'flag_only')
                })

    def _check_allergens(self, ingredients: List[Dict], product: Dict) -> Dict:
        """
        P0.1: Check for allergens with presence_type and precedence.

        Sources (in precedence order):
        1. Label statements/warnings (Contains / May contain / Facility)
        2. Ingredient list (direct ingredient-derived)
        3. Heuristics (hidden allergens)

        Conflict Resolution:
        - contains > may_contain > facility_warning > ingredient_list > unknown
        - If same allergen from multiple sources, highest precedence wins
        """
        allergen_db = self.databases.get('allergens', {})
        allergen_list = allergen_db.get('common_allergens', allergen_db.get('allergens', []))

        all_text = self._get_all_product_text(product).lower()

        # Collect allergens from all sources
        all_found = []

        # Source 1: Label text (has precedence)
        label_allergens = self._extract_allergen_presence_from_text(product)
        all_found.extend(label_allergens)

        # Source 2: Ingredient list
        for ingredient in ingredients:
            ing_name = ingredient.get('name', '')
            std_name = ingredient.get('standardName', '') or ing_name

            for allergen in allergen_list:
                allergen_name = allergen.get('standard_name', '')
                allergen_aliases = allergen.get('aliases', [])

                if self._exact_match(ing_name, allergen_name, allergen_aliases) or \
                   self._exact_match(std_name, allergen_name, allergen_aliases):

                    # Check for negation context
                    if self._is_negated(allergen_name, allergen_aliases, all_text):
                        continue

                    all_found.append({
                        "allergen_id": allergen.get('id', ''),
                        "allergen_name": allergen_name,
                        "ingredient": ing_name,
                        "presence_type": "ingredient_list",
                        "source": "ingredient_list",
                        "evidence": f"Ingredient: {ing_name}",
                        "matched_text": ing_name,
                        "severity_level": allergen.get('severity_level', 'low'),
                        "regulatory_status": allergen.get('regulatory_status', ''),
                        "general_handling": allergen.get('general_handling', 'flag_only'),
                        "category": allergen.get('category', '')
                    })

        # Deduplicate by allergen_id, keeping highest precedence
        deduplicated = {}
        for item in all_found:
            allergen_id = item.get('allergen_id', '')
            if not allergen_id:
                continue

            existing = deduplicated.get(allergen_id)
            if existing:
                # Compare precedence
                existing_priority = self.ALLERGEN_PRESENCE_PRIORITY.get(existing.get('presence_type', 'unknown'), 1)
                new_priority = self.ALLERGEN_PRESENCE_PRIORITY.get(item.get('presence_type', 'unknown'), 1)

                if new_priority > existing_priority:
                    deduplicated[allergen_id] = item
            else:
                deduplicated[allergen_id] = item

        found = list(deduplicated.values())

        # Check for may_contain/facility warnings
        has_may_contain = any(a.get('presence_type') in ['may_contain', 'facility_warning'] for a in found)

        return {
            "found": len(found) > 0,
            "allergens": found,
            "has_may_contain_warning": has_may_contain
        }

    def _is_negated(self, name: str, aliases: List[str], text: str) -> bool:
        """
        Check if allergen mention is in negation context.

        IMPORTANT - SCOPE LIMITATION:
        This negation check applies ONLY to free-text fields:
        - allergenStatement (e.g., "Contains no milk, egg, or soy")
        - labelStatement (e.g., "Free from common allergens")
        - targetGroups text (e.g., "Dairy-Free")
        - marketing claims and descriptions

        This check MUST NOT be used to filter out allergens detected from:
        - structured ingredient rows (activeIngredients, inactiveIngredients)
        - ingredient name fields directly

        Rationale: If "Milk Protein" appears as an ingredient row, it IS an
        allergen regardless of any "dairy-free" claim elsewhere. The structured
        ingredient list is authoritative. Negation only filters allergens
        detected via text scanning of unstructured fields.

        Args:
            name: Allergen standard name (e.g., "milk")
            aliases: List of allergen aliases (e.g., ["dairy", "lactose"])
            text: The free-text to scan for negation context (must be lowercase)

        Returns:
            True if allergen appears in negation context, False otherwise
        """
        negation_patterns = [
            r'\bno\s+', r'\bfree\s+(from|of)\s+', r'\bwithout\s+',
            r'\bdoes\s+not\s+contain\s+', r'\bcontains\s+no\s+'
        ]

        terms = [name.lower()] + [a.lower() for a in aliases]

        for term in terms:
            for pattern in negation_patterns:
                if re.search(pattern + r'.*?' + re.escape(term), text):
                    return True

        return False

    def _collect_compliance_data(self, product: Dict,
                                  contaminant_data: Optional[Dict] = None) -> Dict:
        """
        Collect allergen & dietary compliance data for scoring Section B2.

        Args:
            product: The product dict to analyze
            contaminant_data: Pre-collected contaminant data to avoid double-collection
        """
        target_groups = product.get('targetGroups', [])
        all_text = self._get_all_product_text(product).lower()

        # Extract claims from target groups and text
        allergen_free_claims = []
        for pattern_name, pattern in ALLERGEN_FREE_PATTERNS.items():
            if re.search(pattern, all_text, re.I):
                allergen_free_claims.append(pattern_name)

        # Check target groups - normalize list items (can be str or dict)
        normalized_groups = []
        for tg in target_groups:
            if isinstance(tg, str):
                normalized_groups.append(tg)
            elif isinstance(tg, dict):
                normalized_groups.append(tg.get('text', '') or tg.get('name', '') or '')
        target_lower = ' '.join(normalized_groups).lower()

        gluten_free = 'gluten free' in target_lower or 'gluten-free' in target_lower
        dairy_free = 'dairy free' in target_lower or 'dairy-free' in target_lower
        soy_free = 'soy free' in target_lower or 'soy-free' in target_lower
        vegan = 'vegan' in target_lower
        vegetarian = 'vegetarian' in target_lower

        # Check for conflicts with detected allergens
        # Use pre-collected data if provided (avoids double-collection)
        if contaminant_data is None:
            contaminant_data = self._collect_contaminant_data(product)
        detected_allergens = contaminant_data['allergens']['allergens']

        conflicts = []
        if dairy_free and any('milk' in a['allergen_name'].lower() or 'dairy' in a['allergen_name'].lower()
                             for a in detected_allergens):
            conflicts.append("dairy-free claim conflicts with detected dairy")
        if soy_free and any('soy' in a['allergen_name'].lower() for a in detected_allergens):
            conflicts.append("soy-free claim conflicts with detected soy")
        if gluten_free and any('wheat' in a['allergen_name'].lower() or 'gluten' in a['allergen_name'].lower()
                              for a in detected_allergens):
            conflicts.append("gluten-free claim conflicts with detected gluten/wheat")

        # P0.1: Use structured allergen data for may_contain detection
        # Fall back to text search if not available
        may_contain_from_allergens = contaminant_data['allergens'].get('has_may_contain_warning', False)
        may_contain_from_text = 'may contain' in all_text or 'shared equipment' in all_text
        may_contain = may_contain_from_allergens or may_contain_from_text

        # ENHANCED (v1.0.0): Evidence-based allergen claims with validation
        allergen_evidence = self._collect_claims_from_rules_db(product, 'allergen_free_claims')

        # Apply conflict checking to evidence objects
        for evidence in allergen_evidence:
            conflict_allergens = []
            dedupe_key = evidence.get('dedupe_key', '')

            # Check for actual allergen conflicts
            if 'gluten' in dedupe_key and any(
                'wheat' in a['allergen_name'].lower() or 'gluten' in a['allergen_name'].lower()
                for a in detected_allergens
            ):
                conflict_allergens.append('gluten/wheat detected')
            if 'dairy' in dedupe_key and any(
                'milk' in a['allergen_name'].lower() or 'dairy' in a['allergen_name'].lower()
                for a in detected_allergens
            ):
                conflict_allergens.append('dairy/milk detected')
            if 'soy' in dedupe_key and any(
                'soy' in a['allergen_name'].lower() for a in detected_allergens
            ):
                conflict_allergens.append('soy detected')
            if 'nut' in dedupe_key and any(
                'nut' in a['allergen_name'].lower() for a in detected_allergens
            ):
                conflict_allergens.append('nut detected')

            # Update score_eligible based on conflicts
            if conflict_allergens and evidence.get('score_eligible', False):
                evidence['score_eligible'] = False
                evidence['ineligibility_reason'] = f'allergen_conflict:{",".join(conflict_allergens)}'
                evidence['proximity_conflicts'].extend(conflict_allergens)

            # Also check for may_contain warning
            if may_contain and evidence.get('score_eligible', False):
                evidence['score_eligible'] = False
                evidence['ineligibility_reason'] = 'may_contain_warning'

        return {
            # Legacy format for backward compatibility
            "allergen_free_claims": allergen_free_claims,
            "gluten_free": gluten_free,
            "dairy_free": dairy_free,
            "soy_free": soy_free,
            "vegan": vegan,
            "vegetarian": vegetarian,
            "conflicts": conflicts,
            "has_may_contain_warning": may_contain,
            "verified": len(conflicts) == 0,
            # ENHANCED: Evidence-based detection (for hardened scoring)
            "evidence_based": {
                "allergen_free_claims": allergen_evidence,
                "rules_db_version": self.reference_versions.get('cert_claim_rules', {}).get('version', 'unknown')
            }
        }

    # =========================================================================
    # CLAIMS VALIDATION SYSTEM (v1.0.0 - Evidence-based claim detection)
    # =========================================================================

    def _get_field_groups(self) -> Dict[str, List[str]]:
        """Get source field groups from cert_claim_rules database."""
        cert_rules = self.databases.get('cert_claim_rules', {})
        return cert_rules.get('config', {}).get('source_field_groups', {
            'product_level_fields': ['statements', 'qualityFeatures', 'certifications',
                                      'claims', 'labelText'],
            'ingredient_fields': ['ingredients', 'activeIngredients', 'inactiveIngredients',
                                   'supplementFacts', 'otherIngredients', 'ingredientRows'],
            'any_field': ['*']
        })

    def _check_claim_with_validation(self, text: str, source_field: str, rule: Dict,
                                      field_groups: Dict) -> Optional[Dict]:
        """
        Check claim against rule with negative pattern and scope validation.

        This method implements the hardened claim detection system:
        1. Match positive patterns to find potential claims
        2. Check negative patterns to reject false positives
        3. Validate scope (product-level claims only from approved fields)
        4. Return evidence object with full audit trail

        NOTE: Does NOT compute points_awarded - that's scoring's responsibility

        Args:
            text: Text to search for claim
            source_field: Field name where text came from (for scope validation)
            rule: Rule definition from cert_claim_rules.json
            field_groups: Centralized field groups for scope validation

        Returns:
            Evidence object if claim found, None otherwise
        """
        # 1. Check positive patterns
        positive_match = None
        for i, pattern in enumerate(rule.get('positive_patterns', [])):
            try:
                match = re.search(pattern, text, re.I)
                if match:
                    positive_match = {
                        'text': match.group(),
                        'start': match.start(),
                        'end': match.end(),
                        'pattern_id': f"{rule.get('id', 'UNKNOWN')}_positive_{i}"
                    }
                    break
            except re.error as e:
                self.logger.warning(f"Invalid regex pattern in rule {rule.get('id')}: {e}")
                continue

        if not positive_match:
            return None  # No claim found

        # 2. SCOPE VALIDATION (using centralized field groups)
        scope_rule = rule.get('scope_rule', 'any')
        approved_field_group = rule.get('approved_field_group', 'any_field')
        approved_fields = field_groups.get(approved_field_group, ['*'])
        scope_violation = False

        if scope_rule == 'product_level_only' and '*' not in approved_fields:
            # Check if source_field base is in approved group
            field_base = source_field.split('[')[0].split('.')[0]
            if field_base not in approved_fields:
                scope_violation = True

        # 3. Check negative patterns with evidence capture
        negation = {
            'negated': False,
            'negation_match_text': None,
            'negation_source_field': None,
            'negation_pattern_id': None
        }
        for j, pattern in enumerate(rule.get('negative_patterns', [])):
            try:
                neg_match = re.search(pattern, text, re.I)
                if neg_match:
                    negation = {
                        'negated': True,
                        'negation_match_text': neg_match.group(),
                        'negation_source_field': source_field,
                        'negation_pattern_id': f"{rule.get('id', 'UNKNOWN')}_negative_{j}"
                    }
                    break
            except re.error:
                continue

        # 4. Check required tokens if specified
        required_tokens = rule.get('required_tokens', [])
        required_tokens_missing = False
        if required_tokens:
            text_lower = text.lower()
            if not any(token.lower() in text_lower for token in required_tokens):
                required_tokens_missing = True

        # 5. Check required context if specified (for batch traceability)
        required_context = rule.get('required_context', [])
        context_missing = False
        if required_context:
            text_lower = text.lower()
            if not any(ctx.lower() in text_lower for ctx in required_context):
                context_missing = True

        # 6. Proximity check (for allergen claims)
        proximity_window = rule.get('proximity_window', 150)
        proximity_conflicts = []
        conflict_allergens = rule.get('conflict_allergens', [])
        if conflict_allergens:
            window_start = max(0, positive_match['start'] - proximity_window)
            window_end = min(len(text), positive_match['end'] + proximity_window)
            nearby_text = text[window_start:window_end].lower()

            for allergen in conflict_allergens:
                if allergen.lower() in nearby_text:
                    # Check if it's not the "-free" claim itself
                    if f"{allergen.lower()}-free" not in nearby_text and f"{allergen.lower()} free" not in nearby_text:
                        proximity_conflicts.append(allergen)

        # 7. Determine score eligibility with REASON
        evidence_strength = rule.get('evidence_strength', 'weak')
        score_eligible = True
        ineligibility_reason = None

        if negation['negated']:
            score_eligible = False
            ineligibility_reason = 'negated'
        elif scope_violation:
            score_eligible = False
            ineligibility_reason = 'scope_violation'
        elif required_tokens_missing:
            score_eligible = False
            ineligibility_reason = 'required_tokens_missing'
        elif context_missing:
            score_eligible = False
            ineligibility_reason = 'required_context_missing'
        elif len(proximity_conflicts) > 0:
            score_eligible = False
            ineligibility_reason = f'proximity_conflict:{",".join(proximity_conflicts)}'
        elif evidence_strength == 'weak':
            score_eligible = False
            ineligibility_reason = 'weak_evidence'

        # NOTE: points_awarded is NOT computed here - scoring does that
        return {
            'rule_id': rule.get('id', 'UNKNOWN'),
            'claim_type': rule.get('claim_type', 'unknown'),
            'display_name': rule.get('display_name', rule.get('id', 'Unknown')),
            'dedupe_key': rule.get('dedupe_key'),
            'matched_text': positive_match['text'],
            'source_field': source_field,
            'pattern_id': positive_match['pattern_id'],
            'scope_rule': scope_rule,
            'approved_field_group': approved_field_group,
            'scope_violation': scope_violation,
            'negation': negation,
            'proximity_conflicts': proximity_conflicts,
            'evidence_strength': evidence_strength,
            'score_eligible': score_eligible,
            'ineligibility_reason': ineligibility_reason,
            'points_if_eligible': rule.get('points_if_eligible', 0)
        }

    def _collect_claims_from_rules_db(self, product: Dict, rule_category: str) -> List[Dict]:
        """
        Collect claims from a specific category in cert_claim_rules.json.

        FIXED (v1.0.1): Now scans field-by-field for proper scope validation.
        - Iterates through each product field separately
        - Passes real source_field path to _check_claim_with_validation
        - Deduplicates by dedupe_key, keeping best evidence
        - Adds context_snippet for audit readability

        Args:
            product: Product data
            rule_category: Category key in cert_claim_rules (e.g., 'third_party_programs', 'gmp_certifications')

        Returns:
            List of evidence objects for matched claims (deduplicated)
        """
        cert_rules = self.databases.get('cert_claim_rules', {})
        rules = cert_rules.get('rules', {}).get(rule_category, {})
        field_groups = self._get_field_groups()

        # Collect all text sources with their field paths
        text_sources = self._extract_text_sources(product)

        # Collect all matches (may have duplicates)
        all_matches = []

        for rule_key, rule in rules.items():
            if rule_key.startswith('_'):
                continue
            if not isinstance(rule, dict):
                continue
            if 'positive_patterns' not in rule:
                continue

            # Scan all fields - scope validation happens in _check_claim_with_validation
            for source_field, text in text_sources:
                if not text or len(text.strip()) < 3:
                    continue

                # For 'any' scope, scan all fields
                # For 'product_level_only', still scan all but let validation catch violations
                evidence = self._check_claim_with_validation(
                    text, source_field, rule, field_groups
                )
                if evidence:
                    # Add context snippet for audit readability
                    evidence['context_snippet'] = self._get_context_snippet(
                        text, evidence.get('matched_text', ''), context_chars=80
                    )
                    all_matches.append(evidence)

        # Deduplicate by dedupe_key, keeping the best evidence
        return self._deduplicate_evidence(all_matches)

    def _extract_text_sources(self, product: Dict) -> List[Tuple[str, str]]:
        """
        Extract all text sources from product with their field paths.

        Returns list of (field_path, text) tuples for field-by-field scanning.
        """
        sources = []

        # Product-level fields (for scope validation)
        # statements - list of dicts with 'notes' or 'text'
        for i, stmt in enumerate(product.get('statements', [])):
            if isinstance(stmt, str):
                sources.append((f'statements[{i}]', stmt))
            elif isinstance(stmt, dict):
                notes = stmt.get('notes', '') or stmt.get('text', '') or ''
                stmt_type = stmt.get('type', '')
                if notes:
                    sources.append((f'statements[{i}].notes', notes))
                if stmt_type:
                    sources.append((f'statements[{i}].type', stmt_type))

        # qualityFeatures - list of strings or dicts
        for i, qf in enumerate(product.get('qualityFeatures', [])):
            if isinstance(qf, str):
                sources.append((f'qualityFeatures[{i}]', qf))
            elif isinstance(qf, dict):
                text = qf.get('text', '') or qf.get('name', '') or qf.get('notes', '') or ''
                if text:
                    sources.append((f'qualityFeatures[{i}]', text))

        # certifications - list of strings or dicts
        for i, cert in enumerate(product.get('certifications', [])):
            if isinstance(cert, str):
                sources.append((f'certifications[{i}]', cert))
            elif isinstance(cert, dict):
                text = cert.get('text', '') or cert.get('name', '') or ''
                if text:
                    sources.append((f'certifications[{i}]', text))

        # claims - list of dicts with langualCodeDescription
        for i, claim in enumerate(product.get('claims', [])):
            if isinstance(claim, str):
                sources.append((f'claims[{i}]', claim))
            elif isinstance(claim, dict):
                text = claim.get('text', '') or claim.get('langualCodeDescription', '') or claim.get('notes', '') or ''
                if text:
                    sources.append((f'claims[{i}]', text))

        # labelText - string or nested dict
        label_text = product.get('labelText', '')
        if isinstance(label_text, str) and label_text:
            sources.append(('labelText', label_text))
        elif isinstance(label_text, dict):
            raw = label_text.get('raw', '')
            if raw:
                sources.append(('labelText.raw', raw))
            parsed = label_text.get('parsed', {})
            if isinstance(parsed, dict):
                for key, val in parsed.items():
                    if isinstance(val, str) and val:
                        sources.append((f'labelText.parsed.{key}', val))
                    elif isinstance(val, list):
                        for j, item in enumerate(val):
                            if isinstance(item, str) and item:
                                sources.append((f'labelText.parsed.{key}[{j}]', item))

        # fullName and brandName (product-level)
        full_name = product.get('fullName', '')
        if full_name:
            sources.append(('fullName', full_name))
        brand_name = product.get('brandName', '')
        if brand_name:
            sources.append(('brandName', brand_name))

        # Ingredient-level fields (for 'any' scope rules)
        for i, ing in enumerate(product.get('activeIngredients', [])):
            notes = ing.get('notes', '')
            if notes:
                sources.append((f'activeIngredients[{i}].notes', notes))

        for i, ing in enumerate(product.get('inactiveIngredients', [])):
            notes = ing.get('notes', '') or ing.get('name', '') or ''
            if notes:
                sources.append((f'inactiveIngredients[{i}]', notes))

        # otherIngredients - often a string
        other_ing = product.get('otherIngredients', '')
        if isinstance(other_ing, str) and other_ing:
            sources.append(('otherIngredients', other_ing))
        elif isinstance(other_ing, list):
            for i, oi in enumerate(other_ing):
                if isinstance(oi, str) and oi:
                    sources.append((f'otherIngredients[{i}]', oi))
                elif isinstance(oi, dict):
                    text = oi.get('text', '') or oi.get('name', '') or ''
                    if text:
                        sources.append((f'otherIngredients[{i}]', text))

        return sources

    def _get_context_snippet(self, full_text: str, matched_text: str, context_chars: int = 80) -> str:
        """
        Extract context snippet around matched text for audit readability.

        Returns matched text with ±context_chars of surrounding text.
        """
        if not matched_text or not full_text:
            return ''

        try:
            idx = full_text.lower().find(matched_text.lower())
            if idx == -1:
                return matched_text

            start = max(0, idx - context_chars)
            end = min(len(full_text), idx + len(matched_text) + context_chars)

            snippet = full_text[start:end]

            # Add ellipsis if truncated
            if start > 0:
                snippet = '...' + snippet
            if end < len(full_text):
                snippet = snippet + '...'

            return snippet.replace('\n', ' ').replace('\t', ' ')
        except Exception:
            return matched_text

    def _deduplicate_evidence(self, evidence_list: List[Dict]) -> List[Dict]:
        """
        Deduplicate evidence objects by dedupe_key, keeping the best evidence.

        Priority order (best first):
        1. Strong evidence > Medium > Weak
        2. Non-negated > Negated
        3. Non-scope-violation > Scope violation
        4. score_eligible=True > False
        """
        if not evidence_list:
            return []

        # Group by dedupe_key
        by_key = {}
        for ev in evidence_list:
            key = ev.get('dedupe_key') or ev.get('rule_id', 'unknown')
            if key not in by_key:
                by_key[key] = []
            by_key[key].append(ev)

        # For each group, pick the best evidence
        strength_rank = {'strong': 3, 'medium': 2, 'weak': 1}
        deduplicated = []

        for key, candidates in by_key.items():
            # Sort by quality (best first)
            def sort_key(ev):
                return (
                    strength_rank.get(ev.get('evidence_strength', 'weak'), 0),  # Higher is better
                    0 if ev.get('negation', {}).get('negated') else 1,  # Non-negated better
                    0 if ev.get('scope_violation') else 1,  # Non-violation better
                    1 if ev.get('score_eligible') else 0,  # Eligible better
                )

            candidates.sort(key=sort_key, reverse=True)
            best = candidates[0]

            # Add duplicate count for audit
            if len(candidates) > 1:
                best['duplicate_count'] = len(candidates)
                best['other_sources'] = [c.get('source_field') for c in candidates[1:]][:5]

            deduplicated.append(best)

        return deduplicated

    def _collect_certification_data(self, product: Dict) -> Dict:
        """
        Collect certification data for scoring Section B3.

        ENHANCED (v1.0.0): Now uses cert_claim_rules.json for evidence-based detection.
        - Returns evidence objects with full audit trail
        - Validates claims with negative patterns
        - Enforces scope rules (product-level only)
        - Scoring decides points based on evidence_strength and score_eligible

        Also derives safety verification flags from certifications:
        - purity_verified: Product tested by program that tests for contaminants
        - heavy_metal_tested: Product tested by program that tests for heavy metals
        - label_accuracy_verified: Product tested by program that verifies label claims
        """
        all_text = self._get_all_product_text(product)

        # LEGACY: Collect using old patterns for backward compatibility
        third_party = self._collect_third_party_certs(all_text)
        gmp = self._collect_gmp_data(all_text)
        traceability = self._collect_traceability_data(all_text)

        # ENHANCED (v1.0.0): Collect using rules database with evidence objects
        # These provide full audit trail for hardened scoring
        third_party_evidence = self._collect_claims_from_rules_db(product, 'third_party_programs')
        gmp_evidence = self._collect_claims_from_rules_db(product, 'gmp_certifications')
        batch_evidence = self._collect_claims_from_rules_db(product, 'batch_traceability')

        # Derive safety flags from certifications
        # These programs test for heavy metals, contaminants, and/or label accuracy
        safety_flags = self._derive_safety_flags(third_party, product)

        return {
            # Legacy format for backward compatibility
            "third_party_programs": third_party,
            "gmp": gmp,
            "batch_traceability": traceability,
            # Safety verification flags for app display
            "purity_verified": safety_flags["purity_verified"],
            "heavy_metal_tested": safety_flags["heavy_metal_tested"],
            "label_accuracy_verified": safety_flags["label_accuracy_verified"],
            "category_contamination_risk": safety_flags["category_contamination_risk"],
            # ENHANCED: Evidence-based detection (for hardened scoring)
            "evidence_based": {
                "third_party_programs": third_party_evidence,
                "gmp_certifications": gmp_evidence,
                "batch_traceability": batch_evidence,
                "rules_db_version": self.reference_versions.get('cert_claim_rules', {}).get('version', 'unknown')
            }
        }

    def _collect_third_party_certs(self, text: str) -> List[Dict]:
        """Collect third-party testing certifications"""
        certs = []

        # Priority certification patterns (named programs only)
        cert_checks = [
            ("NSF Sport", r'\bNSF\b.*certified\s*for\s*sport\b|\bNSF[-\s]?sport\b'),
            ("NSF Certified", r'\bNSF\b.*(certified|certification)\b(?!.*sport)|\bNSF/ANSI\s*173\b'),
            ("USP Verified", r'\bUSP\b.*(Verified|Verification\s*Program)\b'),
            ("ConsumerLab", r'\bConsumerLab\b.*(Approved|Seal)\b'),
            ("Informed Sport", r'\bInformed[-\s]?Sport\b'),
            ("Informed Choice", r'\bInformed[-\s]?Choice\b'),
            ("BSCG", r'\bBSCG\b.*(Certified|Drug\s*Free)\b'),
            ("IFOS", r'\bIFOS\b|\bInternational\s*Fish\s*Oil\s*Standards\b')
        ]

        for cert_name, pattern in cert_checks:
            if re.search(pattern, text, re.I):
                certs.append({
                    "name": cert_name,
                    "verified": True
                })

        # Check for generic "third-party tested" (doesn't count for points)
        generic_third_party = bool(re.search(r'\b(third[-\s]?party|3rd[-\s]?party)\s*(tested|verified)\b', text, re.I))

        return {
            "programs": certs,
            "count": len(certs),
            "has_generic_claim_only": generic_third_party and len(certs) == 0
        }

    def _collect_gmp_data(self, text: str) -> Dict:
        """Collect GMP certification data"""
        gmp_found = bool(self.compiled_patterns['gmp'].search(text))
        nsf_gmp = bool(self.compiled_patterns['nsf_gmp'].search(text))
        fda_registered = bool(self.compiled_patterns['fda_registered'].search(text))

        return {
            "claimed": gmp_found or nsf_gmp or fda_registered,
            "nsf_gmp": nsf_gmp,
            "fda_registered": fda_registered,
            "text_matched": "NSF GMP" if nsf_gmp else "FDA Registered" if fda_registered else "GMP" if gmp_found else ""
        }

    def _collect_traceability_data(self, text: str) -> Dict:
        """Collect batch traceability data"""
        has_coa = bool(self.compiled_patterns['coa'].search(text))
        has_qr = bool(self.compiled_patterns['qr_code'].search(text))
        has_batch_lookup = bool(self.compiled_patterns['batch_lookup'].search(text))

        return {
            "has_coa": has_coa,
            "has_qr_code": has_qr,
            "has_batch_lookup": has_batch_lookup,
            "qualifies": has_coa or has_qr or has_batch_lookup
        }

    # Programs that test for heavy metals (lead, arsenic, mercury, cadmium)
    HEAVY_METAL_TESTING_PROGRAMS = [
        "NSF Sport", "NSF Certified", "USP Verified", "ConsumerLab", "IFOS"
    ]

    # Programs that verify label accuracy (ingredient identity & potency)
    LABEL_ACCURACY_PROGRAMS = [
        "USP Verified", "ConsumerLab", "NSF Certified"
    ]

    # Programs that test for purity/contaminants (pesticides, microbes, etc.)
    PURITY_TESTING_PROGRAMS = [
        "NSF Sport", "NSF Certified", "USP Verified", "ConsumerLab",
        "IFOS", "Informed Sport", "Informed Choice", "BSCG"
    ]

    # Categories with elevated contamination risk (based on ConsumerLab/FDA data)
    HIGH_CONTAMINATION_RISK_CATEGORIES = {
        "protein_powder": {
            "severity_level": "elevated",
            "concerns": ["heavy_metals", "bpa"],
            "note": "Independent tests found lead/arsenic in many protein supplements"
        },
        "greens_superfood": {
            "severity_level": "elevated",
            "concerns": ["heavy_metals", "pesticides"],
            "note": "Plant-based concentrates may accumulate soil contaminants"
        },
        "ayurvedic_herbal": {
            "severity_level": "high",
            "concerns": ["heavy_metals", "adulterants"],
            "note": "Traditional preparations sometimes contain lead/mercury"
        },
        "weight_loss": {
            "severity_level": "high",
            "concerns": ["adulterants", "stimulants"],
            "note": "FDA has found hidden drugs in weight loss supplements"
        },
        "sexual_enhancement": {
            "severity_level": "high",
            "concerns": ["adulterants", "prescription_drugs"],
            "note": "FDA frequently finds hidden Viagra/Cialis analogs"
        },
        "sports_performance": {
            "severity_level": "moderate",
            "concerns": ["banned_substances", "stimulants"],
            "note": "May contain substances banned by WADA"
        }
    }

    def _derive_safety_flags(self, third_party: Dict, product: Dict) -> Dict:
        """
        Derive safety verification flags from certification programs.

        These flags indicate whether the product has been tested by programs
        that verify specific safety criteria:
        - purity_verified: Tested for contaminants (pesticides, microbes, etc.)
        - heavy_metal_tested: Tested for heavy metals (Pb, As, Hg, Cd)
        - label_accuracy_verified: Ingredient identity and potency verified

        Also assesses category-based contamination risk.
        """
        programs = third_party.get("programs", [])
        program_names = [p.get("name", "") for p in programs]

        # Check if any program covers each safety criterion
        purity_verified = any(
            name in self.PURITY_TESTING_PROGRAMS for name in program_names
        )
        heavy_metal_tested = any(
            name in self.HEAVY_METAL_TESTING_PROGRAMS for name in program_names
        )
        label_accuracy_verified = any(
            name in self.LABEL_ACCURACY_PROGRAMS for name in program_names
        )

        # Assess category-based contamination risk
        category_risk = self._assess_category_contamination_risk(product)

        return {
            "purity_verified": purity_verified,
            "heavy_metal_tested": heavy_metal_tested,
            "label_accuracy_verified": label_accuracy_verified,
            "verifying_programs": program_names if program_names else [],
            "category_contamination_risk": category_risk
        }

    def _assess_category_contamination_risk(self, product: Dict) -> Dict:
        """
        Assess contamination risk based on product category.

        Returns risk level and specific concerns for high-risk categories.
        """
        product_name = (product.get("product_name", "") or product.get("fullName", "")).lower()
        # Normalize targetGroups - can be list of strings or dicts
        raw_groups = product.get("targetGroups", [])
        normalized_groups = []
        for tg in raw_groups:
            if isinstance(tg, str):
                normalized_groups.append(tg)
            elif isinstance(tg, dict):
                normalized_groups.append(tg.get('text', '') or tg.get('name', '') or '')
        target_groups = " ".join(normalized_groups).lower()
        all_text = f"{product_name} {target_groups}"

        # Check for high-risk category indicators
        risk_indicators = {
            "protein_powder": ["protein powder", "whey protein", "casein protein",
                              "plant protein", "pea protein", "protein isolate"],
            "greens_superfood": ["greens powder", "superfood", "green blend",
                                "spirulina", "chlorella", "barley grass"],
            "ayurvedic_herbal": ["ayurvedic", "ayurveda", "ashwagandha", "triphala",
                                "guggul", "brahmi", "shatavari"],
            "weight_loss": ["weight loss", "fat burner", "thermogenic", "metabolism",
                           "appetite suppressant", "diet pill"],
            "sexual_enhancement": ["sexual enhancement", "male enhancement", "libido",
                                  "testosterone booster", "ed support"],
            "sports_performance": ["pre-workout", "pre workout", "bcaa", "creatine",
                                  "sports performance", "athletic"]
        }

        detected_category = None
        for category, keywords in risk_indicators.items():
            if any(keyword in all_text for keyword in keywords):
                detected_category = category
                break

        if detected_category and detected_category in self.HIGH_CONTAMINATION_RISK_CATEGORIES:
            risk_info = self.HIGH_CONTAMINATION_RISK_CATEGORIES[detected_category]
            return {
                "has_elevated_risk": True,
                "category": detected_category,
                "severity_level": risk_info["severity_level"],
                "concerns": risk_info["concerns"],
                "note": risk_info["note"]
            }

        return {
            "has_elevated_risk": False,
            "category": None,
            "severity_level": "standard",
            "concerns": [],
            "note": None
        }

    def _collect_proprietary_data(self, product: Dict) -> Dict:
        """
        Collect proprietary blend data for scoring Section B4.

        UNION-OF-EVIDENCE CONTRACT:
        Enrichment proprietary_data MUST be union of:
        1. Detector evidence (pattern-based from ProprietaryBlendDetector)
        2. Cleaning evidence (indicator-based from proprietaryBlend flags)
        3. Deduplicated to prevent double-penalizing

        This ensures blends flagged during cleaning are NEVER silently dropped
        when the detector returns empty results.

        Merge Precedence Rules (when same blend from both sources):
        - disclosure_level: prefer detector (more accurate analysis)
        - blend_total_amount: prefer detector if parsed, else cleaning
        - blend_ingredient_count: prefer detector if available
        - blend_name: prefer cleaning (better for UI display)
        """
        active_ingredients = product.get('activeIngredients', [])
        inactive_ingredients = product.get('inactiveIngredients', [])
        total_active = len(active_ingredients)

        # Step 1: Collect detector blends (pattern-based)
        detector_blends = []
        if self.blend_detector:
            try:
                result = self.blend_detector.analyze_product(product)
                for blend in result.blends_detected:
                    detector_blends.append({
                        "name": blend.blend_name,
                        "disclosure_level": blend.disclosure_level,
                        "nested_count": blend.blend_ingredient_count,
                        "total_weight": blend.blend_total_amount,
                        "unit": blend.blend_total_unit or "",
                        "sources": ["detector"],
                        "evidence": {
                            "blend_id": blend.blend_id,
                            "matched_text": blend.matched_text,
                            "source_field": blend.source_field,
                            "risk_category": blend.risk_category,
                            "severity_level": blend.severity_level,
                            "amounts_present": blend.blend_amounts_present,
                            "ingredients_with_amounts": blend.ingredients_with_amounts,
                            "ingredients_without_amounts": blend.ingredients_without_amounts,
                            "penalty_applicable": blend.penalty_applicable,
                            "penalty_reason": blend.penalty_reason
                        }
                    })
            except Exception as e:
                self.logger.warning(
                    f"ProprietaryBlendDetector failed: {e}"
                )

        # Step 2: Collect cleaning blends (indicator-based from proprietaryBlend flags)
        # Nested proprietary children should roll up to their parent blend to avoid
        # inflating B5 penalties (e.g., each enzyme row being treated as a separate blend).
        cleaning_blends = []
        nested_parent_groups = {}
        for ingredient in active_ingredients + inactive_ingredients:
            is_blend = (
                ingredient.get('proprietaryBlend', False) or
                ingredient.get('isProprietaryBlend', False)
            )
            if is_blend:
                disclosure = ingredient.get('disclosureLevel', 'none')
                nested = ingredient.get('nestedIngredients', [])
                is_nested = bool(ingredient.get('isNestedIngredient', False))
                parent_blend = (ingredient.get('parentBlend', '') or '').strip()
                quantity = ingredient.get('quantity', 0) or 0
                unit = ingredient.get('unit', '') or ''

                # Roll nested rows under parent blend key when available.
                if is_nested and parent_blend:
                    group_key = (parent_blend.lower(), disclosure)
                    group = nested_parent_groups.get(group_key)
                    if not group:
                        group = {
                            "name": parent_blend,
                            "disclosure_level": disclosure,
                            "nested_count": 0,
                            "total_weight": 0.0,
                            "unit": "",
                            "sources": ["cleaning"],
                            "evidence": None,
                            "_child_names": set()
                        }
                        nested_parent_groups[group_key] = group

                    child_name = (ingredient.get('name', '') or '').strip()
                    if child_name:
                        group["_child_names"].add(child_name.lower())
                    # Preserve any measured parent quantity if it exists on nested rows.
                    if isinstance(quantity, (int, float)) and quantity > group["total_weight"]:
                        group["total_weight"] = float(quantity)
                        group["unit"] = unit
                    continue

                cleaning_blends.append({
                    "name": ingredient.get('name', ''),
                    "disclosure_level": disclosure,
                    "nested_count": len(nested),
                    "total_weight": quantity,
                    "unit": unit,
                    "sources": ["cleaning"],
                    "evidence": None
                })

        for group in nested_parent_groups.values():
            group["nested_count"] = max(group["nested_count"], len(group.pop("_child_names", set())))
            cleaning_blends.append(group)

        # Step 3: Merge and dedupe using union-of-evidence
        merged_blends = self._merge_blend_evidence(detector_blends, cleaning_blends)

        # Step 4: Compute counts and metrics for transparency
        detector_count = len(detector_blends)
        cleaning_count = len(cleaning_blends)
        raw_total = detector_count + cleaning_count  # Before deduplication
        merged_count = len(merged_blends)  # After deduplication

        # Deduplication rate: how many duplicates were removed
        # This is expected due to detector finding same blend from multiple sources
        dedup_count = raw_total - merged_count
        dedup_rate = dedup_count / raw_total if raw_total > 0 else 0.0

        # Blend loss rate: cleaning blends that didn't make it to merged
        # This should be 0% after the union-of-evidence fix
        blend_loss_rate = 0.0
        if cleaning_count > 0:
            cleaning_names = {b["name"].lower().strip() for b in cleaning_blends}
            merged_names = {b["name"].lower().strip() for b in merged_blends}
            lost_names = cleaning_names - merged_names
            blend_loss_rate = len(lost_names) / cleaning_count if cleaning_count > 0 else 0.0

        return {
            "has_proprietary_blends": len(merged_blends) > 0,
            "blends": merged_blends,
            "blend_count": len(merged_blends),
            "total_active_ingredients": total_active,
            # Provenance tracking for auditing (Issue #1 & #2 from audit)
            "blend_sources": {
                # Raw counts (before deduplication)
                "detector_raw_count": detector_count,
                "cleaning_raw_count": cleaning_count,
                "raw_total": raw_total,
                # After deduplication
                "merged_count": merged_count,
                "dedup_count": dedup_count,
                "dedup_rate": round(dedup_rate, 4),
                # Quality metric (should be 0)
                "blend_loss_rate": round(blend_loss_rate, 4)
            }
        }

    def _merge_blend_evidence(
        self,
        detector_blends: List[Dict],
        cleaning_blends: List[Dict]
    ) -> List[Dict]:
        """
        Merge detector and cleaning blend evidence with deduplication.

        Dedupe key: (normalized_name, 5mg_bucket, nested_count)
        This matches the dedupe logic in B4 scoring.

        Merge Precedence:
        - disclosure_level: prefer detector (more accurate)
        - blend_total_amount: prefer detector if parsed
        - blend_ingredient_count: prefer detector if available
        - blend_name: prefer cleaning (better UI display, label-facing)
        - detector_group: preserve detector's classification category
        - sources: union of both

        AUDIT CLARITY:
        - `name`: Label-facing blend name (from cleaning when available)
        - `detector_group`: Detector's classification (e.g., "General Proprietary Blends")
        This preserves both the human-readable label name and the detector category.
        """
        merged = {}

        def dedupe_key(blend: Dict) -> tuple:
            """Generate deduplication key matching B4 scoring logic."""
            name = (blend.get("name") or "").lower().strip()
            mg = blend.get("total_weight")
            # 5mg bucket to tolerate parsing variance
            mg_bucket = int(round(mg / 5.0) * 5) if mg and mg > 0 else None
            nested = blend.get("nested_count", 0)
            return (name, mg_bucket, nested)

        # Add detector blends first (higher precedence for most fields)
        for blend in detector_blends:
            key = dedupe_key(blend)
            blend_copy = blend.copy()
            # Store detector's classification as detector_group for audit
            blend_copy["detector_group"] = blend.get("name")
            merged[key] = blend_copy

        # Merge cleaning blends (may add new or enrich existing)
        for cleaning_blend in cleaning_blends:
            key = dedupe_key(cleaning_blend)

            if key in merged:
                # Blend exists from detector - merge sources and prefer cleaning name
                existing = merged[key]
                # Union sources
                existing_sources = set(existing.get("sources", []))
                existing_sources.add("cleaning")
                existing["sources"] = list(existing_sources)
                # Prefer cleaning name for UI (label-facing, more specific)
                # Keep detector_group as the classifier category
                if cleaning_blend.get("name"):
                    existing["name"] = cleaning_blend["name"]
            else:
                # New blend from cleaning only - no detector_group
                blend_copy = cleaning_blend.copy()
                blend_copy["detector_group"] = None  # Not detected by pattern DB
                merged[key] = blend_copy

        return list(merged.values())

    def _extract_strain_ids_from_product(self, product: Dict) -> List[str]:
        """Extract probiotic strain IDs from product text and ingredient fields."""
        strain_id_pattern = re.compile(
            r'(atcc\s*(?:pta\s*)?[\d]+|dsm\s*[\d]+|ncfm|gg|k12|m18|bb-?12|bb536|hn019|bi-?07|de111|299v)',
            re.IGNORECASE
        )
        texts = [self._get_all_product_text(product)]
        for ing in product.get('activeIngredients', []) + product.get('inactiveIngredients', []):
            texts.append(ing.get('name', '') or '')
            texts.append(ing.get('standardName', '') or '')
            texts.append(ing.get('notes', '') or '')
            texts.append(ing.get('harvestMethod', '') or '')
        combined = ' '.join(filter(None, texts))
        matches = strain_id_pattern.findall(combined)
        deduped = sorted({re.sub(r'\s+', ' ', m.strip()) for m in matches if m})
        return deduped

    def _collect_product_signals(
        self,
        product: Dict,
        ingredient_quality_data: Dict,
        certification_data: Dict,
        formulation_data: Dict,
        probiotic_data: Dict
    ) -> Dict:
        """Collect product-level signals for auditing and UI display."""
        coverage = {
            "total_records_seen": ingredient_quality_data.get("total_records_seen", 0),
            "total_ingredients_evaluated": ingredient_quality_data.get("total_ingredients_evaluated", 0),
            "unevaluated_records": ingredient_quality_data.get("unevaluated_records", 0),
            "pattern_match_wins_count": ingredient_quality_data.get("pattern_match_wins_count", 0),
            "contains_match_wins_count": ingredient_quality_data.get("contains_match_wins_count", 0),
            "parent_fallback_count": ingredient_quality_data.get("parent_fallback_count", 0)
        }

        cert_types = set()
        third_party_programs = certification_data.get("third_party_programs", {}).get("programs", [])
        for program in third_party_programs:
            name = program.get("name")
            if name:
                cert_types.add(name)

        gmp = certification_data.get("gmp", {})
        if gmp.get("claimed"):
            cert_types.add(gmp.get("text_matched") or "GMP")

        batch = certification_data.get("batch_traceability", {})
        if batch.get("has_coa"):
            cert_types.add("COA")
        if batch.get("has_qr_code"):
            cert_types.add("QR Code")
        if batch.get("has_batch_lookup"):
            cert_types.add("Batch Lookup")

        label_text = self._get_all_product_text(product)
        trademark_present = bool(re.search(r'[™®©]', label_text))
        standardized_botanicals = formulation_data.get("standardized_botanicals", [])
        strain_ids = self._extract_strain_ids_from_product(product)

        label_disclosure_signals = {
            "standardized_botanicals_count": len(standardized_botanicals),
            "standardized_botanicals": standardized_botanicals,
            "strain_ids": strain_ids,
            "strain_id_count": len(strain_ids),
            "total_strain_count": probiotic_data.get("total_strain_count", 0),
            "clinical_strain_count": probiotic_data.get("clinical_strain_count", 0),
            "has_trademarked_forms": trademark_present
        }

        return {
            "coverage": coverage,
            "certificates_present": bool(cert_types),
            "certificate_types": sorted(cert_types),
            "label_disclosure_signals": label_disclosure_signals
        }

    def _project_scoring_fields(self, enriched: Dict) -> None:
        """
        Project nested enrichment outputs into stable top-level fields used by
        scoring and downstream consumers.
        """
        delivery_data = enriched.get("delivery_data", {}) or {}
        absorption_data = enriched.get("absorption_data", {}) or {}
        formulation_data = enriched.get("formulation_data", {}) or {}
        contaminant_data = enriched.get("contaminant_data", {}) or {}
        compliance_data = enriched.get("compliance_data", {}) or {}
        certification_data = enriched.get("certification_data", {}) or {}
        proprietary_data = enriched.get("proprietary_data", {}) or {}
        evidence_data = enriched.get("evidence_data", {}) or {}
        manufacturer_data = enriched.get("manufacturer_data", {}) or {}
        ingredient_quality_data = enriched.get("ingredient_quality_data", {}) or {}

        enriched["delivery_tier"] = delivery_data.get("highest_tier")
        enriched["absorption_enhancer_paired"] = bool(
            absorption_data.get("qualifies_for_bonus", False)
        )

        organic_data = formulation_data.get("organic", {})
        if isinstance(organic_data, dict):
            is_certified_organic = bool(
                organic_data.get("usda_verified")
                or (organic_data.get("claimed") and not organic_data.get("exclusion_matched"))
            )
        else:
            is_certified_organic = bool(organic_data)
        enriched["is_certified_organic"] = is_certified_organic

        standardized_botanicals = formulation_data.get("standardized_botanicals", []) or []
        enriched["has_standardized_botanical"] = any(
            bool(item.get("meets_threshold"))
            for item in standardized_botanicals
            if isinstance(item, dict)
        )

        synergy_clusters = formulation_data.get("synergy_clusters", []) or []
        synergy_cluster_qualified = False
        for cluster in synergy_clusters:
            if not isinstance(cluster, dict):
                continue
            matched_ingredients = cluster.get("matched_ingredients", []) or []
            match_count = cluster.get("match_count", len(matched_ingredients)) or 0
            try:
                match_count = int(match_count)
            except (TypeError, ValueError):
                match_count = 0

            if match_count < 2:
                continue

            checkable = []
            for item in matched_ingredients:
                if not isinstance(item, dict):
                    continue
                min_dose = item.get("min_effective_dose", 0) or 0
                try:
                    min_dose = float(min_dose)
                except (TypeError, ValueError):
                    min_dose = 0
                if min_dose > 0:
                    checkable.append(item)

            if not checkable:
                synergy_cluster_qualified = True
                break

            dosed = [item for item in checkable if bool(item.get("meets_minimum", False))]
            required = (len(checkable) + 1) // 2
            if len(dosed) >= required:
                synergy_cluster_qualified = True
                break

        enriched["synergy_cluster_qualified"] = synergy_cluster_qualified

        harmful_additives = (
            contaminant_data.get("harmful_additives", {}).get("additives", []) or []
        )
        allergen_hits = (
            contaminant_data.get("allergens", {}).get("allergens", []) or []
        )
        enriched["harmful_additives"] = harmful_additives
        enriched["allergen_hits"] = allergen_hits

        conflicts = [
            str(x).lower()
            for x in (compliance_data.get("conflicts", []) or [])
        ]
        has_may_contain = bool(compliance_data.get("has_may_contain_warning", False))
        allergen_claims = compliance_data.get("allergen_free_claims", []) or []

        allergen_contradiction = has_may_contain or any(
            any(term in c for term in ["allergen", "dairy", "soy", "egg", "gluten", "wheat", "shellfish", "nut"])
            for c in conflicts
        )
        gluten_contradiction = has_may_contain or any(
            ("gluten" in c) or ("wheat" in c) for c in conflicts
        )
        vegan_contradiction = any(
            any(term in c for term in ["gelatin", "bovine", "porcine", "vegan", "vegetarian"])
            for c in conflicts
        )

        enriched["claim_allergen_free_validated"] = bool(allergen_claims) and not allergen_contradiction and len(allergen_hits) == 0
        enriched["claim_gluten_free_validated"] = bool(compliance_data.get("gluten_free", False)) and not gluten_contradiction
        enriched["claim_vegan_validated"] = bool(
            compliance_data.get("vegan", False) or compliance_data.get("vegetarian", False)
        ) and not vegan_contradiction

        third_party_programs = certification_data.get("third_party_programs", {}).get("programs", []) or []
        named_programs = []
        for program in third_party_programs:
            if isinstance(program, dict):
                name = program.get("name")
            else:
                name = program
            if name:
                named_programs.append(name)
        enriched["named_cert_programs"] = named_programs

        gmp_data = certification_data.get("gmp", {}) or {}
        if bool(gmp_data.get("nsf_gmp") or gmp_data.get("claimed")):
            gmp_level = "certified"
        elif bool(gmp_data.get("fda_registered")):
            gmp_level = "fda_registered"
        else:
            gmp_level = None
        enriched["gmp_level"] = gmp_level

        batch_data = certification_data.get("batch_traceability", {}) or {}
        enriched["has_coa"] = bool(batch_data.get("has_coa", False))
        enriched["has_batch_lookup"] = bool(
            batch_data.get("has_batch_lookup", False) or batch_data.get("has_qr_code", False)
        )

        enriched["proprietary_blends"] = proprietary_data.get("blends", []) or []
        enriched["has_disease_claims"] = bool(
            (evidence_data.get("unsubstantiated_claims", {}) or {}).get("found", False)
        )

        top_manufacturer = manufacturer_data.get("top_manufacturer", {}) or {}
        # Trusted-manufacturer bonus is exact-match only; fuzzy hits are audit-only.
        enriched["is_trusted_manufacturer"] = bool(
            top_manufacturer.get("found", False)
            and str(top_manufacturer.get("match_type", "")).lower() == "exact"
        )

        ingredients = ingredient_quality_data.get("ingredients_scorable", []) or ingredient_quality_data.get("ingredients", []) or []
        has_missing_dose = any(
            isinstance(item, dict) and not bool(item.get("has_dose", False))
            for item in ingredients
        )
        has_hidden_blends = any(
            isinstance(blend, dict) and str(blend.get("disclosure_level", "")).lower() in {"none", "partial"}
            for blend in enriched["proprietary_blends"]
        )
        enriched["has_full_disclosure"] = (not has_missing_dose) and (not has_hidden_blends)

        bonus_features = manufacturer_data.get("bonus_features", {}) or {}
        enriched["claim_physician_formulated"] = bool(bonus_features.get("physician_formulated", False))
        enriched["has_sustainable_packaging"] = bool(bonus_features.get("sustainability_claim", False))
        enriched["manufacturing_region"] = (
            manufacturer_data.get("country_of_origin", {}) or {}
        ).get("country")

    # =========================================================================
    # SECTION C: EVIDENCE & RESEARCH DATA COLLECTORS
    # =========================================================================

    def _collect_evidence_data(self, product: Dict) -> Dict:
        """
        Collect clinical evidence data for scoring Section C.
        """
        clinical_db = self.databases.get('backed_clinical_studies', {})
        studies = clinical_db.get('backed_clinical_studies', [])

        active_ingredients = product.get('activeIngredients', [])
        matches = []

        for ingredient in active_ingredients:
            ing_name = ingredient.get('name', '')
            std_name = ingredient.get('standardName', '') or ing_name

            for study in studies:
                study_name = study.get('standard_name', '')
                study_aliases = study.get('aliases', [])

                if self._exact_match(ing_name, study_name, study_aliases) or \
                   self._exact_match(std_name, study_name, study_aliases):

                    # For brand-specific studies, check brand mention
                    study_id = study.get('id', '')
                    if study_id.startswith('BRAND_'):
                        if not self._brand_mentioned(study_name, study_aliases, product):
                            continue

                    matches.append({
                        "ingredient": ing_name,
                        "study_id": study_id,
                        "study_name": study_name,
                        "evidence_level": study.get('evidence_level', 'ingredient-human'),
                        "study_type": study.get('study_type', 'rct_single'),
                        "score_contribution": study.get('score_contribution', 'tier_3'),
                        "health_goals_supported": study.get('health_goals_supported', []),
                        "key_endpoints": study.get('key_endpoints', [])
                    })
                    break  # One match per ingredient

        # Check for unsubstantiated claims
        all_text = self._get_all_product_text(product)
        unsubstantiated = self._check_unsubstantiated_claims(all_text)

        return {
            "clinical_matches": matches,
            "match_count": len(matches),
            "unsubstantiated_claims": unsubstantiated
        }

    def _brand_mentioned(self, study_name: str, aliases: List[str], product: Dict) -> bool:
        """Check if brand is explicitly mentioned in product"""
        all_text = self._get_all_product_text(product).lower()

        terms = [study_name.lower()] + [a.lower() for a in aliases]
        return any(term in all_text for term in terms)

    def _check_unsubstantiated_claims(self, text: str) -> Dict:
        """Check for egregious unsubstantiated claims"""
        found_claims = []

        checks = [
            ('disease_claims', 'disease treatment claim', -5),
            ('miracle_claims', 'miracle/instant cure claim', -5),
            ('fda_approved', 'false FDA approval claim', -5)
        ]

        for pattern_name, claim_type, penalty in checks:
            if self.compiled_patterns[pattern_name].search(text):
                found_claims.append({
                    "type": claim_type,
                    "severity": "critical"
                })

        return {
            "found": len(found_claims) > 0,
            "claims": found_claims
        }

    # =========================================================================
    # SECTION D: BRAND TRUST DATA COLLECTORS
    # =========================================================================

    def _collect_manufacturer_data(self, product: Dict) -> Dict:
        """
        Collect manufacturer data for scoring Section D.
        """
        brand_name = product.get('brandName', '')
        contacts = product.get('contacts', [])

        # Get manufacturer from contacts
        manufacturer = ""
        for contact in contacts:
            if 'Manufacturer' in contact.get('types', []):
                manufacturer = contact.get('contactDetails', {}).get('name', '')
                break

        if not manufacturer:
            manufacturer = brand_name

        return {
            "brand_name": brand_name,
            "manufacturer": manufacturer,
            "top_manufacturer": self._check_top_manufacturer(brand_name, manufacturer),
            "violations": self._check_violations(brand_name, manufacturer),
            "country_of_origin": self._extract_country(product),
            "bonus_features": self._collect_bonus_features(product)
        }

    def _check_top_manufacturer(self, brand: str, manufacturer: str) -> Dict:
        """
        Check if manufacturer is in top manufacturers list.
        Uses exact match first, then fuzzy match as fallback.

        AC2: Now includes provenance fields for auditability:
        - product_manufacturer_raw: Original text from product
        - product_manufacturer_normalized: Normalized version
        - source_path: Which field provided the match
        """
        top_db = self.databases.get('top_manufacturers_data', {})
        top_list = top_db.get('top_manufacturers', [])

        # Determine which input was used for matching (AC2 source_path)
        brand_normalized = self._normalize_company_name(brand) if brand else ""
        mfr_normalized = self._normalize_company_name(manufacturer) if manufacturer else ""

        # PASS 1: exact match across the WHOLE list. An exact hit anywhere must
        # beat any fuzzy hit — previously a weak fuzzy match on an earlier DB
        # entry returned immediately and preempted a later exact match, making
        # the result iteration-order dependent.
        for top_mfr in top_list:
            std_name = top_mfr.get('standard_name', '')
            aliases = top_mfr.get('aliases', [])

            brand_exact = self._exact_match(brand, std_name, aliases)
            mfr_exact = self._exact_match(manufacturer, std_name, aliases)

            if brand_exact or mfr_exact:
                # Determine which input matched (AC2)
                matched_source = "brandName" if brand_exact else "manufacturer"
                matched_raw = brand if brand_exact else manufacturer
                matched_normalized = brand_normalized if brand_exact else mfr_normalized

                return {
                    "found": True,
                    "manufacturer_id": top_mfr.get('id', ''),
                    "name": std_name,
                    "match_type": "exact",
                    # AC2: Provenance fields for auditability
                    "product_manufacturer_raw": matched_raw,
                    "product_manufacturer_normalized": matched_normalized,
                    "source_path": matched_source,
                }

        # PASS 2: fuzzy fallback for variations like "Thorne" vs "Thorne
        # Research". Evaluate ALL entries (std_name AND aliases, for parity
        # with the exact pass) and keep the single best score.
        best = None  # (score, top_mfr, matched_source)
        for top_mfr in top_list:
            std_name = top_mfr.get('standard_name', '')
            aliases = top_mfr.get('aliases', [])

            for candidate in [std_name] + list(aliases):
                if not candidate:
                    continue
                brand_match, brand_score = self._fuzzy_company_match(brand, candidate)
                mfr_match, mfr_score = self._fuzzy_company_match(manufacturer, candidate)

                if brand_match and (best is None or brand_score > best[0]):
                    best = (brand_score, top_mfr, "brandName")
                if mfr_match and (best is None or mfr_score > best[0]):
                    best = (mfr_score, top_mfr, "manufacturer")

        if best is not None:
            match_conf, top_mfr, matched_source = best
            matched_raw = brand if matched_source == "brandName" else manufacturer
            matched_normalized = (
                brand_normalized if matched_source == "brandName" else mfr_normalized
            )

            return {
                "found": True,
                "manufacturer_id": top_mfr.get('id', ''),
                "name": top_mfr.get('standard_name', ''),
                "match_type": "fuzzy",
                "match_confidence": round(match_conf, 3),
                # AC2: Provenance fields for auditability
                "product_manufacturer_raw": matched_raw,
                "product_manufacturer_normalized": matched_normalized,
                "source_path": matched_source,
            }

        # AC2: Include provenance even for non-matches
        return {
            "found": False,
            "product_manufacturer_raw": manufacturer or brand,
            "product_manufacturer_normalized": mfr_normalized or brand_normalized,
            "source_path": "manufacturer" if manufacturer else "brandName",
        }

    def _check_violations(self, brand: str, manufacturer: str) -> Dict:
        """
        Check for manufacturer violations using fuzzy matching.

        Handles variations like:
        - "Healthy Directions" vs "Healthy Directions, LLC"
        - "Dr. David Williams" vs "David Williams"
        - "Natural Living" vs "Natural Living, Inc."
        """
        violations_db = self.databases.get('manufacturer_violations', {})
        violations_list = violations_db.get('manufacturer_violations', [])

        # Applying another company's violation penalty is a high-precision
        # decision: require near-certain identity (normalized-exact or a
        # same-name variation), not merely a passing fuzzy score. Weaker
        # fuzzy hits are kept as audit-only near-misses with NO deduction.
        VIOLATION_MATCH_MIN_CONFIDENCE = 0.95

        found = []
        near_misses = []
        for violation in violations_list:
            mfr_name = violation.get('manufacturer', '')
            if not mfr_name:
                continue

            # Check for match using fuzzy company name matching
            brand_match, brand_score = self._fuzzy_company_match(brand, mfr_name)
            mfr_match, mfr_score = self._fuzzy_company_match(manufacturer, mfr_name)

            if brand_match or mfr_match:
                match_score = max(
                    brand_score if brand_match else 0.0,
                    mfr_score if mfr_match else 0.0,
                )
                if match_score < VIOLATION_MATCH_MIN_CONFIDENCE:
                    near_misses.append({
                        "violation_id": violation.get('id', ''),
                        "violation_manufacturer": mfr_name,
                        "match_confidence": round(match_score, 3),
                        "reason": "below_violation_confidence_floor",
                    })
                    continue
                total_deduction_applied = violation.get('total_deduction_applied', 0.0)
                found.append({
                    "violation_id": violation.get('id', ''),
                    "violation_type": violation.get('violation_type', ''),
                    "severity_level": violation.get('severity_level', ''),
                    "date": violation.get('date', ''),
                    "total_deduction_applied": total_deduction_applied,
                    # Backward-compatible alias for legacy consumers.
                    "total_deduction": total_deduction_applied,
                    "is_resolved": violation.get('is_resolved', False),
                    "match_confidence": round(match_score, 3)
                })

        total_deduction_applied = 0.0
        for item in found:
            try:
                total_deduction_applied += float(item.get("total_deduction_applied", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue

        return {
            "found": len(found) > 0,
            "total_deduction_applied": round(total_deduction_applied, 2),
            "violations": found,
            # Audit-only: fuzzy hits below the confidence floor (no deduction).
            "near_misses": near_misses
        }

    def _extract_country(self, product: Dict) -> Dict:
        """Extract country of origin data"""
        all_text = self._get_all_product_text(product)

        made_usa = bool(self.compiled_patterns['made_usa'].search(all_text))
        made_eu = bool(self.compiled_patterns['made_eu'].search(all_text))

        # List of high-regulation countries
        high_reg = made_usa or made_eu

        country = ""
        if made_usa:
            country = "USA"
        elif made_eu:
            # Try to extract specific EU country
            eu_match = self.compiled_patterns['made_eu'].search(all_text)
            if eu_match:
                country = eu_match.group(0)

        return {
            "detected": country != "",
            "country": country,
            "high_regulation_country": high_reg
        }

    def _collect_bonus_features(self, product: Dict) -> Dict:
        """Collect bonus feature data"""
        all_text = self._get_all_product_text(product)

        physician = bool(self.compiled_patterns['physician'].search(all_text))
        sustainability = bool(self.compiled_patterns['sustainability'].search(all_text))

        # Extract sustainability text if found
        sustainability_text = ""
        if sustainability:
            match = self.compiled_patterns['sustainability'].search(all_text)
            if match:
                sustainability_text = match.group(0)

        return {
            "physician_formulated": physician,
            "sustainability_claim": sustainability,
            "sustainability_text": sustainability_text
        }

    # =========================================================================
    # PROBIOTIC-SPECIFIC DATA COLLECTOR
    # =========================================================================

    # Survivability coating keywords for probiotic scoring
    # P1.2: Enhanced with additional common phrases
    SURVIVABILITY_KEYWORDS = [
        "enteric coated", "enteric-coated", "enteric coating",
        "delayed release", "delayed-release", "dr caps", "drcaps",
        "bio-tract", "biotract", "livebac",
        "acid-resistant", "acid resistant", "acid-protected",
        "survives stomach acid", "stomach acid resistant",
        "patented delivery", "targeted release",
        "spore-based", "spore-forming", "spore forming",
        "bacillus coagulans", "bacillus subtilis",  # Inherently spore-forming
        # P1.2: Additional keywords from plan
        "protected by an outer layer", "protected by patented",
        "outer protective layer", "proprietary coating",
        "microencapsulated", "acid-resistant coating",
        "protective coating", "survives digestive tract",
        "survives gi tract", "gastric bypass",
        "protected strain", "protected probiotic"
    ]

    def _collect_probiotic_data(self, product: Dict) -> Dict:
        """
        Collect probiotic-specific data for scoring.
        - CFU count and guarantee type
        - Strain diversity
        - Clinically relevant strains
        - Prebiotic pairing
        - Survivability coating
        """
        active_ingredients = product.get('activeIngredients', [])
        all_ingredients = active_ingredients + product.get('inactiveIngredients', [])

        # Check if this is a probiotic product
        probiotic_blends = []
        total_strains = 0
        all_nested_strains = []

        for ingredient in active_ingredients:
            ing_name = ingredient.get('name', '').lower()
            std_name = ingredient.get('standardName', '').lower()
            category = ingredient.get('category', '').lower()

            # Check for probiotic indicators (including abbreviated forms and strain names)
            probiotic_terms = [
                'probiotic', 'lactobacillus', 'bifidobacterium', 'streptococcus',
                'bacillus', 'saccharomyces', 'limosilactobacillus',
                # Strain-specific terms
                'reuteri', 'rhamnosus', 'acidophilus', 'plantarum', 'casei',
                'salivarius', 'coagulans', 'prodentis', 'protectis', 'subtilis',
                # Abbreviated forms
                'l. reuteri', 'l. rhamnosus', 'l. acidophilus', 'l. plantarum',
                'b. lactis', 'b. longum', 'b. infantis', 's. salivarius',
                'b. subtilis', 'b. coagulans',
                # CFU indicators
                'cfu', 'billion cfu', 'live cultures', 'viable cells'
            ]
            is_probiotic = any(term in ing_name or term in std_name for term in probiotic_terms)
            is_probiotic = is_probiotic or 'probiotic' in category or 'bacteria' in category

            if is_probiotic:
                nested = ingredient.get('nestedIngredients', [])
                harvest = ingredient.get('harvestMethod', '') or ''
                notes = ingredient.get('notes', '') or ''

                # P1.1: Extract CFU from text AND from quantity/unit
                # Also include product statements for guarantee type (e.g., "At the time of manufacture.")
                statements_text = ' '.join([
                    s.get('notes', '') or s.get('text', '') or str(s)
                    for s in product.get('statements', [])
                    if isinstance(s, dict) or isinstance(s, str)
                ])
                cfu_text = harvest + ' ' + notes + ' ' + statements_text
                cfu_data = self._extract_cfu(cfu_text, ingredient=ingredient)

                probiotic_blends.append({
                    "name": ingredient.get('name', ''),
                    "strain_count": len(nested) if nested else 1,
                    "strains": [n.get('name', '') for n in nested] if nested else [ingredient.get('name', '')],
                    "cfu_data": cfu_data
                })

                total_strains += len(nested) if nested else 1
                all_nested_strains.extend([n.get('name', '') for n in nested] if nested else [ingredient.get('name', '')])

        if not probiotic_blends:
            return {"is_probiotic_product": False}

        # Check for clinically relevant strains
        strains_db = self.databases.get('clinically_relevant_strains', {})
        clinical_strains = strains_db.get('clinically_relevant_strains', [])

        found_clinical_strains = []
        for strain in all_nested_strains:
            for clinical in clinical_strains:
                clin_name = clinical.get('standard_name', '')
                clin_aliases = clinical.get('aliases', [])

                # Use strain-specific matching for probiotic strain names
                if self._strain_match(strain, clin_name, clin_aliases):
                    found_clinical_strains.append({
                        "strain": strain,
                        "clinical_id": clinical.get('id', ''),
                        "evidence_level": clinical.get('evidence_level', 'moderate')
                    })
                    break

        # Check for prebiotic pairing
        prebiotics_data = strains_db.get('prebiotics', {}).get('ingredients', [])
        prebiotic_found = False
        prebiotic_name = ""

        prebiotic_candidates = []
        for ing in all_ingredients:
            ing_name = ing.get('name', '')
            std_name = ing.get('standardName', '') or ing_name
            prebiotic_candidates.append((ing_name, std_name))

            # Include nested blend children so prebiotic rows inside proprietary
            # blends are not silently missed.
            for nested_ing in ing.get('nestedIngredients', []) or []:
                if not isinstance(nested_ing, dict):
                    continue
                nested_name = nested_ing.get('name', '')
                nested_std = nested_ing.get('standardName', '') or nested_name
                prebiotic_candidates.append((nested_name, nested_std))

        for ing_name, std_name in prebiotic_candidates:
            for prebiotic in prebiotics_data:
                pre_name = prebiotic.get('standard_name', '')
                pre_aliases = prebiotic.get('aliases', [])

                if self._exact_match(ing_name, pre_name, pre_aliases) or \
                   self._exact_match(std_name, pre_name, pre_aliases):
                    prebiotic_found = True
                    prebiotic_name = pre_name
                    break
            if prebiotic_found:
                break

        # Check for survivability coating
        has_survivability_coating = False
        survivability_reason = ""

        # Build text to search: product name, delivery form, harvestMethod, notes, label text
        product_name = product.get('product_name', product.get('fullName', '')).lower()
        delivery_form = product.get('deliveryForm', '').lower()
        label_text = self._get_safe_text_field(product, 'labelText').lower()

        # Combine all text sources for checking
        texts_to_check = [product_name, delivery_form, label_text]

        # Also check harvestMethod and notes from probiotic ingredients
        for blend in probiotic_blends:
            for ing in active_ingredients:
                if ing.get('name', '') == blend.get('name', ''):
                    texts_to_check.append((ing.get('harvestMethod', '') or '').lower())
                    texts_to_check.append((ing.get('notes', '') or '').lower())

        combined_text = ' '.join(texts_to_check)

        for keyword in self.SURVIVABILITY_KEYWORDS:
            if keyword in combined_text:
                has_survivability_coating = True
                survivability_reason = keyword
                break

        # Calculate aggregate CFU data from blends
        total_cfu = 0
        has_cfu = False
        guarantee_type = None
        total_billion_count = 0.0

        for blend in probiotic_blends:
            cfu_data = blend.get('cfu_data', {})
            if cfu_data.get('has_cfu'):
                has_cfu = True
                total_cfu += cfu_data.get('cfu_count', 0)
                total_billion_count += cfu_data.get('billion_count', 0)
            # Take first non-None guarantee_type
            if not guarantee_type and cfu_data.get('guarantee_type'):
                guarantee_type = cfu_data.get('guarantee_type')

        return {
            "is_probiotic": True,  # Top-level flag for quick filtering
            "is_probiotic_product": True,
            "probiotic_blends": probiotic_blends,
            "total_strain_count": total_strains,
            # Aggregate CFU data at top level for easy access
            "has_cfu": has_cfu,
            "total_cfu": total_cfu,
            "total_billion_count": total_billion_count,
            "guarantee_type": guarantee_type,
            # Clinical and other data
            "clinical_strains": found_clinical_strains,
            "clinical_strain_count": len(found_clinical_strains),
            "prebiotic_present": prebiotic_found,
            "prebiotic_name": prebiotic_name,
            "has_survivability_coating": has_survivability_coating,
            "survivability_reason": survivability_reason
        }

    # P1.1: CFU-equivalent units
    CFU_EQUIVALENT_UNITS = [
        'viable cell(s)', 'viable cells', 'cells', 'cfu',
        'colony forming units', 'live cells', 'active cells'
    ]

    def _extract_cfu(self, text: str, ingredient: Optional[Dict] = None) -> Dict:
        """
        Extract CFU information from text and ingredient quantity.

        P1.1: Recognizes "Viable Cell(s)" as CFU-equivalent unit.
        """
        result = {
            "has_cfu": False,
            "cfu_count": 0,
            "billion_count": 0,
            "guarantee_type": None  # 'at_manufacture' or 'at_expiration'
        }

        # P1.1: First check ingredient quantity/unit for CFU-equivalent units
        if ingredient:
            quantity = ingredient.get('quantity', 0)
            unit = (ingredient.get('unit', '') or '').lower()

            if unit and any(cfu_unit in unit for cfu_unit in self.CFU_EQUIVALENT_UNITS):
                if quantity and quantity > 0:
                    result["has_cfu"] = True
                    result["cfu_count"] = quantity
                    result["billion_count"] = quantity / 1e9

        # Also check text for CFU mentions
        if text:
            # Extract billion count from text (full word "billion")
            match = self.compiled_patterns['cfu_billion'].search(text)
            if match:
                billion_from_text = float(match.group(1))
                # Only override if ingredient didn't provide CFU or text has higher value
                if not result["has_cfu"] or billion_from_text > result["billion_count"]:
                    result["has_cfu"] = True
                    result["billion_count"] = billion_from_text
                    result["cfu_count"] = billion_from_text * 1e9

            # Also check abbreviated billion format (e.g., "1.5 B CFU")
            if not result["has_cfu"]:
                abbrev_match = self.compiled_patterns['cfu_billion_abbrev'].search(text)
                if abbrev_match:
                    billion_from_text = float(abbrev_match.group(1))
                    result["has_cfu"] = True
                    result["billion_count"] = billion_from_text
                    result["cfu_count"] = billion_from_text * 1e9

            # Also check for million CFU (e.g., "500 Million CFUs")
            if not result["has_cfu"]:
                million_match = self.compiled_patterns['cfu_million'].search(text)
                if million_match:
                    million_from_text = float(million_match.group(1))
                    result["has_cfu"] = True
                    result["billion_count"] = million_from_text / 1000  # Convert to billions
                    result["cfu_count"] = million_from_text * 1e6

            # P1.1: Enhanced guarantee type parsing
            result["guarantee_type"] = self._extract_guarantee_type(text)

        return result

    def _extract_guarantee_type(self, text: str) -> Optional[str]:
        """
        P1.1: Extract CFU guarantee type from text.

        Returns:
        - 'at_manufacture' for "At the time of manufacture"
        - 'at_expiration' for "Until expiration" / "Through expiration"
        - None if no guarantee statement found
        """
        if not text:
            return None

        text_lower = text.lower()

        # Check for expiration guarantee first (more valuable)
        if self.compiled_patterns['cfu_expiration'].search(text):
            return "at_expiration"

        # Check for manufacture guarantee
        if self.compiled_patterns['cfu_manufacture'].search(text):
            return "at_manufacture"

        # P1.1: Additional patterns for guarantee type
        expiration_patterns = [
            'until expiration', 'through expiration', 'at expiration',
            'best by date', 'until best by', 'at time of expiration'
        ]
        manufacture_patterns = [
            'at the time of manufacture', 'at time of manufacture',
            'at manufacture', 'when manufactured', 'at production'
        ]

        for pattern in expiration_patterns:
            if pattern in text_lower:
                return "at_expiration"

        for pattern in manufacture_patterns:
            if pattern in text_lower:
                return "at_manufacture"

        return None

    # =========================================================================
    # SUPPLEMENT TYPE CLASSIFIER
    # =========================================================================

    def _classify_supplement_type(self, product: Dict) -> Dict:
        """
        Classify supplement type for context-aware scoring.
        Types: single_nutrient, targeted, multivitamin, herbal_blend, probiotic, prebiotic, specialty
        """
        active_ingredients = product.get('activeIngredients', [])
        inactive_ingredients = product.get('inactiveIngredients', [])

        active_count = len(active_ingredients)
        total_count = active_count + len(inactive_ingredients)

        # Count categories AND detect probiotic ingredients by name
        category_counts = {}
        probiotic_name_count = 0
        _probiotic_terms = (
            'probiotic', 'lactobacillus', 'bifidobacterium',
            'streptococcus', 'bacillus', 'saccharomyces',
            'limosilactobacillus', 'lacticaseibacillus',
        )
        _probiotic_cats = {'probiotic', 'bacteria'}
        for ing in active_ingredients:
            cat = ing.get('category', 'other').lower()
            category_counts[cat] = category_counts.get(cat, 0) + 1
            # Name-based detection only for ingredients NOT already
            # counted by their category (avoids double-counting)
            if cat not in _probiotic_cats:
                ing_name = (
                    ing.get('name', '') or ''
                ).lower()
                std_name = (
                    ing.get('standardName', '') or ''
                ).lower()
                if any(t in ing_name or t in std_name
                       for t in _probiotic_terms):
                    probiotic_name_count += 1

        # Determine type
        supplement_type = "unknown"

        # Probiotic detection: category + ingredient names (deduplicated)
        probiotic_total = (
            category_counts.get('probiotic', 0)
            + category_counts.get('bacteria', 0)
            + probiotic_name_count
        )
        product_name_text = " ".join([
            str(product.get('product_name', '') or ''),
            str(product.get('fullName', '') or ''),
            str(product.get('bundleName', '') or ''),
        ]).lower()
        probiotic_name_signal = any(term in product_name_text for term in _probiotic_terms)

        # Probiotic — check first so single-strain products
        # are classified correctly
        if probiotic_total > 0 and (
            active_count == 1
            or probiotic_total >= active_count * 0.5
            or probiotic_name_signal
        ):
            supplement_type = "probiotic"

        # Single nutrient (non-probiotic)
        elif active_count == 1:
            supplement_type = "single_nutrient"

        # Herbal blend (>60% botanicals)
        elif category_counts.get('botanical', 0) + category_counts.get('herb', 0) > active_count * 0.6:
            supplement_type = "herbal_blend"

        # Multivitamin (6+ actives, mixed categories)
        elif active_count >= 6 and len(category_counts) >= 3:
            supplement_type = "multivitamin"

        # Targeted (2-5 actives, same category)
        elif 2 <= active_count <= 5:
            if len(category_counts) <= 2:
                supplement_type = "targeted"
            else:
                supplement_type = "specialty"

        else:
            supplement_type = "specialty"

        return {
            "type": supplement_type,
            "active_count": active_count,
            "total_count": total_count,
            "category_breakdown": category_counts
        }

    # =========================================================================
    # DIETARY SENSITIVITY DATA COLLECTOR (Sugar/Sodium for Diabetes/Hypertension)
    # =========================================================================

    # FDA/AHA Thresholds for sodium per serving (based on FDA labeling rules)
    SODIUM_THRESHOLDS = {
        "sodium_free": 5,          # <5mg = "Sodium-Free" (FDA 21 CFR 101.61)
        "very_low_sodium": 35,     # ≤35mg = "Very Low Sodium" (FDA)
        "low_sodium": 140,         # ≤140mg = "Low Sodium" (FDA/AHA recommended)
        "moderate_sodium": 400,    # >140mg but ≤400mg = moderate concern
        "high_sodium": 400         # >400mg = high concern for hypertension
    }

    # Sugar thresholds per serving (based on FDA labeling and ADA guidelines)
    SUGAR_THRESHOLDS = {
        "sugar_free": 0.5,         # <0.5g = "Sugar-Free" (FDA 21 CFR 101.60)
        "low_sugar": 3,            # ≤3g = generally acceptable for diabetics
        "moderate_sugar": 5,       # 3-5g = moderate concern
        "high_sugar": 5            # >5g = high concern for diabetics
    }

    def _collect_dietary_sensitivity_data(self, product: Dict) -> Dict:
        """
        Collect sugar and sodium data for users with dietary sensitivities.

        Designed to help users with:
        - Diabetes (Type 1, Type 2, Prediabetes) - sugar awareness
        - Hypertension (high blood pressure) - sodium awareness
        - Heart disease / cardiovascular conditions - both
        - Kidney disease - sodium and sugar awareness

        Thresholds based on:
        - FDA labeling requirements (21 CFR 101.60, 101.61)
        - American Heart Association recommendations (<1,500mg/day sodium)
        - American Diabetes Association Standards of Care 2024
        """
        nutritional_info = product.get('nutritionalInfo', {})

        # Extract sugar data
        sugar_data = self._analyze_sugar_content(product, nutritional_info)

        # Extract sodium data
        sodium_data = self._analyze_sodium_content(product, nutritional_info)

        # Check for problematic sweeteners (for diabetics)
        sweetener_data = self._check_problematic_sweeteners(product)

        # Generate user-facing warnings
        warnings = self._generate_dietary_warnings(sugar_data, sodium_data, sweetener_data)

        return {
            "sugar": sugar_data,
            "sodium": sodium_data,
            "sweeteners": sweetener_data,
            "warnings": warnings,
            # Quick boolean flags for filtering
            # P0.2: Use contains_sugar from sugar_data (considers both amount AND ingredient sources)
            "contains_sugar": sugar_data.get("contains_sugar", sugar_data["amount_g"] > 0),
            "contains_sodium": sodium_data["amount_mg"] > 0,
            # P0.2: diabetes_friendly must be false if contains_sugar is true
            "diabetes_friendly": not sugar_data.get("contains_sugar", False) and sugar_data["level"] in ["sugar_free", "low"],
            "hypertension_friendly": sodium_data["level"] in ["sodium_free", "very_low", "low"]
        }

    def _collect_serving_basis_data(self, product: Dict) -> Dict:
        """
        P0.4: Extract serving basis information for deterministic prescore
        and on-device recalculation.

        Derives from:
        - servingSizes[] → basis_count, canonical_serving_size_quantity
        - physicalState.langualCodeDescription → form_factor
        - delivery_data.systems[0].name → form_factor (fallback)
        - statements[] directions parsing → min_recommended, max_recommended
        - userGroups[] → selection_policy

        Returns:
            Dict with serving_basis and form_factor at top level
        """
        serving_sizes = product.get('servingSizes', [])
        physical_state = product.get('physicalState', {})
        statements = product.get('statements', [])
        user_groups = product.get('userGroups', [])

        # Determine form_factor from physicalState
        form_factor = None
        langual_desc = physical_state.get('langualCodeDescription', '')
        if langual_desc:
            form_factor = self._normalize_form_factor(langual_desc)

        # Fallback: try delivery_data if already collected
        if not form_factor:
            delivery_data = getattr(self, '_last_delivery_data', None)
            if delivery_data and delivery_data.get('systems'):
                form_factor = delivery_data['systems'][0].get('name', '').lower()

        # Extract basis from servingSizes
        basis_count = None
        basis_unit = None
        canonical_serving_size_qty = None
        min_servings_per_day = None
        max_servings_per_day = None
        servings_per_day_source = "default"

        if serving_sizes and isinstance(serving_sizes, list):
            # Look for adult/primary serving size
            primary_serving = self._select_canonical_serving(serving_sizes, user_groups)
            if primary_serving:
                # Handle various field names for quantity
                basis_count = (
                    primary_serving.get('quantity') or
                    primary_serving.get('servingSizeQuantity') or
                    primary_serving.get('maxQuantity') or
                    primary_serving.get('minQuantity')
                )
                # Handle various field names for unit
                basis_unit = (
                    primary_serving.get('servingSizeUnitOfMeasure') or
                    primary_serving.get('unit') or
                    ''
                )
                canonical_serving_size_qty = basis_count

                # Normalize unit using deterministic map (not heuristics)
                if basis_unit:
                    basis_unit_raw = basis_unit.lower().strip()
                    # Clean up parenthetical variants like "(ies)", "(s)", "(es)"
                    basis_unit_raw = basis_unit_raw.replace('(ies)', '')
                    basis_unit_raw = basis_unit_raw.replace('(s)', '')
                    basis_unit_raw = basis_unit_raw.replace('(es)', '')
                    # Remove any unclosed parens
                    basis_unit_raw = re.sub(r'\([^)]*$', '', basis_unit_raw).strip()
                    # Use deterministic map for canonical form
                    basis_unit = SERVING_UNIT_NORMALIZATION_MAP.get(
                        basis_unit_raw, basis_unit_raw
                    )

                # Extract daily servings if provided by DSLD
                min_servings_per_day = (
                    primary_serving.get('minDailyServings') or
                    primary_serving.get('minServingsPerDay') or
                    primary_serving.get('min_daily_servings')
                )
                max_servings_per_day = (
                    primary_serving.get('maxDailyServings') or
                    primary_serving.get('maxServingsPerDay') or
                    primary_serving.get('max_daily_servings')
                )
                if min_servings_per_day is not None or max_servings_per_day is not None:
                    servings_per_day_source = "servingSizes"

        # Parse directions for min/max recommended
        min_recommended = None
        max_recommended = None
        parsed_from_directions = False

        # First check labelText.parsed.directions
        label_text = product.get('labelText', {})
        if isinstance(label_text, dict):
            parsed = label_text.get('parsed', {})
            directions_text = parsed.get('directions', '')
            if directions_text:
                dosage_info = self._parse_dosage_from_directions(directions_text)
                if dosage_info:
                    min_recommended = dosage_info.get('min')
                    max_recommended = dosage_info.get('max')
                    parsed_from_directions = True

        # Fallback to statements if not found
        if not parsed_from_directions:
            for statement in statements:
                if isinstance(statement, dict):
                    stmt_type = statement.get('type', '').lower()
                    stmt_text = statement.get('text', '') or statement.get('notes', '')
                else:
                    stmt_type = ''
                    stmt_text = str(statement)

                if 'direction' in stmt_type or 'dosage' in stmt_type or 'take' in stmt_text.lower() or 'chew' in stmt_text.lower():
                    dosage_info = self._parse_dosage_from_directions(stmt_text)
                    if dosage_info:
                        min_recommended = dosage_info.get('min')
                        max_recommended = dosage_info.get('max')
                        parsed_from_directions = True
                        break

        if min_servings_per_day is None and max_servings_per_day is None and parsed_from_directions:
            if min_recommended is not None or max_recommended is not None:
                min_servings_per_day = min_recommended
                max_servings_per_day = max_recommended
                servings_per_day_source = "directions"

        # Determine selection policy
        selection_policy = "first_serving"
        selected_from = "servingSizes"
        basis_reason = "default"

        if user_groups:
            # Check if we have adult-specific groups
            for group in user_groups:
                if isinstance(group, dict):
                    # Handle various field names in userGroups
                    group_text = (
                        group.get('text', '') or
                        group.get('dailyValueTargetGroupName', '') or
                        group.get('langualCodeDescription', '') or
                        group.get('name', '')
                    )
                else:
                    group_text = str(group)

                if 'adult' in group_text.lower() or 'children 4' in group_text.lower():
                    selection_policy = "adult_primary"
                    selected_from = "userGroups"
                    basis_reason = "adult_default_from_userGroups"
                    break

        return {
            "serving_basis": {
                "basis_count": basis_count,
                "basis_unit": basis_unit,
                "basis_reason": basis_reason,
                "min_recommended": min_recommended,
                "max_recommended": max_recommended,
                "min_servings_per_day": min_servings_per_day,
                "max_servings_per_day": max_servings_per_day,
                "servings_per_day_source": servings_per_day_source,
                "parsed_from_directions": parsed_from_directions,
                "selection_policy": selection_policy,
                "selected_from": selected_from,
                "canonical_serving_size_quantity": canonical_serving_size_qty
            },
            "form_factor": form_factor
        }

    def _normalize_form_factor(self, langual_desc: str) -> Optional[str]:
        """Normalize langualCodeDescription to standard form_factor."""
        desc_lower = langual_desc.lower()

        form_mapping = {
            'gummy': 'gummy',
            'gummies': 'gummy',
            'chewable': 'chewable',
            'tablet': 'tablet',
            'capsule': 'capsule',
            'softgel': 'softgel',
            'liquid': 'liquid',
            'powder': 'powder',
            'drop': 'drop',
            'lozenge': 'lozenge',
            'spray': 'spray',
            'patch': 'patch'
        }

        for key, value in form_mapping.items():
            if key in desc_lower:
                return value

        return langual_desc.lower() if langual_desc else None

    def _select_canonical_serving(self, serving_sizes: List[Dict], user_groups: List) -> Optional[Dict]:
        """
        Select the canonical serving size based on user groups.

        Selection Rule (P0.3/P0.4):
        1. Choose adult/primary basis if present (often "Adults and children 4+")
        2. If no adult group, use highest serving_size_quantity
        3. Default to first serving size
        """
        if not serving_sizes:
            return None

        # If we have user groups, try to match adult serving
        if user_groups:
            for group in user_groups:
                if isinstance(group, dict):
                    group_text = (
                        group.get('text', '') or
                        group.get('dailyValueTargetGroupName', '') or
                        group.get('langualCodeDescription', '') or
                        group.get('name', '')
                    )
                else:
                    group_text = str(group)

                if 'adult' in group_text.lower():
                    # Find serving size that matches this group (highest quantity = adult)
                    # Since cleaned servingSizes don't have targetGroup, use highest quantity
                    pass  # Fall through to max quantity selection

        # Find the highest serving quantity (adult default)
        max_serving = None
        max_qty = 0
        for serving in serving_sizes:
            # Handle various field names for quantity
            qty = (
                serving.get('quantity') or
                serving.get('servingSizeQuantity') or
                serving.get('maxQuantity') or
                serving.get('minQuantity') or
                serving.get('normalizedServing') or
                0
            )
            if qty > max_qty:
                max_qty = qty
                max_serving = serving

        return max_serving or (serving_sizes[0] if serving_sizes else None)

    # Word to number mapping for dosage parsing
    WORD_TO_NUM = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
    }

    def _parse_dosage_from_directions(self, text: str) -> Optional[Dict]:
        """Parse min/max dosage from directions text.

        Handles both numeric and word-based dosages:
        - "Take 2 gummies daily"
        - "Chew two gummies daily"
        - "Adults: chew two gummies"

        For multi-group directions, extracts the adult/max dosage.
        """
        text_lower = text.lower()

        # First convert word numbers to digits for easier parsing
        for word, num in self.WORD_TO_NUM.items():
            text_lower = re.sub(rf'\b{word}\b', str(num), text_lower)

        # Look for adult dosage specifically (prioritize adult instructions)
        adult_patterns = [
            r'adults[^:]*:\s*(?:chew|take)\s+(\d+)',  # "Adults: chew 2"
            r'adults[^:]*:\s*(\d+)\s+(?:tablet|capsule|gumm|softgel)',  # "Adults: 2 gummies"
            r'(?:4|four)\s+years[^:]*:\s*(?:chew|take)\s+(\d+)',  # "4 years: chew 2"
            r'older:\s*(?:chew|take)\s+(\d+)',  # "older: chew 2"
        ]

        for pattern in adult_patterns:
            match = re.search(pattern, text_lower)
            if match:
                adult_dose = int(match.group(1))
                # Also look for child dose to get range
                child_patterns = [
                    r'children\s+(?:\d+\s+to\s+)?(\d+)[^:]*:\s*(?:chew|take)\s+(\d+)',
                    r'(\d+)\s+to\s+\d+\s+years[^:]*:\s*(?:chew|take)\s+(\d+)',
                ]
                child_dose = None
                for cp in child_patterns:
                    cm = re.search(cp, text_lower)
                    if cm:
                        child_dose = int(cm.group(2)) if len(cm.groups()) >= 2 else int(cm.group(1))
                        break

                if child_dose and child_dose < adult_dose:
                    return {"min": child_dose, "max": adult_dose}
                return {"min": adult_dose, "max": adult_dose}

        # Fallback patterns for simpler directions
        patterns = [
            r'(?:take|chew)\s+(\d+)\s*(?:to|-)\s*(\d+)',  # "take 2 to 4"
            r'(?:take|chew)\s+(\d+)',  # "take 2" or "chew 2"
            r'(\d+)\s*(?:to|-)\s*(\d+)\s+(?:tablet|capsule|gumm|softgel)',  # "2 to 4 tablets"
            r'(\d+)\s+(?:tablet|capsule|gumm|softgel)',  # "2 tablets"
        ]

        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                groups = match.groups()
                if len(groups) >= 2 and groups[1]:
                    return {"min": int(groups[0]), "max": int(groups[1])}
                elif len(groups) >= 1:
                    return {"min": int(groups[0]), "max": int(groups[0])}

        return None

    def _analyze_sugar_content(self, product: Dict, nutritional_info: Dict) -> Dict:
        """
        Analyze sugar content from nutritionalInfo and ingredients.

        P0.2 Guardrail: Internal consistency enforcement
        - If has_added_sugar == true OR amount_g > 0, then contains_sugar = true
        - Never allow sugar_free level when amount_g > 0 or has_added_sugar
        """
        sugar_info = nutritional_info.get('sugars', {})
        amount = sugar_info.get('amount', 0) or 0
        unit = sugar_info.get('unit', 'Gram(s)')

        # Normalize to grams
        amount_g = float(amount) if amount else 0.0
        if 'mg' in str(unit).lower():
            amount_g = amount_g / 1000

        # Check if sugar is in inactive ingredients FIRST (needed for guardrail)
        sugar_in_ingredients = self._find_sugar_in_ingredients(product)
        has_added_sugar = len(sugar_in_ingredients) > 0

        # P0.2 GUARDRAIL: Determine contains_sugar flag
        # If sugar_g > 0 OR has_added_sugar, then contains_sugar = true
        contains_sugar = amount_g > 0 or has_added_sugar

        # Determine level based on FDA thresholds
        # P0.2 GUARDRAIL: Never allow sugar_free when contains_sugar is true
        if amount_g < self.SUGAR_THRESHOLDS["sugar_free"] and not contains_sugar:
            level = "sugar_free"
            level_display = "Sugar-Free"
        elif amount_g <= self.SUGAR_THRESHOLDS["low_sugar"]:
            level = "low"
            level_display = "Low Sugar"
        elif amount_g <= self.SUGAR_THRESHOLDS["moderate_sugar"]:
            level = "moderate"
            level_display = "Moderate Sugar"
        else:
            level = "high"
            level_display = "High Sugar"

        return {
            "amount_g": round(amount_g, 1),
            "unit": "g",
            "level": level,
            "level_display": level_display,
            "contains_sugar": contains_sugar,
            "exceeds_diabetic_threshold": amount_g > self.SUGAR_THRESHOLDS["low_sugar"],
            "sugar_sources": sugar_in_ingredients,
            "has_added_sugar": has_added_sugar
        }

    def _analyze_sodium_content(self, product: Dict, nutritional_info: Dict) -> Dict:
        """
        Analyze sodium content from nutritionalInfo and ingredients.
        """
        sodium_info = nutritional_info.get('sodium', {})
        amount = sodium_info.get('amount', 0) or 0
        unit = sodium_info.get('unit', 'mg')

        # Normalize to mg
        amount_mg = float(amount) if amount else 0.0
        if 'g' in str(unit).lower() and 'mg' not in str(unit).lower():
            amount_mg = amount_mg * 1000

        # Determine level based on FDA/AHA thresholds
        if amount_mg < self.SODIUM_THRESHOLDS["sodium_free"]:
            level = "sodium_free"
            level_display = "Sodium-Free"
        elif amount_mg <= self.SODIUM_THRESHOLDS["very_low_sodium"]:
            level = "very_low"
            level_display = "Very Low Sodium"
        elif amount_mg <= self.SODIUM_THRESHOLDS["low_sodium"]:
            level = "low"
            level_display = "Low Sodium"
        elif amount_mg <= self.SODIUM_THRESHOLDS["moderate_sodium"]:
            level = "moderate"
            level_display = "Moderate Sodium"
        else:
            level = "high"
            level_display = "High Sodium"

        # Check for sodium-containing ingredients
        sodium_sources = self._find_sodium_in_ingredients(product)

        return {
            "amount_mg": round(amount_mg, 1),
            "unit": "mg",
            "level": level,
            "level_display": level_display,
            "exceeds_aha_threshold": amount_mg > self.SODIUM_THRESHOLDS["low_sodium"],
            "percent_daily_value": round((amount_mg / 2300) * 100, 1) if amount_mg > 0 else 0,
            "sodium_sources": sodium_sources
        }

    def _find_sugar_in_ingredients(self, product: Dict) -> List[str]:
        """Find sugar-containing ingredients in the product."""
        sugar_keywords = [
            'sugar', 'sucrose', 'glucose', 'fructose', 'dextrose', 'maltose',
            'corn syrup', 'high fructose', 'cane', 'honey', 'agave', 'molasses',
            'maple syrup', 'brown rice syrup', 'tapioca syrup', 'invert sugar'
        ]

        found = []
        all_ingredients = (
            product.get('inactiveIngredients', []) +
            product.get('activeIngredients', [])
        )

        for ing in all_ingredients:
            name = ing.get('name', '').lower()
            std_name = ing.get('standardName', '').lower()

            for keyword in sugar_keywords:
                if keyword in name or keyword in std_name:
                    found.append(ing.get('name', ''))
                    break

        return list(set(found))

    def _find_sodium_in_ingredients(self, product: Dict) -> List[str]:
        """Find sodium-containing ingredients in the product."""
        # Note: Not all sodium compounds contribute dietary sodium equally
        # Salt (NaCl) is the primary concern; some sodium compounds are minimal
        high_sodium_keywords = [
            'salt', 'sodium chloride', 'sea salt', 'table salt'
        ]
        # These contain sodium but in smaller amounts
        moderate_sodium_keywords = [
            'sodium citrate', 'sodium bicarbonate', 'baking soda',
            'sodium ascorbate', 'sodium benzoate'
        ]

        found = []
        all_ingredients = (
            product.get('inactiveIngredients', []) +
            product.get('activeIngredients', [])
        )

        for ing in all_ingredients:
            name = ing.get('name', '').lower()
            std_name = ing.get('standardName', '').lower()

            # Check high-sodium sources first
            for keyword in high_sodium_keywords:
                if keyword in name or keyword in std_name:
                    found.append(f"{ing.get('name', '')} (high)")
                    break
            else:
                # Check moderate sodium sources
                for keyword in moderate_sodium_keywords:
                    if keyword in name or keyword in std_name:
                        found.append(f"{ing.get('name', '')} (trace)")
                        break

        return list(set(found))

    def _check_problematic_sweeteners(self, product: Dict) -> Dict:
        """
        Check for sweeteners that may be problematic for specific conditions.

        Based on:
        - WHO 2023 guidance on non-nutritive sweeteners
        - ADA 2024 standards (sweeteners can be used in moderation)
        - Recent research on gut microbiome effects
        """
        # High glycemic / problematic for diabetics
        high_glycemic_sweeteners = [
            'maltodextrin', 'dextrose', 'glucose syrup', 'corn syrup solids',
            'tapioca maltodextrin', 'rice syrup'
        ]

        # Artificial sweeteners (controversial, some research concerns)
        artificial_sweeteners = [
            'aspartame', 'sucralose', 'saccharin', 'acesulfame',
            'neotame', 'advantame'
        ]

        # Sugar alcohols (may cause GI issues)
        sugar_alcohols = [
            'sorbitol', 'mannitol', 'xylitol', 'erythritol', 'maltitol',
            'isomalt', 'lactitol'
        ]

        # Generally safer alternatives for diabetics
        safer_alternatives = [
            'stevia', 'monk fruit', 'allulose', 'lo han guo'
        ]

        found_high_glycemic = []
        found_artificial = []
        found_sugar_alcohols = []
        found_safer = []

        all_ingredients = (
            product.get('inactiveIngredients', []) +
            product.get('activeIngredients', [])
        )

        for ing in all_ingredients:
            name = ing.get('name', '').lower()
            std_name = ing.get('standardName', '').lower()
            combined = f"{name} {std_name}"

            for sweetener in high_glycemic_sweeteners:
                if sweetener in combined:
                    found_high_glycemic.append(ing.get('name', ''))
                    break

            for sweetener in artificial_sweeteners:
                if sweetener in combined:
                    found_artificial.append(ing.get('name', ''))
                    break

            for sweetener in sugar_alcohols:
                if sweetener in combined:
                    found_sugar_alcohols.append(ing.get('name', ''))
                    break

            for sweetener in safer_alternatives:
                if sweetener in combined:
                    found_safer.append(ing.get('name', ''))
                    break

        return {
            "high_glycemic": list(set(found_high_glycemic)),
            "artificial": list(set(found_artificial)),
            "sugar_alcohols": list(set(found_sugar_alcohols)),
            "safer_alternatives": list(set(found_safer)),
            "has_high_glycemic": len(found_high_glycemic) > 0,
            "has_artificial": len(found_artificial) > 0,
            "has_sugar_alcohols": len(found_sugar_alcohols) > 0,
            "uses_safer_alternatives": len(found_safer) > 0
        }

    def _generate_dietary_warnings(self, sugar_data: Dict, sodium_data: Dict,
                                   sweetener_data: Dict) -> List[Dict]:
        """
        Generate user-facing warnings for dietary sensitivities.
        """
        warnings = []

        # Sugar warnings for diabetics
        if sugar_data["exceeds_diabetic_threshold"]:
            warnings.append({
                "type": "diabetes",
                "severity": "high" if sugar_data["level"] == "high" else "moderate",
                "message": f"Contains {sugar_data['amount_g']}g sugar per serving. "
                          f"May affect blood glucose levels.",
                "recommendation": "Consult healthcare provider if managing diabetes."
            })

        # High glycemic sweetener warning
        if sweetener_data["has_high_glycemic"]:
            warnings.append({
                "type": "diabetes",
                "severity": "moderate",
                "message": f"Contains high-glycemic sweeteners: "
                          f"{', '.join(sweetener_data['high_glycemic'])}",
                "recommendation": "May cause blood sugar spikes despite low sugar content."
            })

        # Sodium warnings for hypertension
        if sodium_data["exceeds_aha_threshold"]:
            warnings.append({
                "type": "hypertension",
                "severity": "high" if sodium_data["level"] == "high" else "moderate",
                "message": f"Contains {sodium_data['amount_mg']}mg sodium per serving "
                          f"({sodium_data['percent_daily_value']}% DV).",
                "recommendation": "Monitor intake if managing blood pressure."
            })

        # Sugar alcohol warning (GI issues)
        if sweetener_data["has_sugar_alcohols"]:
            warnings.append({
                "type": "digestive",
                "severity": "low",
                "message": f"Contains sugar alcohols: "
                          f"{', '.join(sweetener_data['sugar_alcohols'])}",
                "recommendation": "May cause digestive discomfort in some individuals."
            })

        return warnings

    def _empty_rda_ul_payload(self, reason: str) -> Dict:
        """Return a schema-stable empty RDA/UL payload when collection is skipped."""
        return {
            "ingredients_with_rda": [],
            "analyzed_ingredients": [],
            "count": 0,
            "adequacy_results": [],
            "conversion_evidence": [],
            "safety_flags": [],
            "has_over_ul": False,
            "collection_enabled": False,
            "collection_reason": reason
        }

    # =========================================================================
    # PRENATAL COVERAGE LEDGER (Section E device-side data; NOT used in scoring)
    # =========================================================================

    # Pregnancy anchor nutrients. Coverage is a completeness LEDGER for the
    # app's stack/"what's missing or underdosed" views - it must never feed
    # the quality score: a base prenatal that intentionally ships DHA/choline
    # as a companion product is not a lower-QUALITY product (role-fairness).
    # Targets come from rda_optimal_uls.json Pregnancy rows at enrich time;
    # DHA (no DRI row) falls back to the prenatal synergy cluster's minimum
    # effective dose (200 mg, ACOG/ISSFAL consensus floor).
    PRENATAL_ANCHOR_TOKENS = {
        "folate": ["folate", "folic", "b9"],
        "iron": ["iron"],
        "iodine": ["iodine"],
        "vitamin_d": ["vitamin d"],
        "vitamin_b12": ["b12", "cobalamin"],
        "choline": ["choline"],
        "dha": ["dha", "docosahexaenoic"],
        "calcium": ["calcium"],
    }
    PRENATAL_RDA_ROW_NAMES = {
        "folate": "Folate",
        "iron": "Iron",
        "iodine": "Iodine",
        "vitamin_d": "Vitamin D",
        "vitamin_b12": "Vitamin B12",
        "choline": "Choline",
        "calcium": "Calcium",
    }
    # A dose is "meaningful" at >= 2/3 of the pregnancy RDA/AI. Below that it
    # counts as below_target (e.g. 110 mg choline vs the 450 mg AI).
    PRENATAL_ADEQUACY_FLOOR = 0.67

    @staticmethod
    def _prenatal_amount_convert(quantity: float, unit: str, target_unit: str) -> Optional[float]:
        """Convert label quantity to the anchor's canonical unit (mg or mcg).

        Handles mcg/ug/mg/g, treats 'mcg DFE'/'mcg RAE' as mcg, and vitamin D
        IU (1 mcg = 40 IU). Returns None when the unit is not interpretable.
        """
        u = (unit or "").strip().lower().replace("µg", "mcg")
        base_mcg = None
        if u.startswith("mcg") or u.startswith("ug"):
            base_mcg = quantity
        elif u.startswith("mg"):
            base_mcg = quantity * 1000.0
        elif u == "g" or u.startswith("g "):
            base_mcg = quantity * 1_000_000.0
        elif u == "iu" or u.startswith("iu"):
            # Only meaningful for vitamin D here (1 mcg = 40 IU)
            base_mcg = quantity / 40.0 if target_unit == "mcg" else None
        if base_mcg is None:
            return None
        return base_mcg if target_unit == "mcg" else base_mcg / 1000.0

    def _prenatal_pregnancy_targets(self) -> Dict[str, Dict]:
        """Pregnancy RDA/AI + UL per anchor, read from reference data."""
        targets: Dict[str, Dict] = {}
        rda_db = self.databases.get('rda_optimal_uls', {}) or {}
        rows = {
            str(n.get("standard_name", "")): n
            for n in rda_db.get("nutrient_recommendations", []) or []
        }
        unit_map = {
            "folate": "mcg", "iron": "mg", "iodine": "mcg", "vitamin_d": "mcg",
            "vitamin_b12": "mcg", "choline": "mg", "calcium": "mg",
        }
        for anchor, row_name in self.PRENATAL_RDA_ROW_NAMES.items():
            row = rows.get(row_name)
            if not row:
                continue
            preg = [
                d for d in row.get("data", []) or []
                if "preg" in str(d.get("group", "")).lower()
                and d.get("age_range") in ("19-30", "31-50")
            ]
            if not preg:
                continue
            targets[anchor] = {
                "target": preg[0].get("rda_ai"),
                "ul": preg[0].get("ul"),
                "unit": unit_map[anchor],
                "source": f"rda_optimal_uls:{row_name}:Pregnancy",
            }
        # DHA: no DRI row - use the prenatal synergy cluster's min effective
        # dose when available, else the 200 mg consensus floor.
        dha_min = 200.0
        synergy_db = self.databases.get('synergy_cluster', {}) or {}
        for cluster in synergy_db.get('synergy_clusters', []) or []:
            if cluster.get('id') == 'prenatal_pregnancy_support':
                try:
                    dha_min = float((cluster.get('min_effective_doses') or {}).get('dha', dha_min))
                except (TypeError, ValueError):
                    pass
                break
        targets["dha"] = {
            "target": dha_min, "ul": None, "unit": "mg",
            "source": "synergy_cluster:prenatal_pregnancy_support (200 mg consensus floor fallback)",
        }
        return targets

    def _collect_prenatal_coverage(
        self,
        product: Dict,
        max_servings_per_day: Optional[float] = None
    ) -> Dict:
        """
        Build the prenatal coverage ledger (Section E, device-side data).

        For each pregnancy anchor nutrient: present/missing, per-day amount,
        pregnancy target, and a status in
        {missing, below_target, meets_target, above_ul}.

        Contract: informational only. The v3-series scorer does not read this
        block; the app decides when to display it (role-aware completeness is
        a display/stack concern, not a product-quality concern).
        """
        targets = self._prenatal_pregnancy_targets()
        try:
            servings = float(max_servings_per_day) if max_servings_per_day else 1.0
        except (TypeError, ValueError):
            servings = 1.0
        if servings <= 0:
            servings = 1.0

        # Sum per-anchor amounts across matching actives (standardName-based
        # to avoid salt-cation traps like "calcium ascorbate" -> Vitamin C).
        sums: Dict[str, float] = {}
        unparsed: Dict[str, List[str]] = {}
        for ing in product.get('activeIngredients', []) or []:
            std = (ing.get('standardName') or ing.get('name') or '').lower()
            if not std:
                continue
            try:
                qty = float(ing.get('quantity') or 0)
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue
            unit = ing.get('unit', '')
            for anchor, tokens in self.PRENATAL_ANCHOR_TOKENS.items():
                if anchor not in targets:
                    continue
                # Word-boundary match: a bare substring test lets "dha" match
                # inside "ashwagandha" (and "iron" inside "environmental", etc.).
                if any(
                    re.search(r'\b' + re.escape(tok) + r'\b', std)
                    for tok in tokens
                ):
                    converted = self._prenatal_amount_convert(
                        qty, unit, targets[anchor]["unit"]
                    )
                    if converted is None:
                        unparsed.setdefault(anchor, []).append(
                            f"{ing.get('name', '')} ({qty} {unit})"
                        )
                    else:
                        sums[anchor] = sums.get(anchor, 0.0) + converted
                    break  # one anchor per ingredient row

        anchors_out: Dict[str, Dict] = {}
        summary = {"missing": [], "below_target": [], "meets_target": [], "above_ul": []}
        for anchor, tinfo in targets.items():
            target = tinfo.get("target")
            ul = tinfo.get("ul")
            amount = sums.get(anchor)
            entry: Dict[str, Any] = {
                "present": amount is not None,
                "amount_per_day": round(amount * servings, 3) if amount is not None else None,
                "unit": tinfo["unit"],
                "pregnancy_target": target,
                "pregnancy_ul": ul,
                "target_source": tinfo["source"],
            }
            if anchor in unparsed:
                entry["unparsed_rows"] = unparsed[anchor]
            if amount is None:
                status = "missing"
            else:
                per_day = amount * servings
                pct = (per_day / target * 100.0) if target else None
                entry["pct_of_target"] = round(pct, 1) if pct is not None else None
                if ul is not None and per_day > float(ul):
                    status = "above_ul"
                elif target and per_day < float(target) * self.PRENATAL_ADEQUACY_FLOOR:
                    status = "below_target"
                else:
                    status = "meets_target"
            entry["status"] = status
            anchors_out[anchor] = entry
            summary[status].append(anchor)

        # Prenatal positioning: "prenatal" anywhere, OR a target group that
        # AFFIRMATIVELY targets pregnant/lactating women. A pregnancy CAUTION
        # ("Women (not pregnant or lactating)", "not for use if pregnant") is a
        # contraindication, not positioning - it must not flip this true.
        name = str(product.get('fullName', '') or '').lower()
        target_groups = [str(t).lower() for t in (product.get('targetGroups', []) or [])]
        affirmative_pregnancy_target = any(
            ("pregnan" in tg or "lactat" in tg)
            and not re.search(r'\bnot\b|\bnon[\s-]?pregnan|\bexcept', tg)
            for tg in target_groups
        )
        is_prenatal_positioned = (
            "prenatal" in name
            or any("prenatal" in tg for tg in target_groups)
            or affirmative_pregnancy_target
        )

        return {
            "schema_version": "1.0.0",
            "basis": "pregnancy_19_50_per_day",
            "servings_per_day_used": servings,
            "adequacy_floor_pct": int(self.PRENATAL_ADEQUACY_FLOOR * 100),
            "is_prenatal_positioned": is_prenatal_positioned,
            "anchors": anchors_out,
            "summary": summary,
            "scoring_impact": "none",
        }

    # =========================================================================
    # PRODUCT ROLE CLASSIFICATION (Section E device-side data; NOT scored)
    # =========================================================================

    # Text signals that a product markets itself as a COMPLETE / all-in-one
    # solution. If it makes this claim but is only a base (missing DHA/choline),
    # that is a claim/completeness mismatch the app can surface - it is NOT a
    # quality penalty here.
    COMPLETE_CLAIM_PATTERN = re.compile(
        r'\b(all[\s-]?in[\s-]?one|complete|comprehensive|everything\s+you\s+need|'
        r'all\s+you\s+need|full[\s-]?spectrum\s+prenatal|one[\s-]?and[\s-]?done|'
        r'total\s+prenatal)\b',
        re.I,
    )

    # A product is prenatal "by composition" when it carries the non-negotiable
    # prenatal core. DHA/choline/iron are the COMPLETENESS nutrients whose
    # presence separates a complete prenatal from a base (companion-paired).
    PRENATAL_CORE_ANCHORS = ("folate", "iodine", "vitamin_d", "vitamin_b12")
    PRENATAL_COMPLETENESS_ANCHORS = ("iron", "dha", "choline")

    def _classify_product_role(
        self,
        product: Dict,
        coverage: Dict,
        supp_type: str,
    ) -> Dict:
        """
        Classify the product's ROLE so the app can be role-aware (a prenatal
        base that pairs with a separate DHA/choline product is not a low-quality
        prenatal - it is a different role). Data-only: the v3 scorer does not
        read this; role-aware SCORING would be a separate, versioned change.

        Roles: prenatal_complete, prenatal_base, prenatal_dha_companion,
        prenatal_choline_companion, general_multi, targeted_gap_filler,
        single_ingredient, unclassified.
        """
        anchors = (coverage or {}).get("anchors", {}) or {}

        def present(anchor: str) -> bool:
            a = anchors.get(anchor)
            return bool(a) and a.get("status") in ("meets_target", "below_target", "above_ul")

        core_present = [a for a in self.PRENATAL_CORE_ANCHORS if present(a)]
        completeness_present = [a for a in self.PRENATAL_COMPLETENESS_ANCHORS if present(a)]
        completeness_missing = [
            a for a in self.PRENATAL_COMPLETENESS_ANCHORS if not present(a)
        ]

        is_prenatal_positioned = bool((coverage or {}).get("is_prenatal_positioned"))
        is_prenatal_by_composition = len(core_present) >= 3
        active_count = len([
            i for i in product.get('activeIngredients', []) or []
            if (i.get('quantity') or 0)
        ])

        all_present = [a for a in anchors if present(a)]

        role = "unclassified"
        # Companion products: a small product built around DHA and/or choline,
        # marketed prenatal but not a multi.
        dha_only = present("dha") and not is_prenatal_by_composition
        choline_only = present("choline") and not is_prenatal_by_composition
        if (is_prenatal_positioned or dha_only or choline_only) and active_count <= 3 \
                and not is_prenatal_by_composition:
            if present("dha") and not present("choline"):
                role = "prenatal_dha_companion"
            elif present("choline") and not present("dha"):
                role = "prenatal_choline_companion"
            elif present("dha") and present("choline"):
                role = "prenatal_dha_companion"  # dominant anchor; app can refine
        if role == "unclassified":
            if is_prenatal_positioned or is_prenatal_by_composition:
                if not completeness_missing:
                    role = "prenatal_complete"
                else:
                    role = "prenatal_base"
            elif supp_type in ("probiotic", "prebiotic", "herbal_blend"):
                # These are already meaningful roles; pass through.
                role = supp_type
            elif supp_type in ("single", "single_nutrient") or active_count == 1:
                role = "single_ingredient"
            elif supp_type == "multivitamin" or active_count >= 6:
                # Count-based fallback (matches the scorer's >=6 == multivitamin
                # rule); robust when supp_type resolves to "specialty".
                role = "general_multi"
            elif supp_type in ("targeted", "targeted_condition") or 2 <= active_count <= 5:
                role = "targeted_gap_filler"

        text = " ".join(filter(None, [
            str(product.get('fullName', '') or ''),
            " ".join(
                str(s.get('notes', '') or s.get('text', ''))
                for s in product.get('statements', []) or []
                if isinstance(s, dict)
            ),
        ]))
        claims_complete = bool(self.COMPLETE_CLAIM_PATTERN.search(text))
        # A completeness claim only conflicts for a prenatal that is missing
        # completeness nutrients (base). A genuinely complete prenatal claiming
        # "complete" is consistent.
        completeness_claim_mismatch = bool(
            claims_complete and role == "prenatal_base" and completeness_missing
        )

        return {
            "schema_version": "1.0.0",
            "role": role,
            "is_prenatal_positioned": is_prenatal_positioned,
            "is_prenatal_by_composition": is_prenatal_by_composition,
            "core_anchors_present": core_present,
            "completeness_present": completeness_present,
            "completeness_missing": completeness_missing,
            "claims_complete": claims_complete,
            "completeness_claim_mismatch": completeness_claim_mismatch,
            "scoring_impact": "none",
        }

    # =========================================================================
    # RDA/UL DATA COLLECTOR (for user profile scoring on device)
    # =========================================================================

    def _collect_rda_ul_data(
        self,
        product: Dict,
        min_servings_per_day: Optional[float] = None,
        max_servings_per_day: Optional[float] = None
    ) -> Dict:
        """
        Collect RDA/UL reference data for user profile scoring (Section E).

        Uses RDAULCalculator and UnitConverter for evidence-based adequacy:
        - Unit conversion with form detection (Vitamin A, E)
        - Adequacy band classification
        - Safety flag generation for over-UL nutrients
        - Full evidence tracking
        """
        active_ingredients = product.get('activeIngredients', [])
        rda_data = []
        adequacy_results = []
        safety_flags = []
        conversion_evidence = []
        try:
            servings_min = float(min_servings_per_day) if min_servings_per_day is not None else None
        except (TypeError, ValueError):
            servings_min = None
        try:
            servings_max = float(max_servings_per_day) if max_servings_per_day is not None else None
        except (TypeError, ValueError):
            servings_max = None

        if servings_min is None or servings_min <= 0:
            servings_min = 1
        if servings_max is None or servings_max <= 0:
            servings_max = servings_min

        # Use new modules if available
        if self.unit_converter and self.rda_calculator:
            try:
                for ingredient in active_ingredients:
                    ing_name = ingredient.get('name', '')
                    std_name = ingredient.get('standardName', '') or ing_name
                    quantity = ingredient.get('quantity', 0)
                    unit = ingredient.get('unit', '')

                    # Convert quantity to float safely
                    try:
                        quantity_float = float(quantity) if quantity else 0
                    except (ValueError, TypeError):
                        continue

                    if quantity_float == 0:
                        continue

                    # Step 1: Convert units with form detection
                    conversion = self.unit_converter.convert_nutrient(
                        nutrient=std_name,
                        amount=quantity_float,
                        from_unit=unit,
                        ingredient_name=ing_name
                    )

                    conv_evidence = conversion.to_dict()
                    conv_evidence["ingredient"] = ing_name
                    conversion_evidence.append(conv_evidence)

                    # Step 2: Compute adequacy with converted amount
                    rule_id = (conversion.conversion_rule_id or '').lower()
                    form_detected = (conversion.form_detected or '').lower()
                    unknown_form = (
                        'unknown' in rule_id or
                        'unknown' in form_detected or
                        'unspecified' in form_detected
                    )
                    conversion_failed = (
                        not conversion.success or
                        conversion.converted_value is None or
                        conversion.converted_unit is None
                    )
                    if conversion_failed:
                        unit_normalized = unit.lower().replace('µg', 'mcg').replace(' ', '_').strip()
                        if unit_normalized.startswith('mcg') or unit_normalized.startswith('mg') or unit_normalized == 'g':
                            conversion_failed = False
                    skip_ul_check = False
                    skip_ul_reason = None
                    if unknown_form:
                        skip_ul_check = True
                        skip_ul_reason = "unknown_vitamin_form"
                    elif conversion_failed:
                        skip_ul_check = True
                        skip_ul_reason = "conversion_failed"

                    converted_amount = conversion.converted_value or float(quantity)
                    converted_unit = conversion.converted_unit or unit
                    per_day_min = converted_amount * servings_min
                    per_day_max = converted_amount * servings_max
                    amount_for_ul = per_day_max or per_day_min or converted_amount

                    adequacy = self.rda_calculator.compute_nutrient_adequacy(
                        nutrient=std_name,
                        amount=amount_for_ul,
                        unit=converted_unit
                    )

                    adequacy_dict = adequacy.to_dict()
                    if skip_ul_check:
                        adequacy_dict.update({
                            "rda_ai": None,
                            "rda_ai_source": "unknown",
                            "ul": None,
                            "ul_status": f"skipped_{skip_ul_reason}",
                            "pct_rda": None,
                            "pct_ul": None,
                            "adequacy_band": "unknown",
                            "over_ul": False,
                            "over_ul_amount": None,
                            "scoring_eligible": False,
                            "point_recommendation": 0,
                            "notes": [f"UL check skipped: {skip_ul_reason}"],
                            "warnings": []
                        })
                        adequacy_dict["skip_ul_check"] = True
                        adequacy_dict["skip_ul_reason"] = skip_ul_reason
                        if skip_ul_reason == "unknown_vitamin_form":
                            adequacy_dict["form_confidence"] = "LOW"
                    else:
                        adequacy_dict["skip_ul_check"] = False
                    adequacy_dict["original_quantity"] = quantity
                    adequacy_dict["original_unit"] = unit
                    adequacy_dict["conversion_applied"] = conversion.success
                    adequacy_dict["per_day_min"] = per_day_min
                    adequacy_dict["per_day_max"] = per_day_max
                    adequacy_dict["servings_per_day_min"] = servings_min
                    adequacy_dict["servings_per_day_max"] = servings_max
                    adequacy_results.append(adequacy_dict)

                    # Collect safety flags
                    if not skip_ul_check and adequacy.over_ul:
                        pct_ul_val = adequacy.pct_ul or 0
                        over_ul_amount = adequacy.over_ul_amount or 0
                        safety_flags.append({
                            "nutrient": ing_name,
                            "amount": amount_for_ul,
                            "unit": converted_unit,
                            "ul": adequacy.ul,
                            "pct_ul": pct_ul_val,
                            "over_amount": over_ul_amount,
                            "warning": f"Exceeds UL by {over_ul_amount:.1f}",
                            "severity": "critical" if pct_ul_val >= 200 else "warning"
                        })

                    # Legacy format for backward compatibility
                    rda_data.append({
                        "ingredient": ing_name,
                        "standard_name": std_name,
                        "quantity": quantity,
                        "unit": unit,
                        "converted_quantity": converted_amount,
                        "converted_unit": converted_unit,
                        "per_day_min": per_day_min,
                        "per_day_max": per_day_max,
                        "servings_per_day_min": servings_min,
                        "servings_per_day_max": servings_max,
                        "skip_ul_check": skip_ul_check,
                        "skip_ul_reason": skip_ul_reason,
                        "nutrient_unit": adequacy.unit,
                        "highest_ul": None if skip_ul_check else adequacy.ul,
                        "optimal_range": f"{adequacy.optimal_min}-{adequacy.optimal_max}" if adequacy.optimal_min else "",
                        "pct_rda": None if skip_ul_check else adequacy.pct_rda,
                        "adequacy_band": "unknown" if skip_ul_check else adequacy.adequacy_band,
                        "warnings": [] if skip_ul_check else adequacy.warnings,
                        "data_by_group": []  # Deprecated in new format
                    })

                return {
                    "ingredients_with_rda": rda_data,
                    "analyzed_ingredients": rda_data,  # AC3: Canonical field name for scoring
                    "count": len(rda_data),
                    # Enhanced evidence fields
                    "adequacy_results": adequacy_results,
                    "conversion_evidence": conversion_evidence,
                    "safety_flags": safety_flags,
                    "has_over_ul": len(safety_flags) > 0
                }

            except Exception as e:
                self._rda_ul_warning_count += 1
                if self._rda_ul_warning_count <= 3:
                    self.logger.warning(f"RDA/UL calculation failed, using fallback: {e}")
                elif self._rda_ul_warning_count == 4:
                    self.logger.warning(
                        "RDA/UL fallback warnings are being suppressed after 3 occurrences; "
                        "enable DEBUG logs for full detail."
                    )
                else:
                    self.logger.debug(f"RDA/UL calculation failed, using fallback: {e}")

        # Fallback: original logic
        rda_db = self.databases.get('rda_optimal_uls', {})
        nutrient_recs = rda_db.get('nutrient_recommendations', [])

        for ingredient in active_ingredients:
            ing_name = ingredient.get('name', '')
            std_name = ingredient.get('standardName', '') or ing_name
            quantity = ingredient.get('quantity', 0)
            unit = ingredient.get('unit', '')

            for nutrient in nutrient_recs:
                nutrient_name = nutrient.get('standard_name', '')
                name_match = (
                    self._normalize_text(std_name) == self._normalize_text(nutrient_name) or
                    self._normalize_text(ing_name) == self._normalize_text(nutrient_name)
                )
                if name_match:
                    try:
                        quantity_float = float(quantity)
                    except (TypeError, ValueError):
                        quantity_float = None

                    if quantity_float is None:
                        per_day_min = quantity
                        per_day_max = quantity
                    else:
                        per_day_min = quantity_float * servings_min
                        per_day_max = quantity_float * servings_max

                    rda_data.append({
                        "ingredient": ing_name,
                        "standard_name": nutrient_name,
                        "quantity": quantity,
                        "unit": unit,
                        "per_day_min": per_day_min,
                        "per_day_max": per_day_max,
                        "servings_per_day_min": servings_min,
                        "servings_per_day_max": servings_max,
                        "nutrient_unit": nutrient.get('unit', ''),
                        "highest_ul": nutrient.get('highest_ul', 0),
                        "optimal_range": nutrient.get('optimal_range', ''),
                        "warnings": nutrient.get('warnings', []),
                        "data_by_group": nutrient.get('data', [])
                    })
                    break

        return {
            "ingredients_with_rda": rda_data,
            "analyzed_ingredients": rda_data,  # AC3: Canonical field name for scoring
            "count": len(rda_data)
        }

    # =========================================================================
    # MAIN ENRICHMENT METHOD
    # =========================================================================

    def enrich_product(self, product: Dict) -> Tuple[Dict, List[str]]:
        """
        Enrich a single product with all data needed for scoring.
        Returns: (enriched_product, issues_list)
        """
        product_id = product.get('dsld_id', product.get('id', 'unknown'))
        issues = []

        # Validate product structure before processing
        is_valid, validation_issues = self.validate_product(product)
        if not is_valid:
            issues.extend(validation_issues)
            self.logger.warning(
                "Product %s: Validation failed - %s", product_id, validation_issues
            )
            # Return product with empty schema placeholders for consistent output
            product.update(copy.deepcopy(self.EMPTY_ENRICHMENT_SCHEMA))
            product["enrichment_status"] = "validation_failed"
            product["enrichment_error"] = "; ".join(validation_issues)
            return product, issues

        try:
            # Start with all cleaned data
            enriched = dict(product)

            # Map DSLD field names to scoring-expected names for consistency
            if 'id' in enriched and 'dsld_id' not in enriched:
                enriched['dsld_id'] = enriched['id']
            if 'fullName' in enriched and 'product_name' not in enriched:
                enriched['product_name'] = enriched['fullName']

            # Add enrichment metadata
            enriched["enrichment_version"] = self.VERSION
            enriched["compatible_scoring_versions"] = self.COMPATIBLE_SCORING_VERSIONS
            enriched["enriched_date"] = datetime.utcnow().isoformat() + "Z"
            enriched["reference_versions"] = self.reference_versions  # Track data file versions for auditability

            # Classify supplement type (determines scoring adjustments)
            enriched["supplement_type"] = self._classify_supplement_type(product)

            # Section A: Ingredient Quality
            enriched["ingredient_quality_data"] = self._collect_ingredient_quality_data(product)
            enriched["delivery_data"] = self._collect_delivery_data(product)
            enriched["absorption_data"] = self._collect_absorption_data(product)
            enriched["formulation_data"] = self._collect_formulation_data(product)

            # Section B: Safety & Purity
            # Collect contaminant_data once, pass to compliance to avoid double-collection
            contaminant_data = self._collect_contaminant_data(product)
            enriched["contaminant_data"] = contaminant_data
            enriched["compliance_data"] = self._collect_compliance_data(
                product, contaminant_data=contaminant_data
            )
            enriched["certification_data"] = self._collect_certification_data(product)
            enriched["proprietary_data"] = self._collect_proprietary_data(product)

            # Section C: Evidence & Research
            enriched["evidence_data"] = self._collect_evidence_data(product)

            # Section D: Brand Trust
            manufacturer_data = self._collect_manufacturer_data(product)
            enriched["manufacturer_data"] = manufacturer_data

            # P1.3: Add manufacturer_normalized at top-level for stable matching
            manufacturer_raw = manufacturer_data.get('manufacturer', '') or manufacturer_data.get('brand_name', '')
            enriched["manufacturer_normalized"] = self._normalize_company_name(manufacturer_raw)

            # P0.4: Serving basis and form factor for deterministic prescore
            serving_data = self._collect_serving_basis_data(product)
            enriched["serving_basis"] = serving_data["serving_basis"]
            enriched["form_factor"] = serving_data["form_factor"]

            # Section E: User Profile Data (for device-side scoring)
            collect_rda_ul_data = self.config.get("processing_config", {}).get("collect_rda_ul_data", True)
            if collect_rda_ul_data:
                servings_min = serving_data["serving_basis"].get("min_servings_per_day")
                servings_max = serving_data["serving_basis"].get("max_servings_per_day")
                enriched["rda_ul_data"] = self._collect_rda_ul_data(
                    product,
                    min_servings_per_day=servings_min,
                    max_servings_per_day=servings_max
                )
                if isinstance(enriched["rda_ul_data"], dict):
                    enriched["rda_ul_data"]["collection_enabled"] = True
            else:
                enriched["rda_ul_data"] = self._empty_rda_ul_payload("disabled_by_config")

            # Probiotic-specific data
            enriched["probiotic_data"] = self._collect_probiotic_data(product)

            # Dietary sensitivity data (sugar/sodium for diabetes/hypertension users)
            enriched["dietary_sensitivity_data"] = self._collect_dietary_sensitivity_data(product)

            # Prenatal coverage ledger (Section E device-side data; not scored)
            enriched["prenatal_coverage"] = self._collect_prenatal_coverage(
                product,
                max_servings_per_day=serving_data["serving_basis"].get("max_servings_per_day")
            )
            # Product role classification (Section E device-side data; not scored)
            enriched["product_role"] = self._classify_product_role(
                product,
                enriched["prenatal_coverage"],
                enriched.get("supplement_type", {}).get("type")
                if isinstance(enriched.get("supplement_type"), dict)
                else enriched.get("supplement_type"),
            )

            # Product-level signals (coverage, certificates, label disclosure)
            enriched["product_signals"] = self._collect_product_signals(
                product,
                enriched.get("ingredient_quality_data", {}),
                enriched.get("certification_data", {}),
                enriched.get("formulation_data", {}),
                enriched.get("probiotic_data", {})
            )

            # Project nested enrichment outputs into stable top-level scoring fields.
            self._project_scoring_fields(enriched)

            # P0.2: Dosage normalization with unit conversion evidence
            if self.dosage_normalizer:
                try:
                    dosage_result = self.dosage_normalizer.normalize_product_dosages(product)
                    enriched["dosage_normalization"] = dosage_result.to_dict()
                except Exception as e:
                    self.logger.warning(f"Dosage normalization failed: {e}")
                    enriched["dosage_normalization"] = {"success": False, "error": str(e)}

            # Enrichment metadata (version lock for scoring compatibility)
            enriched["enrichment_metadata"] = {
                "enrichment_version": self.VERSION,
                "scoring_compatibility": self.COMPATIBLE_SCORING_VERSIONS,
                "generated_by": "SupplementEnricherV3",
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "data_completeness": self._calculate_completeness(enriched),
                "ready_for_scoring": True,
                "unmapped_active_count": enriched["ingredient_quality_data"]["unmapped_count"]
            }

            # Build match ledger and unmatched lists (Pipeline Hardening Phase 3)
            ledger_data = self._build_match_ledger(product, enriched)
            enriched["match_ledger"] = ledger_data["match_ledger"]
            enriched["unmatched_ingredients"] = ledger_data.get("unmatched_ingredients", [])
            enriched["unmatched_additives"] = ledger_data.get("unmatched_additives", [])
            enriched["unmatched_allergens"] = ledger_data.get("unmatched_allergens", [])
            enriched["unmatched_delivery_systems"] = ledger_data.get("unmatched_delivery_systems", [])
            enriched["rejected_manufacturer_matches"] = ledger_data.get("rejected_manufacturer_matches", [])
            enriched["rejected_claim_matches"] = ledger_data.get("rejected_claim_matches", [])

            return enriched, issues

        except (KeyError, TypeError) as e:
            # Data structure issues - log and continue
            self.logger.error(f"Product {product_id}: Data structure error: {e}")
            issues.append(f"Data structure error: {str(e)}")
            product["enrichment_status"] = "failed"
            product["enrichment_error"] = f"Data structure error: {str(e)}"
            return product, issues
        except (ValueError, AttributeError) as e:
            # Value/attribute issues - log and continue
            self.logger.error(f"Product {product_id}: Value error: {e}")
            issues.append(f"Value error: {str(e)}")
            product["enrichment_status"] = "failed"
            product["enrichment_error"] = f"Value error: {str(e)}"
            return product, issues
        except Exception as e:
            # Unexpected error - log with traceback for debugging, but don't crash batch
            self.logger.error(f"Product {product_id}: Unexpected enrichment error: {e}", exc_info=True)
            issues.append(f"Enrichment error: {str(e)}")

            # Return product with minimal enrichment
            product["enrichment_version"] = self.VERSION
            product["enriched_date"] = datetime.utcnow().isoformat() + "Z"
            product["enrichment_status"] = "failed"
            product["enrichment_error"] = str(e)

            return product, issues

    def _calculate_completeness(self, enriched: Dict) -> float:
        """Calculate data completeness percentage"""
        checks = [
            enriched.get("ingredient_quality_data", {}).get("total_active", 0) > 0,
            enriched.get("supplement_type", {}).get("type") != "unknown",
            enriched.get("manufacturer_data", {}).get("brand_name", "") != "",
            enriched.get("certification_data") is not None,
            enriched.get("contaminant_data") is not None
        ]

        return (sum(checks) / len(checks)) * 100

    def _track_unmapped(self, ingredient_name: str, ing_type: str):
        """Track unmapped ingredients for reporting"""
        key = f"{ing_type}:{ingredient_name}"
        self.unmapped_tracker[key] = self.unmapped_tracker.get(key, 0) + 1

    def _track_unmapped_form(self, raw_form_text: str, base_name: str, original_label: str):
        """
        Track unmapped forms for database expansion.

        Args:
            raw_form_text: The raw form string that failed to match
            base_name: The base ingredient name (e.g., "Vitamin A")
            original_label: The full original label text
        """
        # Normalize key for deduplication
        key = raw_form_text.lower().strip()
        if not key:
            return

        if key not in self.unmapped_forms_tracker:
            self.unmapped_forms_tracker[key] = {
                'raw_text': raw_form_text,
                'count': 0,
                'base_names': set(),
                'example_labels': []
            }

        entry = self.unmapped_forms_tracker[key]
        entry['count'] += 1
        entry['base_names'].add(base_name)
        if len(entry['example_labels']) < 3 and original_label not in entry['example_labels']:
            entry['example_labels'].append(original_label)

    def get_unmapped_forms_report(self) -> Dict:
        """
        Generate report of all unmapped forms for database expansion.

        Returns:
            Dict with unmapped forms sorted by frequency and base name associations.
        """
        report = {
            'total_unique_unmapped_forms': len(self.unmapped_forms_tracker),
            'total_unmapped_occurrences': sum(
                e['count'] for e in self.unmapped_forms_tracker.values()
            ),
            'forms_by_frequency': [],
            'forms_by_base_name': {}
        }

        # Sort by frequency (most common first)
        sorted_forms = sorted(
            self.unmapped_forms_tracker.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )

        for key, entry in sorted_forms:
            base_names_list = list(entry['base_names'])
            report['forms_by_frequency'].append({
                'raw_form': entry['raw_text'],
                'count': entry['count'],
                'base_names': base_names_list,
                'example_labels': entry['example_labels']
            })

            # Group by base name for easier database expansion
            for base_name in base_names_list:
                if base_name not in report['forms_by_base_name']:
                    report['forms_by_base_name'][base_name] = []
                report['forms_by_base_name'][base_name].append(entry['raw_text'])

        return report

    def _build_match_ledger(self, product: Dict, enriched: Dict) -> Dict:
        """
        Build match ledger from enriched data.

        Extracts match information from existing enrichment structures
        and builds a centralized audit ledger.

        Returns:
            Dict containing match_ledger and unmatched_* lists
        """
        ledger = MatchLedgerBuilder()

        # =====================================================================
        # INGREDIENTS DOMAIN
        # =====================================================================
        ingredient_data = enriched.get("ingredient_quality_data", {})

        # Process scorable ingredients (matched)
        for ing in ingredient_data.get("ingredients_scorable", []):
            raw_text = ing.get("original_name") or ing.get("name", "")
            std_name = ing.get("standard_name", "")
            canonical_id = ing.get("canonical_id")
            match_tier = ing.get("match_tier")

            # Determine source path from provenance if available
            source_path = ing.get("raw_source_path", "activeIngredients")
            normalized_key = ing.get("normalized_key") or norm_module.make_normalized_key(raw_text)

            if canonical_id:
                # Map match_tier to method
                method = METHOD_EXACT
                if match_tier == "normalized":
                    method = METHOD_NORMALIZED
                elif match_tier == "pattern":
                    method = METHOD_PATTERN
                elif match_tier == "contains":
                    method = METHOD_CONTAINS

                ledger.record_match(
                    domain=DOMAIN_INGREDIENTS,
                    raw_source_text=raw_text,
                    raw_source_path=source_path,
                    canonical_id=canonical_id,
                    match_method=method,
                    matched_to_name=std_name,
                    confidence=1.0 if match_tier == "exact" else 0.9,
                    normalized_key=normalized_key,
                )
            else:
                recognition_type = ing.get("recognition_type")
                if ing.get("recognized_non_scorable") and recognition_type == "botanical_unscored":
                    ledger.record_recognized_botanical_unscored(
                        domain=DOMAIN_INGREDIENTS,
                        raw_source_text=raw_text,
                        raw_source_path=source_path,
                        botanical_db_match=ing.get("matched_entry_name") or std_name or raw_text,
                        reason=ing.get("recognition_reason") or "botanical_unscored",
                        normalized_key=normalized_key,
                    )
                elif ing.get("recognized_non_scorable"):
                    ledger.record_recognized_non_scorable(
                        domain=DOMAIN_INGREDIENTS,
                        raw_source_text=raw_text,
                        raw_source_path=source_path,
                        recognition_source=ing.get("recognition_source") or "rule_based",
                        recognition_reason=ing.get("recognition_reason") or "recognized_non_scorable",
                        normalized_key=normalized_key,
                    )
                else:
                    # Unmapped scorable ingredient
                    ledger.record_unmatched(
                        domain=DOMAIN_INGREDIENTS,
                        raw_source_text=raw_text,
                        raw_source_path=source_path,
                        reason="no_match_found",
                        normalized_key=normalized_key,
                    )

        # Process skipped ingredients
        for ing in ingredient_data.get("ingredients_skipped", []):
            raw_text = ing.get("name", "")
            source_path = "activeIngredients" if ing.get("source_section") == "active" else "inactiveIngredients"
            skip_reason = ing.get("skip_reason", "non_scorable")
            normalized_key = ing.get("normalized_key") or norm_module.make_normalized_key(raw_text)
            recognition_type = ing.get("recognition_type")
            recognition_source = ing.get("recognition_source")
            recognition_reason = ing.get("recognition_reason")
            recognized_entry_name = ing.get("recognized_entry_name") or ing.get("name", "")

            if skip_reason == SKIP_REASON_RECOGNIZED_NON_SCORABLE:
                if recognition_type == "botanical_unscored":
                    ledger.record_recognized_botanical_unscored(
                        domain=DOMAIN_INGREDIENTS,
                        raw_source_text=raw_text,
                        raw_source_path=source_path,
                        botanical_db_match=recognized_entry_name,
                        reason=recognition_reason or "botanical_unscored",
                        normalized_key=normalized_key,
                    )
                else:
                    ledger.record_recognized_non_scorable(
                        domain=DOMAIN_INGREDIENTS,
                        raw_source_text=raw_text,
                        raw_source_path=source_path,
                        recognition_source=recognition_source or "rule_based",
                        recognition_reason=recognition_reason or "recognized_non_scorable",
                        normalized_key=normalized_key,
                    )
            else:
                ledger.record_skipped(
                    domain=DOMAIN_INGREDIENTS,
                    raw_source_text=raw_text,
                    raw_source_path=source_path,
                    skip_reason=skip_reason,
                    normalized_key=normalized_key,
                )

        # =====================================================================
        # ADDITIVES DOMAIN (from contaminant_data)
        # =====================================================================
        contaminant_data = enriched.get("contaminant_data", {})
        additive_hits = (
            contaminant_data.get("harmful_additives", {}).get("additives")
            if isinstance(contaminant_data.get("harmful_additives"), dict)
            else None
        )
        if additive_hits is None:
            # Backward-compatible fallback for older payload shape.
            additive_hits = contaminant_data.get("additives", [])

        for additive in additive_hits:
            raw_text = (
                additive.get("ingredient")
                or additive.get("raw_source_text")
                or additive.get("additive_name")
                or ""
            )
            matched_name = (
                additive.get("additive_name")
                or additive.get("canonical_name")
                or additive.get("matched_name")
                or ""
            )
            canonical_id = additive.get("additive_id") or additive.get("db_id")
            normalized_key = additive.get("normalized_key") or norm_module.make_normalized_key(raw_text)

            method_raw = self._normalize_text(additive.get("match_method", ""))
            if "exact" in method_raw:
                method = METHOD_EXACT
                confidence = 1.0
            elif "normalized" in method_raw:
                method = METHOD_NORMALIZED
                confidence = 0.9
            else:
                method = METHOD_PATTERN if method_raw else METHOD_NORMALIZED
                confidence = 0.8

            if canonical_id:
                ledger.record_match(
                    domain=DOMAIN_ADDITIVES,
                    raw_source_text=raw_text,
                    raw_source_path="inactiveIngredients",
                    canonical_id=canonical_id,
                    match_method=method,
                    matched_to_name=matched_name,
                    confidence=confidence,
                    normalized_key=normalized_key,
                )
            elif matched_name:
                # Matched but no canonical_id
                ledger.record_match(
                    domain=DOMAIN_ADDITIVES,
                    raw_source_text=raw_text,
                    raw_source_path="inactiveIngredients",
                    canonical_id=matched_name.lower().replace(" ", "_"),  # Generate ID
                    match_method=method,
                    matched_to_name=matched_name,
                    confidence=confidence,
                    normalized_key=normalized_key,
                )

        # =====================================================================
        # ALLERGENS DOMAIN (from compliance_data)
        # =====================================================================
        compliance_data = enriched.get("compliance_data", {})
        for allergen in compliance_data.get("allergens_detected", []):
            raw_text = allergen.get("source_ingredient") or allergen.get("allergen_name", "")
            allergen_type = allergen.get("allergen_type", "")
            normalized_key = norm_module.make_normalized_key(raw_text)

            ledger.record_match(
                domain=DOMAIN_ALLERGENS,
                raw_source_text=raw_text,
                raw_source_path=allergen.get("presence_type", "ingredient_derived"),
                canonical_id=allergen_type.lower().replace(" ", "_"),
                match_method=METHOD_EXACT,
                matched_to_name=allergen_type,
                confidence=1.0,
                normalized_key=normalized_key,
            )

        # =====================================================================
        # MANUFACTURER DOMAIN
        # =====================================================================
        manufacturer_data = enriched.get("manufacturer_data", {})
        top_match = manufacturer_data.get("top_manufacturer", {})

        if top_match.get("found"):
            # Use AC2 provenance fields if available
            raw_text = top_match.get("product_manufacturer_raw") or product.get("brandName") or product.get("manufacturer", "")
            source_path = top_match.get("source_path", "brandName")
            matched_name = top_match.get("name", "")
            canonical_id = top_match.get("manufacturer_id", "")
            confidence = top_match.get("match_confidence", 1.0)
            match_type = top_match.get("match_type", "exact")
            # CONSISTENCY FIX: Always use make_normalized_key() for normalized_key field
            # This ensures manufacturer keys use underscores like ingredient keys (e.g., "protocol_for_life_balance")
            # product_manufacturer_normalized (with spaces) is kept for fuzzy matching comparison only
            normalized_key = norm_module.make_normalized_key(raw_text)

            method = METHOD_EXACT if match_type == "exact" else METHOD_FUZZY

            if match_type == "exact":
                # Exact match - record as matched, will get scoring bonus
                ledger.record_match(
                    domain=DOMAIN_MANUFACTURER,
                    raw_source_text=raw_text,
                    raw_source_path=source_path,
                    canonical_id=canonical_id,
                    match_method=method,
                    matched_to_name=matched_name,
                    confidence=confidence,
                    normalized_key=normalized_key,
                )
            else:
                # POLICY: ALL fuzzy matches are rejected for scoring (exact only gets bonus)
                # Record as rejected regardless of confidence - this populates rejected_manufacturer_matches
                # for auditability of why the product didn't get manufacturer bonus
                rejection_reason = "fuzzy_match_rejected_for_scoring"
                if confidence < 0.85:
                    rejection_reason = "fuzzy_below_threshold"
                ledger.record_rejected(
                    domain=DOMAIN_MANUFACTURER,
                    raw_source_text=raw_text,
                    raw_source_path=source_path,
                    best_match_id=canonical_id,
                    best_match_name=matched_name,
                    match_method=method,
                    confidence=confidence,
                    rejection_reason=rejection_reason,
                    normalized_key=normalized_key,
                )
        else:
            # No match found - use AC2 provenance from top_match if available
            raw_text = top_match.get("product_manufacturer_raw") or product.get("brandName") or product.get("manufacturer", "")
            source_path = top_match.get("source_path", "brandName")
            # CONSISTENCY FIX: Always use make_normalized_key() for normalized_key field
            normalized_key = norm_module.make_normalized_key(raw_text)

            if raw_text:  # Only record if there was input text
                ledger.record_unmatched(
                    domain=DOMAIN_MANUFACTURER,
                    raw_source_text=raw_text,
                    raw_source_path=source_path,
                    reason="no_match_found",
                    normalized_key=normalized_key,
                )

        # =====================================================================
        # DELIVERY SYSTEMS DOMAIN
        # =====================================================================
        delivery_data = enriched.get("delivery_data", {})
        for system in delivery_data.get("matched_systems", []):
            raw_text = system.get("name", "")
            canonical_id = system.get("canonical_id") or raw_text.lower().replace(" ", "_")
            normalized_key = norm_module.make_normalized_key(raw_text)

            ledger.record_match(
                domain=DOMAIN_DELIVERY,
                raw_source_text=raw_text,
                raw_source_path="physicalState",
                canonical_id=canonical_id,
                match_method=METHOD_PATTERN,
                matched_to_name=raw_text,
                confidence=1.0,
                normalized_key=normalized_key,
            )

        # =====================================================================
        # BUILD FINAL OUTPUT
        # =====================================================================
        match_ledger = ledger.build()
        unmatched_lists = ledger.build_unmatched_lists()

        return {
            "match_ledger": match_ledger,
            **unmatched_lists,
        }

    # =========================================================================
    # BATCH PROCESSING
    # =========================================================================

    def process_batch(self, input_file: str, output_dir: str) -> Dict:
        """Process a batch of products"""
        try:
            # Load input data
            with open(input_file, 'r', encoding='utf-8') as f:
                products = json.load(f)

            if not isinstance(products, list):
                products = [products]

            self.logger.info(f"Processing batch: {len(products)} products from {os.path.basename(input_file)}")

            enriched_products = []
            issues_count = 0

            # Check if progress bar should be shown
            show_progress = self.config.get("ui", {}).get("show_progress_bar", True)

            iterator = products
            if show_progress and len(products) > 10 and TQDM_AVAILABLE:
                iterator = tqdm(products, desc="Enriching", unit="product")

            for product in iterator:
                enriched, issues = self.enrich_product(product)
                enriched_products.append(enriched)
                if issues:
                    issues_count += 1

            # Save outputs
            base_name = os.path.splitext(os.path.basename(input_file))[0]

            enriched_dir = os.path.join(output_dir, "enriched")
            os.makedirs(enriched_dir, exist_ok=True)

            output_file = os.path.join(enriched_dir, f"enriched_{base_name}.json")

            # Atomic write: prevents partial files on crash
            self._atomic_write_json(output_file, enriched_products)

            self.logger.info(f"Saved {len(enriched_products)} enriched products to {output_file}")

            # Calculate real success rate based on enrichment_status
            failed_count = sum(
                1 for p in enriched_products
                if p.get('enrichment_status') in ('failed', 'validation_failed')
            )
            successful_count = len(enriched_products) - failed_count
            success_rate = (
                (successful_count / len(enriched_products) * 100)
                if enriched_products else 0
            )

            return {
                "total_products": len(products),
                "successful": successful_count,
                "failed": failed_count,
                "with_issues": issues_count,
                "success_rate": round(success_rate, 1)
            }

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in batch {input_file}: {e}")
            self._write_quarantine(output_dir, input_file, "JSONDecodeError", str(e), "load")
            raise
        except PermissionError as e:
            self.logger.error(f"Permission denied for batch {input_file}: {e}")
            self._write_quarantine(output_dir, input_file, "PermissionError", str(e), "load")
            raise
        except (IOError, OSError) as e:
            self.logger.error(f"I/O error processing batch {input_file}: {e}")
            self._write_quarantine(output_dir, input_file, "IOError", str(e), "load")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error processing batch {input_file}: {e}", exc_info=True)
            self._write_quarantine(
                output_dir, input_file, type(e).__name__, str(e),
                "enrichment", traceback.format_exc()
            )
            raise

    def process_all(self, input_path: str, output_dir: str) -> Dict:
        """Process all files in input path"""
        script_dir = Path(__file__).parent

        # Handle relative paths
        if not os.path.isabs(input_path):
            input_path = script_dir / input_path
        if not os.path.isabs(output_dir):
            output_dir = script_dir / output_dir

        # Get input files
        input_files = []
        if os.path.isfile(input_path):
            input_files = [str(input_path)]
        elif os.path.isdir(input_path):
            input_files = [
                os.path.join(input_path, f)
                for f in os.listdir(input_path)
                if f.endswith('.json')
            ]
        else:
            raise FileNotFoundError(f"Input path not found: {input_path}")

        # Sort for deterministic processing order (reproducible runs)
        input_files.sort()

        if not input_files:
            raise ValueError(f"No JSON files found in: {input_path}")

        self.logger.info(f"Found {len(input_files)} files to process")

        # Process all files
        start_time = datetime.utcnow()
        total_stats = {
            "total_products": 0,
            "successful": 0,
            "with_issues": 0
        }

        for input_file in input_files:
            self.logger.info(f"Processing: {os.path.basename(input_file)}")
            batch_stats = self.process_batch(input_file, str(output_dir))

            for key in total_stats:
                total_stats[key] += batch_stats.get(key, 0)

        # Generate summary
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        summary = {
            "processing_info": {
                "version": self.VERSION,
                "files_processed": len(input_files),
                "duration_seconds": round(duration, 2),
                "timestamp": end_time.isoformat() + "Z"
            },
            "stats": total_stats,
            "match_counters": dict(self.match_counters),
            "unmapped_ingredients": dict(self.unmapped_tracker)
        }

        # Save summary
        reports_dir = os.path.join(output_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)

        summary_file = os.path.join(reports_dir, f"enrichment_summary_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")

        # Atomic write: prevents partial files on crash
        self._atomic_write_json(summary_file, summary)

        self.logger.info("=" * 50)
        self.logger.info("ENRICHMENT COMPLETE")
        self.logger.info(f"Total products: {total_stats['total_products']}")
        self.logger.info(
            f"Pattern match wins: {self.match_counters['pattern_match_wins_count']}; "
            f"Contains match wins: {self.match_counters['contains_match_wins_count']}; "
            f"Parent fallback count: {self.match_counters['parent_fallback_count']}"
        )
        self.logger.info(f"Duration: {duration:.2f}s")
        self.logger.info(f"Summary saved: {summary_file}")
        self.logger.info("=" * 50)

        return summary

def _verify_working_directory(config_path: str) -> None:
    """
    Verify that relative paths in config will resolve correctly from CWD.
    Prevents loading empty DBs and producing garbage enrichment.
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return  # Config errors handled later by SupplementEnricherV3

    db_paths = config.get("database_paths", {})
    if db_paths:
        first_db_path = next(iter(db_paths.values()), None)
        if first_db_path and not os.path.isabs(first_db_path):
            db_dir = os.path.dirname(first_db_path)
            if db_dir and not os.path.exists(db_dir):
                print("\n❌ WORKING DIRECTORY ERROR", file=sys.stderr)
                print(f"   Current directory: {os.getcwd()}", file=sys.stderr)
                print(f"   Expected '{db_dir}/' does not exist here.", file=sys.stderr)
                print("\n   Solution: cd to scripts/ and run again.\n", file=sys.stderr)
                sys.exit(1)



def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='DSLD Supplement Enrichment System v3.0.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python enrich_supplements_v3.py
    python enrich_supplements_v3.py --config config/enrichment_config.json
    python enrich_supplements_v3.py --input-dir cleaned_data --output-dir enriched_output
    python enrich_supplements_v3.py --dry-run
        """
    )

    parser.add_argument('--config', default='config/enrichment_config.json',
                        help='Configuration file path')
    parser.add_argument('--input-dir', help='Input directory (overrides config)')
    parser.add_argument('--output-dir', help='Output directory (overrides config)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Test run without writing files')

    args = parser.parse_args()

    # GUARD: Verify working directory before anything else
    _verify_working_directory(args.config)

    try:
        # Initialize enricher
        enricher = SupplementEnricherV3(args.config)

        # Determine paths
        if args.input_dir and args.output_dir:
            input_path = args.input_dir
            output_dir = args.output_dir
        else:
            paths = enricher.config.get('paths', {})
            input_path = paths.get('input_directory', 'output_Lozenges/cleaned')
            output_dir = paths.get('output_directory', 'output_Lozenges_enriched')

        if args.dry_run:
            enricher.logger.info("DRY RUN MODE")
            enricher.logger.info(f"Would process files from: {input_path}")
            enricher.logger.info(f"Would output to: {output_dir}")
            return

        # Process all files
        enricher.process_all(input_path, output_dir)

    except FileNotFoundError as e:
        logging.error(f"File or directory not found: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON file: {e}")
        sys.exit(1)
    except PermissionError as e:
        logging.error(f"Permission denied: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logging.info("Processing interrupted by user")
        sys.exit(130)
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
