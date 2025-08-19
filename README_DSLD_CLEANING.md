# DSLD Data Cleaning Pipeline

A comprehensive batch processing system for cleaning and normalizing DSLD (Dietary Supplement Label Database) supplement data for the PharmaGuide application.

## Features

- **Batch Processing**: Process thousands of files efficiently with configurable batch sizes
- **Multiprocessing Support**: Utilize multiple CPU cores for faster processing
- **Resume Capability**: Resume processing after interruption without losing progress
- **Comprehensive Normalization**: 
  - Ingredient mapping with aliases and forms
  - Unit conversion (IU→mcg for Vitamin D)
  - Allergen detection with severity levels
  - Harmful additive flagging
  - Certification extraction (GMP, NSF, USP, etc.)
  - Natural source identification
  - Proprietary blend detection
- **Quality Assessment**: Completeness scoring and data validation
- **Detailed Logging**: Comprehensive logging with batch-specific reports
- **Output Formats**: JSONL format for easy debugging and processing

## Installation

1. Ensure Python 3.7+ is installed
2. Install optional dependencies for better performance:
   ```bash
   pip install tqdm fuzzywuzzy python-levenshtein
   ```

## Configuration

Edit `config/cleaning_config.json` to configure processing:

```json
{
  "processing": {
    "batch_size": 1000,           // Files per batch
    "max_workers": 4,             // Parallel workers
    "resume_on_error": true,      // Resume after errors
    "skip_failed_files": true     // Skip files that can't be processed
  },
  "paths": {
    "input_directory": "/path/to/dsld/files",
    "output_directory": "./output",
    "reference_data": "./scripts/data"
  }
}
```

## Usage

### Basic Usage

```bash
# Process all files in input directory
python scripts/clean_dsld_data.py

# Use custom config file
python scripts/clean_dsld_data.py --config my_config.json
```

### Resume Processing

```bash
# Resume from last completed batch
python scripts/clean_dsld_data.py --resume
```

### Dry Run

```bash
# Test configuration without processing
python scripts/clean_dsld_data.py --dry-run
```

### Advanced Options

```bash
# Start from specific batch
python scripts/clean_dsld_data.py --start-batch 5

# Enable verbose logging
python scripts/clean_dsld_data.py --verbose
```

## Output Structure

```
output/
├── cleaned/
│   ├── cleaned_batch_1.jsonl        # Successfully processed products
│   ├── cleaned_batch_2.jsonl
│   └── ...
├── needs_review/
│   ├── needs_review_batch_1.jsonl   # Products missing 1-5 fields
│   └── ...
├── incomplete/
│   ├── incomplete_batch_1.jsonl     # Products missing >5 fields
│   └── ...
├── unmapped/
│   └── unmapped_ingredients.json    # Ingredients needing manual mapping
└── reports/
    └── processing_summary.txt       # Processing statistics
```

## Data Structure

### Cleaned Product Format

Each cleaned product includes:

```json
{
  "id": "326592",
  "fullName": "Men's Advanced Multivitamin",
  "brandName": "New Chapter",
  "upcSku": "7 07359 13802 5",
  "upcValid": true,
  "status": "active",                    // or "discontinued"
  "discontinuedDate": null,              // ISO date if discontinued
  "imageUrl": "https://api.ods.od.nih.gov/dsld/s3/pdf/326592.pdf",
  
  "activeIngredients": [
    {
      "name": "Vitamin A",
      "standardName": "Vitamin A",       // Mapped from aliases
      "quantity": 900.0,
      "unit": "mcg",
      "forms": ["Beta-Carotene"],
      "natural": true,                   // From quality map
      "allergen": false,
      "allergenSeverity": null,          // "low", "moderate", "high"
      "harmfulCategory": "none",         // Additive safety check
      "mapped": true                     // Successfully mapped
    }
  ],
  
  "statements": [
    {
      "type": "Seals/Symbols",
      "notes": "NSF Certified Gluten-Free",
      "certifications": ["NSF Gluten-Free"],
      "allergenFree": ["gluten"],
      "gmpCertified": true
    }
  ],
  
  "metadata": {
    "completeness": {
      "score": 95.2,
      "missingFields": ["images"]
    },
    "qualityFlags": {
      "hasAllergens": true,
      "allergenTypes": ["soy"],
      "hasCertifications": true,
      "certificationTypes": ["GMP", "NSF Gluten-Free"]
    }
  }
}
```

## Reference Data Files

The system uses these reference files in `scripts/data/`:

- `ingredient_quality_map.json` - Ingredient aliases and bioavailability scores
- `allergens.json` - Allergen database with severity levels
- `harmful_additives.json` - Harmful additive database
- `top_manufacturers_data.json` - Manufacturer reputation scores
- Other reference files for enhanced delivery, synergy, etc.

## Processing Statistics

Example output from a processing run:

```
Files processed: 220,000
Success rate: 87.5%

Results:
- Cleaned: 192,500
- Needs review: 22,000
- Incomplete: 4,500
- Errors: 1,000
- Unmapped ingredients: 3,247
```

## Performance

- **Speed**: ~1,000 products/minute on modern hardware
- **Memory**: Constant memory usage regardless of dataset size
- **Scalability**: Handles 220,000+ files efficiently
- **Resume**: No data loss on interruption

## Troubleshooting

### Common Issues

1. **JSON Syntax Errors in Reference Files**
   - Check logs for specific file and line number
   - Validate JSON syntax using online tools

2. **Memory Issues**
   - Reduce `batch_size` in config
   - Reduce `max_workers` 

3. **Processing Stops**
   - Use `--resume` flag to continue
   - Check batch logs in `logs/` directory

### Logging

Logs are saved to:
- `logs/dsld_cleaning_YYYYMMDD_HHMMSS.log` - Main log
- `logs/batch_N_log.txt` - Per-batch logs
- `logs/processing_state.json` - Resume state

## Integration with Scoring System

The cleaned data is designed to work seamlessly with your scoring system:

1. **Standardized Names**: All ingredients mapped to consistent names
2. **Allergen Severity**: Ready for penalty calculations
3. **Quality Flags**: Immediate access to certification status
4. **Form Information**: Bioavailability scoring ready
5. **Complete Metadata**: All information preserved for UI display

## Next Steps

After cleaning:

1. Review `unmapped_ingredients.json` and add to reference files
2. Check `needs_review/` products for missing critical data
3. Import cleaned data into your scoring pipeline
4. Update reference files based on unmapped ingredients

---

For questions or issues, check the logs directory or contact the development team.