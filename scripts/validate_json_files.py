import os
import json
import logging
from jsonschema import validate, ValidationError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    filename='/Users/seancheick/Downloads/dsld_clean/json_validation.log',
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# JSON asset paths
DATA_DIR = '/Users/seancheick/Downloads/dsld_clean/scripts/data'
JSON_FILES = {
    'absorption_enhancers': os.path.join(DATA_DIR, 'absorption_enhancers.json'),
    'allergens': os.path.join(DATA_DIR, 'allergens.json'),
    'backed_clinical_studies': os.path.join(DATA_DIR, 'backed_clinical_studies.json'),
    'banned_recalled_ingredients': os.path.join(DATA_DIR, 'banned_recalled_ingredients.json'),
    'ingredient_quality_map': os.path.join(DATA_DIR, 'ingredient_quality_map.json'),
    'proprietary_blends_penalty': os.path.join(DATA_DIR, 'proprietary_blends_penalty.json'),
    'rda_optimal_uls': os.path.join(DATA_DIR, 'rda_optimal_uls.json'),
    'standardized_botanicals': os.path.join(DATA_DIR, 'standardized_botanicals.json'),
    'top_manufacturers': os.path.join(DATA_DIR, 'top_manufacturers_data.json'),
    'unit_mappings': os.path.join(DATA_DIR, 'unit_mappings.json')
}

# JSON schemas (same as in main script)
SCHEMAS = {
    'absorption_enhancers': {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': {
                'id': {'type': 'string'},
                'name': {'type': 'string'},
                'aliases': {'type': 'array', 'items': {'type': 'string'}},
                'enhances': {'type': 'array', 'items': {'type': 'string'}},
                'score_contribution': {'type': 'integer'}
            },
            'required': ['id', 'name', 'enhances', 'score_contribution']
        }
    },
    'allergens': {
        'type': 'object',
        'properties': {
            'common_allergens': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'string'},
                        'standard_name': {'type': 'string'},
                        'aliases': {'type': 'array', 'items': {'type': 'string'}},
                        'severity_level': {'type': 'string'},
                        'regulatory_status': {'type': 'string'}
                    },
                    'required': ['id', 'standard_name', 'severity_level']
                }
            }
        },
        'required': ['common_allergens']
    },
    'backed_clinical_studies': {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': {
                'id': {'type': 'string'},
                'standard_name': {'type': 'string'},
                'aliases': {'type': 'array', 'items': {'type': 'string'}},
                'published_studies': {'type': 'array', 'items': {'type': 'string'}},
                'score_contribution': {'type': 'integer'},
                'notes': {'type': 'string'},
                'category': {'type': 'string'}
            },
            'required': ['id', 'standard_name', 'published_studies']
        }
    },
    'banned_recalled_ingredients': {
        'type': 'object',
        'properties': {
            'permanently_banned': {'type': 'array', 'items': {'type': 'object'}},
            'high_risk_ingredients': {'type': 'array', 'items': {'type': 'object'}},
            'illegal_spiking_agents': {'type': 'array', 'items': {'type': 'object'}}
        }
    },
    'ingredient_quality_map': {
        'type': 'object',
        'additionalProperties': {
            'type': 'object',
            'properties': {
                'standard_name': {'type': 'string'},
                'forms': {
                    'type': 'object',
                    'additionalProperties': {
                        'type': 'object',
                        'properties': {
                            'bio_score': {'type': 'integer'},
                            'natural': {'type': 'boolean'},
                            'aliases': {'type': 'array', 'items': {'type': 'string'}}
                        }
                    }
                }
            }
        }
    },
    'proprietary_blends_penalty': {
        'type': 'object',
        'properties': {
            'proprietary_blend_concerns': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'string'},
                        'red_flag_terms': {'type': 'array', 'items': {'type': 'string'}},
                        'penalties': {'type': 'array', 'items': {'type': 'object'}}
                    }
                }
            }
        }
    },
    'rda_optimal_uls': {
        'type': 'object',
        'properties': {
            'database_info': {
                'type': 'object',
                'properties': {
                    'version': {'type': 'string'},
                    'last_updated': {'type': 'string'},
                    'total_nutrients': {'type': 'integer'},
                    'data_source': {'type': 'string'},
                    'country': {'type': 'string'},
                    'age_brackets': {'type': 'array', 'items': {'type': 'string'}},
                    'units_verified': {'type': 'boolean'},
                    'notes': {'type': 'string'}
                }
            },
            'nutrient_recommendations': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'standard_name': {'type': 'string'},
                        'unit': {'type': 'string'},
                        'ul_note': {'type': 'string'},
                        'optimal_range': {'type': 'string'},
                        'warnings': {'type': 'array', 'items': {'type': 'string'}},
                        'special_considerations': {'type': 'string'},
                        'deficiency_symptoms': {'type': 'array', 'items': {'type': 'string'}},
                        'toxicity_symptoms': {'type': 'array', 'items': {'type': 'string'}},
                        'interaction_warnings': {'type': 'array', 'items': {'type': 'string'}},
                        'smoker_adjustment': {'type': 'string'},
                        'data': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'group': {'type': 'string'},
                                    'age_range': {'type': 'string'},
                                    'rda_ai': {'type': ['number', 'null']},
                                    'ul': {'type': ['number', 'string', 'null']}
                                },
                                'required': ['group', 'age_range']
                            }
                        }
                    },
                    'required': ['standard_name', 'data']
                }
            }
        },
        'required': ['nutrient_recommendations']
    },
    'standardized_botanicals': {
        'type': 'object',
        'properties': {
            'standardized_botanicals': {
                'type': 'object',
                'additionalProperties': {'type': 'array', 'items': {'type': 'string'}}
            }
        }
    },
    'unit_mappings': {
        'type': 'object',
        'additionalProperties': {
            'type': 'object',
            'additionalProperties': {
                'type': 'object',
                'properties': {
                    'amount': {'type': ['number', 'null']},
                    'unit': {'type': 'string'},
                    'notes': {'type': 'string'}
                },
                'required': ['amount', 'unit']
            }
        }
    },
    'top_manufacturers': {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': {
                'id': {'type': 'string'},
                'standard_name': {'type': 'string'},
                'aka': {'type': 'array', 'items': {'type': 'string'}},
                'score_contribution': {'type': 'integer'},
                'evidence': {'type': 'array', 'items': {'type': 'string'}},
                'notes': {'type': 'string'},
                'last_updated': {'type': 'string'}
            },
            'required': ['id', 'standard_name', 'score_contribution']
        }
    }
}

def load_json_asset(filepath):
    """Loads a JSON file with error handling."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading {filepath}: {e}")
        return None

def validate_json_asset(data, schema, filepath):
    """Validates JSON data against a schema."""
    try:
        validate(instance=data, schema=schema)
        logger.info(f"Validation successful for {filepath}")
        return True
    except ValidationError as e:
        logger.error(f"Validation failed for {filepath}: {e}")
        return False

def validate_all_json_files():
    """Validates all JSON files against their schemas."""
    for schema_key, filepath in JSON_FILES.items():
        data = load_json_asset(filepath)
        if data is None:
            logger.error(f"Skipping validation for {filepath} due to load failure")
            continue
        validate_json_asset(data, SCHEMAS[schema_key], filepath)

if __name__ == "__main__":
    validate_all_json_files()