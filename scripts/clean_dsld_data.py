#!/usr/bin/env python3
"""
DSLD Data Cleaning Pipeline - Main Script
=========================================

Comprehensive batch processing system for cleaning and normalizing DSLD supplement data.
Processes thousands of files efficiently with resume capability, parallel processing,
and detailed logging.

Features:
- Batch processing with configurable size
- Multiprocessing support
- Resume capability after interruption
- Comprehensive ingredient mapping and normalization
- Allergen detection with severity levels
- Harmful additive flagging
- Certification extraction
- Quality assessment and completeness scoring

Usage:
    python clean_dsld_data.py --config scripts/config/cleaning_config.json
    python clean_dsld_data.py --resume
    python clean_dsld_data.py --dry-run

Author: PharmaGuide Team
Version: 1.0.0
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent))

from batch_processor import BatchProcessor
from enhanced_normalizer import EnhancedDSLDNormalizer
from dsld_validator import DSLDValidator
from constants import LOG_FORMAT, LOG_DATE_FORMAT


class DSLDCleaningPipeline:
    """Main pipeline for DSLD data cleaning"""
    
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.logger = self._setup_logging()
        
    def _load_config(self) -> dict:
        """Load configuration file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Validate required sections
            required_sections = ["processing", "paths", "options"]
            for section in required_sections:
                if section not in config:
                    raise ValueError(f"Missing required config section: {section}")
            
            return config
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {str(e)}")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        log_config = self.config.get("logging", {})
        log_level = getattr(logging, log_config.get("level", "INFO"))
        
        # Create logger
        logger = logging.getLogger("dsld_cleaner")
        logger.setLevel(log_level)
        
        # Remove existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create formatter
        formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
        
        # Console handler
        if log_config.get("log_to_console", True):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # File handler
        if log_config.get("log_to_file", True):
            log_dir = Path(self.config["paths"]["log_directory"])
            log_dir.mkdir(parents=True, exist_ok=True)
            
            log_file = log_dir / f"dsld_cleaning_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    def validate_config(self) -> bool:
        """Validate configuration and dependencies"""
        self.logger.info("Validating configuration...")
        
        # Check input directory
        input_dir = Path(self.config["paths"]["input_directory"])
        if not input_dir.exists():
            self.logger.error(f"Input directory does not exist: {input_dir}")
            return False
        
        # Check reference data directory
        ref_dir = Path(self.config["paths"]["reference_data"])
        if not ref_dir.exists():
            self.logger.error(f"Reference data directory does not exist: {ref_dir}")
            return False
        
        # Check required reference files
        required_files = [
            "ingredient_quality_map.json",
            "harmful_additives.json", 
            "allergens.json",
            "top_manufacturers_data.json"
        ]
        
        for filename in required_files:
            file_path = ref_dir / filename
            if not file_path.exists():
                self.logger.error(f"Required reference file missing: {file_path}")
                return False
        
        # Validate processing options
        batch_size = self.config["processing"]["batch_size"]
        if batch_size <= 0:
            self.logger.error(f"Invalid batch size: {batch_size}")
            return False
        
        max_workers = self.config["processing"]["max_workers"]
        if max_workers <= 0:
            self.logger.error(f"Invalid max workers: {max_workers}")
            return False
        
        self.logger.info("Configuration validation passed")
        return True
    
    def dry_run(self) -> bool:
        """Perform dry run to check setup without processing"""
        self.logger.info("=== DRY RUN MODE ===")
        
        if not self.validate_config():
            return False
        
        # Check input files
        processor = BatchProcessor(self.config)
        input_dir = self.config["paths"]["input_directory"]
        
        try:
            files = processor.get_input_files(input_dir)
            self.logger.info(f"Found {len(files)} input files")
            
            if len(files) == 0:
                self.logger.warning("No input files found!")
                return False
            
            # Calculate batch info
            batch_size = self.config["processing"]["batch_size"]
            total_batches = (len(files) + batch_size - 1) // batch_size
            
            self.logger.info(f"Would process {len(files)} files in {total_batches} batches")
            self.logger.info(f"Batch size: {batch_size}")
            self.logger.info(f"Max workers: {self.config['processing']['max_workers']}")
            
            # Test loading reference data
            try:
                normalizer = EnhancedDSLDNormalizer()
                self.logger.info("Reference data loaded successfully")
            except Exception as e:
                self.logger.error(f"Failed to load reference data: {str(e)}")
                return False
            
            # Test processing one file
            test_file = files[0]
            self.logger.info(f"Testing processing with: {test_file.name}")
            
            try:
                with open(test_file, 'r') as f:
                    test_data = json.load(f)
                
                cleaned = normalizer.normalize_product(test_data)
                self.logger.info(f"Test processing successful - product ID: {cleaned.get('id', 'unknown')}")
                
            except Exception as e:
                self.logger.error(f"Test processing failed: {str(e)}")
                return False
            
            self.logger.info("=== DRY RUN COMPLETE - READY TO PROCESS ===")
            return True
            
        except Exception as e:
            self.logger.error(f"Dry run failed: {str(e)}")
            return False
    
    def run(self, resume: bool = False) -> bool:
        """Run the main processing pipeline"""
        self.logger.info("=" * 60)
        self.logger.info("DSLD Data Cleaning Pipeline Starting")
        self.logger.info("=" * 60)
        
        start_time = datetime.now()
        self.logger.info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Validate configuration
            if not self.validate_config():
                self.logger.error("Configuration validation failed")
                return False
            
            # Initialize processor
            processor = BatchProcessor(self.config)
            
            # Get input files
            input_dir = self.config["paths"]["input_directory"]
            files = processor.get_input_files(input_dir)
            
            if len(files) == 0:
                self.logger.error("No input files found!")
                return False
            
            # Process all files
            summary = processor.process_all_files(files, resume=resume)
            
            # Log final results
            end_time = datetime.now()
            duration = end_time - start_time
            
            self.logger.info("=" * 60)
            self.logger.info("PROCESSING COMPLETE")
            self.logger.info("=" * 60)
            self.logger.info(f"Ended at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"Total duration: {duration}")
            self.logger.info(f"Files processed: {summary['total_files']}")
            self.logger.info(f"Success rate: {summary['success_rate']:.1f}%")
            self.logger.info("")
            self.logger.info("Results:")
            self.logger.info(f"  - Cleaned: {summary['results']['cleaned']}")
            self.logger.info(f"  - Needs review: {summary['results']['needs_review']}")
            self.logger.info(f"  - Incomplete: {summary['results']['incomplete']}")
            self.logger.info(f"  - Errors: {summary['results']['errors']}")
            self.logger.info(f"  - Unmapped ingredients: {summary['unmapped_ingredients']}")
            
            # Output file locations
            output_dir = Path(self.config["paths"]["output_directory"])
            self.logger.info("")
            self.logger.info("Output files saved to:")
            self.logger.info(f"  - Cleaned products: {output_dir / 'cleaned'}")
            self.logger.info(f"  - Needs review: {output_dir / 'needs_review'}")
            self.logger.info(f"  - Incomplete: {output_dir / 'incomplete'}")
            self.logger.info(f"  - Unmapped ingredients: {output_dir / 'unmapped'}")
            self.logger.info(f"  - Processing report: {output_dir / 'reports'}")
            
            return True
            
        except KeyboardInterrupt:
            self.logger.info("Processing interrupted by user")
            self.logger.info("You can resume processing using --resume flag")
            return False
            
        except Exception as e:
            self.logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="DSLD Data Cleaning Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --config scripts/config/cleaning_config.json
  %(prog)s --resume
  %(prog)s --dry-run
  %(prog)s --config scripts/config/cleaning_config.json --start-batch 5
        """
    )
    
    # Determine default config path based on current directory
    if Path.cwd().name == "scripts":
        default_config = "config/cleaning_config.json"
        help_text = "Path to configuration file (default: config/cleaning_config.json)"
    else:
        default_config = "scripts/config/cleaning_config.json"
        help_text = "Path to configuration file (default: scripts/config/cleaning_config.json)"

    parser.add_argument(
        "--config",
        default=default_config,
        help=help_text
    )
    
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume processing from last completed batch"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and test processing without running full pipeline"
    )
    
    parser.add_argument(
        "--start-batch",
        type=int,
        help="Start processing from specific batch number"
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set up basic logging for startup
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT
    )
    
    try:
        # Initialize pipeline
        pipeline = DSLDCleaningPipeline(args.config)
        
        # Handle start batch override
        if args.start_batch is not None:
            # Load current state and modify it
            processor = BatchProcessor(pipeline.config)
            state = processor.load_state()
            if state:
                state.last_completed_batch = args.start_batch - 2  # -2 because we add 1 in processor
                processor.save_state(state)
                pipeline.logger.info(f"Set start batch to: {args.start_batch}")
            else:
                pipeline.logger.warning("No existing state found, --start-batch ignored")
        
        # Run pipeline
        if args.dry_run:
            success = pipeline.dry_run()
        else:
            success = pipeline.run(resume=args.resume)
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logging.error(f"Pipeline initialization failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()