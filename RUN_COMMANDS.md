# DSLD Cleaning Script - Run Commands

## 🚀 Quick Start Commands

### **From the `scripts/` directory (Recommended)**

```bash
cd scripts
python clean_dsld_data.py                    # Uses config/cleaning_config.json automatically
python clean_dsld_data.py --resume           # Resume interrupted processing
python clean_dsld_data.py --dry-run          # Test run (no files written)
python clean_dsld_data.py --start-batch 5    # Start from specific batch
```

### **From the root directory**

```bash
python scripts/clean_dsld_data.py --config scripts/config/cleaning_config.json
python scripts/clean_dsld_data.py --config scripts/config/cleaning_config.json --resume
python scripts/clean_dsld_data.py --config scripts/config/cleaning_config.json --dry-run
```

## 📁 File Structure

```
Downloads/dsld_clean/
├── scripts/
│   ├── clean_dsld_data.py          # Main cleaning script
│   ├── config/
│   │   └── cleaning_config.json    # Configuration file
│   ├── data/                       # Reference databases
│   └── enhanced_normalizer.py      # Core processing engine
├── output_lozenges/                # Output directory (created automatically)
├── logs/                          # Log files (created automatically)
└── RUN_COMMANDS.md                # This file
```

## ⚙️ Configuration

The `scripts/config/cleaning_config.json` file contains all settings:

- **Input Directory**: Where your DSLD JSON files are located
- **Output Directory**: Where cleaned files will be saved
- **Processing Settings**: Batch size, workers, performance tuning
- **Validation Rules**: Field requirements and thresholds
- **Options**: Resume, dry-run, reporting settings

## 📊 What the Script Does

### **CLEANING Phase (Current)**

1. ✅ **Ingredient Mapping**: Maps ingredients to standardized names
2. ✅ **Harmful Detection**: Flags harmful additives and allergens
3. ✅ **Data Validation**: Checks completeness and quality
4. ✅ **Performance Optimization**: Fast processing with caching
5. ✅ **Unmapped Tracking**: Reports top unmapped ingredients for enrichment

### **Output Files**

- `output_lozenges/cleaned/` - Successfully processed products
- `output_lozenges/needs_review/` - Products needing manual review
- `output_lozenges/incomplete/` - Products with missing critical data
- `logs/dsld_cleaning.log` - Detailed processing logs
- `processing_report.txt` - Summary with top unmapped ingredients

## 🔄 Complete Workflow

```
1. CLEANING (this script)    → Clean and standardize data
2. ENRICHMENT (next phase)   → Add clinical data, absorption enhancers
3. SCORING (final phase)     → Calculate quality scores
4. DEPLOYMENT               → Send to supplements app & Supabase
```

## 🎯 Performance Features

- **97.9% ingredient coverage** with 9 reference databases
- **3,826+ products/second** processing speed
- **Smart caching** with 5,956x speedup for repeated operations
- **Parallel processing** for large ingredient lists
- **Memory efficient** with automatic cache limits

## 📈 Monitoring

The script provides:

- Real-time progress updates
- Processing speed metrics
- Top 10 unmapped ingredients for enrichment planning
- Detailed logs for troubleshooting
- Comprehensive final reports

## 🆘 Troubleshooting

### **Common Issues**

1. **"Input directory not found"** → Check the `input_directory` path in config
2. **"Permission denied"** → Ensure write permissions for output directory
3. **"Memory error"** → Reduce `batch_size` in config
4. **"Interrupted processing"** → Use `--resume` to continue

### **Performance Tuning**

- **Faster processing**: Increase `max_workers` (up to CPU cores)
- **Less memory usage**: Decrease `batch_size` and `chunk_size`
- **More detailed logs**: Change `logging.level` to "DEBUG"

## 📞 Support

Check the logs in `logs/dsld_cleaning.log` for detailed error information.
The processing report will show ingredient coverage and unmapped items for enrichment planning.
