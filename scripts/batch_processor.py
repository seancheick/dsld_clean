"""
DSLD Batch Processor Module
Handles batch processing, multiprocessing, and state management
"""
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from collections import Counter
from dataclasses import dataclass, asdict

from enhanced_normalizer import EnhancedDSLDNormalizer
from dsld_validator import DSLDValidator, check_completeness
from constants import (
    STATUS_SUCCESS,
    STATUS_NEEDS_REVIEW,
    STATUS_INCOMPLETE,
    STATUS_ERROR,
    OUTPUT_EXTENSION,
    VALID_INPUT_EXTENSIONS
)

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a single file"""
    success: bool
    status: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    file_path: Optional[str] = None
    processing_time: float = 0.0
    unmapped_ingredients: Optional[List[str]] = None


@dataclass
class BatchState:
    """State tracking for batch processing"""
    started: str
    last_updated: str
    last_completed_batch: int
    total_batches: int
    processed_files: int
    total_files: int
    errors: List[str]
    can_resume: bool
    config_checksum: str


class BatchProcessor:
    """Manages batch processing of DSLD files"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.batch_size = config["processing"]["batch_size"]
        self.max_workers = config["processing"]["max_workers"]
        self.output_dir = Path(config["paths"]["output_directory"])
        self.log_dir = Path(config["paths"]["log_directory"])
        
        # Create output directories
        self._create_directories()
        
        # Initialize state
        self.state_file = self.log_dir / "processing_state.json"
        
        # Global counters for unmapped and mapped ingredients
        self.global_unmapped = Counter()
        self.global_mapped = Counter()

        # Remove shared normalizer instance for thread safety
        # Each process will create its own normalizer instance
        
    def _create_directories(self):
        """Create necessary output directories"""
        dirs = [
            self.output_dir / "cleaned",
            self.output_dir / "needs_review", 
            self.output_dir / "incomplete",
            self.output_dir / "unmapped",
            self.log_dir,
            Path(self.config["paths"]["output_directory"]) / "reports"
        ]
        
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_input_files(self, input_directory: str) -> List[Path]:
        """Get list of input DSLD JSON files"""
        input_path = Path(input_directory)
        if not input_path.exists():
            raise FileNotFoundError(f"Input directory not found: {input_directory}")
        
        files = []
        for ext in VALID_INPUT_EXTENSIONS:
            files.extend(input_path.glob(f"*{ext}"))
        
        # Sort for consistent processing order
        files.sort()
        
        logger.info(f"Found {len(files)} input files")
        return files
    
    def load_state(self) -> Optional[BatchState]:
        """Load processing state if exists"""
        if not self.state_file.exists():
            return None
        
        try:
            with open(self.state_file, 'r') as f:
                state_data = json.load(f)
            return BatchState(**state_data)
        except Exception as e:
            logger.error(f"Failed to load state: {str(e)}")
            return None
    
    def save_state(self, state: BatchState):
        """Save processing state"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(asdict(state), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {str(e)}")
    
    def create_initial_state(self, total_files: int) -> BatchState:
        """Create initial processing state"""
        total_batches = (total_files + self.batch_size - 1) // self.batch_size
        
        return BatchState(
            started=datetime.utcnow().isoformat() + "Z",
            last_updated=datetime.utcnow().isoformat() + "Z",
            last_completed_batch=-1,  # -1 means no batches completed yet
            total_batches=total_batches,
            processed_files=0,
            total_files=total_files,
            errors=[],
            can_resume=True,
            config_checksum=self._get_config_checksum()
        )
    
    def _get_config_checksum(self) -> str:
        """Get checksum of config for validation"""
        config_str = json.dumps(self.config, sort_keys=True)
        import hashlib
        return hashlib.md5(config_str.encode()).hexdigest()
    
    def process_all_files(self, files: List[Path], resume: bool = False) -> Dict[str, Any]:
        """Process all files in batches"""
        start_time = time.time()
        
        # Load or create state
        state = None
        if resume:
            state = self.load_state()
            if state and state.config_checksum != self._get_config_checksum():
                logger.warning("Config changed since last run, starting fresh")
                state = None
        
        if not state:
            state = self.create_initial_state(len(files))
        
        logger.info(f"Processing {len(files)} files in {state.total_batches} batches")
        logger.info(f"Batch size: {self.batch_size}, Max workers: {self.max_workers}")
        
        if resume and state.last_completed_batch >= 0:
            logger.info(f"Resuming from batch {state.last_completed_batch + 1}")
        
        # Process batches
        batch_results = []
        start_batch = state.last_completed_batch + 1
        
        for batch_num in range(start_batch, state.total_batches):
            batch_start = batch_num * self.batch_size
            batch_end = min(batch_start + self.batch_size, len(files))
            batch_files = files[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_num + 1}/{state.total_batches} ({len(batch_files)} files)")
            
            # Process batch
            batch_result = self.process_batch(batch_num, batch_files)
            batch_results.append(batch_result)
            
            # Update state
            state.last_completed_batch = batch_num
            state.processed_files += len(batch_files)
            state.last_updated = datetime.utcnow().isoformat() + "Z"
            state.errors.extend(batch_result.get("errors", []))
            self.save_state(state)
            
            # Log batch completion
            logger.info(f"Batch {batch_num + 1} complete: {batch_result['summary']}")
        
        # Generate final summary
        total_time = time.time() - start_time
        summary = self._generate_final_summary(batch_results, total_time)
        
        # Save unmapped ingredients
        self._save_unmapped_ingredients()
        
        # Generate processing report
        self._generate_processing_report(summary, batch_results)
        
        # Generate detailed review report
        self._generate_detailed_review_report()
        
        logger.info(f"Processing complete! Total time: {total_time:.2f}s")
        
        return summary
    
    def process_batch(self, batch_num: int, files: List[Path]) -> Dict[str, Any]:
        """Process a single batch of files"""
        batch_start_time = time.time()
        
        # Create batch logger
        batch_log_file = self.log_dir / f"batch_{batch_num + 1}_log.txt"
        batch_logger = self._create_batch_logger(batch_log_file)
        
        batch_logger.info(f"=== Batch {batch_num + 1} Processing Log ===")
        batch_logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        batch_logger.info(f"Files: {files[0].name} to {files[-1].name}")
        
        # Containers for results
        cleaned_products = []
        needs_review_products = []
        incomplete_products = []
        errors = []
        batch_unmapped = Counter()
        batch_mapped = Counter()
        
        # Process files
        if self.max_workers == 1:
            # Single-threaded processing
            for file_path in files:
                result = process_single_file(str(file_path), str(self.output_dir))
                self._categorize_result(
                    result, 
                    cleaned_products, 
                    needs_review_products, 
                    incomplete_products, 
                    errors,
                    batch_unmapped,
                    batch_mapped
                )
        else:
            # Multi-threaded processing
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all jobs
                future_to_file = {
                    executor.submit(process_single_file, str(f), str(self.output_dir)): f 
                    for f in files
                }
                
                # Collect results
                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]
                    try:
                        result = future.result()
                        self._categorize_result(
                            result, 
                            cleaned_products, 
                            needs_review_products, 
                            incomplete_products, 
                            errors,
                            batch_unmapped,
                            batch_mapped
                        )
                    except Exception as e:
                        error_msg = f"Failed to process {file_path}: {str(e)}"
                        errors.append(error_msg)
                        batch_logger.error(error_msg)
        
        # Update global counters
        self.global_unmapped.update(batch_unmapped)
        self.global_mapped.update(batch_mapped)
        
        # Write batch outputs
        self._write_batch_outputs(batch_num, cleaned_products, needs_review_products, incomplete_products)
        
        # Log batch summary
        batch_time = time.time() - batch_start_time
        summary = {
            "batch_num": batch_num + 1,
            "processed": len(files),
            "cleaned": len(cleaned_products),
            "needs_review": len(needs_review_products),
            "incomplete": len(incomplete_products),
            "errors": len(errors),
            "processing_time": batch_time,
            "avg_time_per_file": batch_time / len(files) if files else 0
        }
        
        batch_logger.info(f"Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        batch_logger.info(f"Summary: {summary}")
        batch_logger.info(f"Unmapped ingredients: {len(batch_unmapped)}")
        
        if errors:
            batch_logger.info("Errors:")
            for error in errors:
                batch_logger.error(f"  - {error}")
        
        return {
            "summary": summary,
            "errors": errors,
            "unmapped_count": len(batch_unmapped)
        }
    
    def _categorize_result(self, result: ProcessingResult, cleaned: List, 
                          needs_review: List, incomplete: List, errors: List,
                          batch_unmapped: Counter, batch_mapped: Counter = None):
        """Categorize processing result into appropriate list"""
        if not result.success:
            errors.append(f"{result.file_path}: {result.error}")
            return
        
        # Update unmapped ingredients
        if result.unmapped_ingredients:
            batch_unmapped.update(result.unmapped_ingredients)
        
        # Extract and count mapped ingredients from the processed data
        if batch_mapped is not None and result.data:
            self._extract_mapped_ingredients(result.data, batch_mapped)
        
        # Categorize by status
        if result.status == STATUS_SUCCESS:
            cleaned.append(result.data)
        elif result.status == STATUS_NEEDS_REVIEW:
            needs_review.append(result.data)
        elif result.status == STATUS_INCOMPLETE:
            incomplete.append(result.data)
        else:
            errors.append(f"{result.file_path}: Unknown status {result.status}")
    
    def _extract_mapped_ingredients(self, product_data: Dict, batch_mapped: Counter):
        """Extract mapped ingredients from processed product data"""
        # Count active ingredients
        active_ingredients = product_data.get('activeIngredients', [])
        for ingredient in active_ingredients:
            ingredient_name = ingredient.get('name', '').strip()
            if ingredient_name and ingredient.get('mapped', False):
                batch_mapped[ingredient_name] += 1
        
        # Count inactive ingredients  
        inactive_ingredients = product_data.get('inactiveIngredients', [])
        for ingredient in inactive_ingredients:
            ingredient_name = ingredient.get('name', '').strip()
            if ingredient_name and ingredient.get('mapped', False):
                batch_mapped[ingredient_name] += 1
    
    def _write_batch_outputs(self, batch_num: int, cleaned: List, 
                           needs_review: List, incomplete: List):
        """Write batch outputs to JSON files"""
        batch_suffix = f"_batch_{batch_num + 1}"
        use_jsonl = self.config.get("output_format", {}).get("use_jsonl", False)
        file_extension = ".jsonl" if use_jsonl else ".json"
        
        # Write cleaned products
        if cleaned:
            output_file = self.output_dir / "cleaned" / f"cleaned{batch_suffix}{file_extension}"
            self._write_json_output(output_file, cleaned, use_jsonl)
        
        # Write needs review
        if needs_review:
            output_file = self.output_dir / "needs_review" / f"needs_review{batch_suffix}{file_extension}"
            self._write_json_output(output_file, needs_review, use_jsonl)
        
        # Write incomplete
        if incomplete:
            output_file = self.output_dir / "incomplete" / f"incomplete{batch_suffix}{file_extension}"
            self._write_json_output(output_file, incomplete, use_jsonl)
    
    def _write_json_output(self, file_path: Path, data: List[Dict], use_jsonl: bool = False):
        """Write data to JSON or JSONL file based on configuration"""
        try:
            pretty_print = self.config.get("output_format", {}).get("pretty_print", False)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                if use_jsonl:
                    # JSONL format: one JSON object per line
                    for item in data:
                        f.write(json.dumps(item, ensure_ascii=False) + '\n')
                else:
                    # Standard JSON array format
                    if pretty_print:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    else:
                        json.dump(data, f, ensure_ascii=False)
                        
            logger.debug(f"Wrote {len(data)} items to {file_path}")
        except Exception as e:
            logger.error(f"Failed to write {file_path}: {str(e)}")
    
    def _write_jsonl(self, file_path: Path, data: List[Dict]):
        """Legacy method for backward compatibility"""
        self._write_json_output(file_path, data, use_jsonl=True)
    
    def _save_unmapped_ingredients(self):
        """Save cumulative unmapped ingredients using enhanced tracking"""
        # Create a temporary normalizer to process the global unmapped ingredients
        temp_normalizer = EnhancedDSLDNormalizer()
        temp_normalizer.set_output_directory(self.output_dir)
        
        # Transfer global unmapped data to the normalizer
        temp_normalizer.unmapped_ingredients = self.global_unmapped.copy()
        
        # We need to reconstruct the details from what we have
        # Since batch processing doesn't track active/inactive status globally,
        # we'll create a basic fallback
        temp_normalizer.unmapped_details = {}
        for name, count in self.global_unmapped.items():
            temp_normalizer.unmapped_details[name] = {
                "processed_name": name.lower(),
                "forms": [],
                "variations_tried": [],
                "is_active": False  # Default to inactive since we can't determine from global counter
            }
        
        # Process and save with enhanced tracking
        try:
            result = temp_normalizer.process_and_save_unmapped_tracking()
            logger.info(f"Saved enhanced unmapped tracking files: {result['total_count']} total ingredients")
            logger.info(f"  Active: {result['active_count']}, Inactive: {result['inactive_count']}")
        except Exception as e:
            logger.error(f"Failed to save enhanced unmapped ingredients: {str(e)}")
            
            # Fallback to original method
            unmapped_data = {
                "unmapped": [
                    {
                        "name": name,
                        "occurrences": count,
                        "firstSeen": datetime.utcnow().isoformat() + "Z"
                    }
                    for name, count in self.global_unmapped.most_common()
                ],
                "stats": {
                    "totalUnmapped": len(self.global_unmapped),
                    "totalOccurrences": sum(self.global_unmapped.values()),
                    "generatedAt": datetime.utcnow().isoformat() + "Z"
                }
            }
            
            output_file = self.output_dir / "unmapped" / "unmapped_ingredients.json"
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(unmapped_data, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved fallback unmapped ingredients: {len(self.global_unmapped)}")
            except Exception as fallback_error:
                logger.error(f"Failed to save fallback unmapped ingredients: {str(fallback_error)}")
    
    def _generate_final_summary(self, batch_results: List[Dict], total_time: float) -> Dict[str, Any]:
        """Generate final processing summary"""
        total_processed = sum(r["summary"]["processed"] for r in batch_results)
        total_cleaned = sum(r["summary"]["cleaned"] for r in batch_results)
        total_needs_review = sum(r["summary"]["needs_review"] for r in batch_results)
        total_incomplete = sum(r["summary"]["incomplete"] for r in batch_results)
        total_errors = sum(r["summary"]["errors"] for r in batch_results)
        
        return {
            "processing_complete": True,
            "total_files": total_processed,
            "results": {
                "cleaned": total_cleaned,
                "needs_review": total_needs_review,
                "incomplete": total_incomplete,
                "errors": total_errors
            },
            "processing_time": {
                "total_seconds": total_time,
                "total_minutes": total_time / 60,
                "avg_per_file": total_time / total_processed if total_processed else 0
            },
            "unmapped_ingredients": len(self.global_unmapped),
            "mapped_ingredients": len(self.global_mapped),
            "success_rate": (total_cleaned / total_processed * 100) if total_processed else 0
        }
    
    def _generate_processing_report(self, summary: Dict, batch_results: List[Dict]):
        """Generate detailed processing report"""
        report_file = Path(self.config["paths"]["output_directory"]) / "reports" / "processing_summary.txt"
        
        try:
            with open(report_file, 'w') as f:
                f.write("DSLD Data Cleaning Processing Report\n")
                f.write("=" * 50 + "\n\n")
                
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Files Processed: {summary['total_files']}\n")
                f.write(f"Processing Time: {summary['processing_time']['total_minutes']:.2f} minutes\n\n")
                
                f.write("Results Summary:\n")
                f.write(f"  - Successfully cleaned: {summary['results']['cleaned']}\n")
                f.write(f"  - Needs review: {summary['results']['needs_review']}\n") 
                f.write(f"  - Incomplete: {summary['results']['incomplete']}\n")
                f.write(f"  - Errors: {summary['results']['errors']}\n")
                f.write(f"  - Success rate: {summary['success_rate']:.1f}%\n\n")
                
                f.write(f"Mapped ingredients found: {summary['mapped_ingredients']}\n")
                f.write(f"Unmapped ingredients found: {summary['unmapped_ingredients']}\n\n")

                # Add top mapped ingredients for data insights
                if self.global_mapped:
                    f.write("Top 15 Mapped Ingredients (data insights):\n")
                    for ingredient, count in self.global_mapped.most_common(15):
                        f.write(f"  {count:>3}x {ingredient}\n")
                    f.write("\n📊 These are the most frequently appearing mapped ingredients\n\n")
                
                # Add top unmapped ingredients for enrichment planning
                if self.global_unmapped:
                    f.write("Top 10 Unmapped Ingredients (for enrichment planning):\n")
                    for ingredient, count in self.global_unmapped.most_common(10):
                        f.write(f"  {count:>3}x {ingredient}\n")
                    f.write("\n💡 These ingredients should be prioritized for database enrichment\n\n")

                f.write("Batch Details:\n")
                for i, batch in enumerate(batch_results):
                    s = batch["summary"]
                    f.write(f"  Batch {s['batch_num']}: {s['cleaned']} cleaned, "
                           f"{s['needs_review']} review, {s['incomplete']} incomplete, "
                           f"{s['errors']} errors ({s['processing_time']:.1f}s)\n")
                
            logger.info(f"Processing report saved to {report_file}")
        except Exception as e:
            logger.error(f"Failed to generate report: {str(e)}")
    
    def _generate_detailed_review_report(self):
        """Generate detailed review report for products needing manual attention"""
        needs_review_dir = self.output_dir / "needs_review"
        report_file = Path(self.config["paths"]["output_directory"]) / "reports" / "detailed_review_report.md"
        
        try:
            # Find all needs_review files (both .json and .jsonl)
            review_files = list(needs_review_dir.glob("*.json*"))
            if not review_files:
                logger.info("No products need review - skipping detailed review report")
                return
            
            # Load all products needing review
            review_products = []
            for file_path in review_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content.startswith('['):
                            # JSON array format
                            products = json.loads(content)
                            review_products.extend(products)
                        else:
                            # JSONL format
                            for line in content.split('\n'):
                                if line.strip():
                                    product = json.loads(line.strip())
                                    review_products.append(product)
                except Exception as e:
                    logger.warning(f"Could not read review file {file_path}: {str(e)}")
            
            if not review_products:
                logger.info("No products found in review files")
                return
            
            # Generate the report
            self._write_detailed_review_report(report_file, review_products)
            logger.info(f"Detailed review report saved to {report_file}")
            
        except Exception as e:
            logger.error(f"Failed to generate detailed review report: {str(e)}")
    
    def _write_detailed_review_report(self, report_file: Path, review_products: List[Dict]):
        """Write the detailed review report in markdown format"""
        from datetime import datetime
        
        with open(report_file, 'w', encoding='utf-8') as f:
            # Header
            f.write("# DSLD Products Requiring Manual Review\n")
            f.write(f"**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n")
            f.write(f"**Total Products Needing Review:** {len(review_products)}\n\n")
            
            # Summary
            f.write("## Summary\n")
            f.write("Products are flagged for review when they have:\n")
            f.write("- **Low ingredient mapping rates** (below 75% mapped ingredients)\n")
            f.write("- **Missing important fields** (like UPC codes, contact info)\n")
            f.write("- **High numbers of unmapped ingredients** requiring manual curation\n\n")
            f.write("---\n\n")
            
            # Process each product
            for i, product in enumerate(review_products, 1):
                self._write_product_review_section(f, product, i)
            
            # Action items summary
            self._write_action_items_summary(f, review_products)
            
            # Files location
            f.write("---\n\n")
            f.write("## Files Location:\n")
            f.write("- **Detailed products:** `output/needs_review/needs_review_batch_*.jsonl`\n")
            f.write("- **Full unmapped ingredients list:** `output/unmapped/unmapped_ingredients.json`\n")
            f.write("- **This report:** `output/reports/detailed_review_report.md`\n")
    
    def _write_product_review_section(self, f, product: Dict, product_num: int):
        """Write individual product review section"""
        # Basic info
        f.write(f"## Product {product_num}: {product.get('fullName', 'Unknown Product')}\n")
        f.write(f"**Product ID:** {product.get('id', 'Unknown')}\n")
        f.write(f"**Brand:** {product.get('brandName', 'Unknown')}\n")
        
        # Status
        status = product.get('status', 'unknown')
        if status == 'discontinued':
            f.write(f"**Status:** ⚠️ **DISCONTINUED**")
            if product.get('discontinuedDate'):
                f.write(f" (Off market as of {product.get('discontinuedDate')[:10]})")
            f.write("\n\n")
        else:
            f.write(f"**Status:** ✅ **ACTIVE**\n\n")
        
        # Completeness and mapping info
        completeness = product.get('metadata', {}).get('completeness', {})
        mapping_stats = product.get('metadata', {}).get('mappingStats', {})
        
        f.write("### Why It Needs Review:\n")
        f.write(f"- **Completeness score:** {completeness.get('score', 0):.1f}%")
        if completeness.get('score', 0) >= 90:
            f.write(" ✅\n")
        else:
            f.write(" ⚠️\n")
        
        f.write(f"- **Critical fields complete:** ")
        if completeness.get('criticalFieldsComplete', False):
            f.write("✅\n")
        else:
            f.write("❌\n")
        
        mapping_rate = mapping_stats.get('mappingRate', 0)
        f.write(f"- **Ingredient mapping:** {mapping_rate:.1f}% ")
        f.write(f"({mapping_stats.get('mappedIngredients', 0)} out of {mapping_stats.get('totalIngredients', 0)} ingredients mapped)")
        if mapping_rate >= 75:
            f.write(" ✅\n\n")
        else:
            f.write(" ⚠️\n\n")
        
        # Issues to address
        f.write("### Issues to Address:\n\n")
        
        # Missing fields
        missing_fields = completeness.get('missingFields', [])
        if missing_fields:
            # Import constants to check field categorization
            from constants import REQUIRED_FIELDS

            # Categorize missing fields
            missing_critical = [f for f in missing_fields if f in REQUIRED_FIELDS["critical"]]
            missing_important = [f for f in missing_fields if f in REQUIRED_FIELDS["important"]]
            missing_optional = [f for f in missing_fields if f in REQUIRED_FIELDS["optional"]]

            if missing_critical or missing_important:
                f.write("#### 1. Missing Critical Information:\n")

                # Handle critical fields
                for field in missing_critical:
                    f.write(f"- **{field}:** Missing critical field\n")

                # Handle important fields
                for field in missing_important:
                    if field == 'upcSku':
                        f.write("- **UPC/SKU Code:** Product has no barcode information\n")
                        f.write("  - **Impact:** Cannot be properly tracked in retail systems\n")
                        f.write("  - **Action:** Contact manufacturer to obtain UPC code\n")
                    else:
                        f.write(f"- **{field}:** Missing important field\n")

                f.write("\n")

            # Handle optional fields separately (informational only)
            if missing_optional:
                f.write("#### Additional Information (Optional Fields):\n")
                for field in missing_optional:
                    f.write(f"- **{field}:** Optional field not present\n")
                f.write("\n")
        
        # Unmapped ingredients
        unmapped_count = mapping_stats.get('unmappedIngredients', 0)
        if unmapped_count > 0:
            if missing_fields:
                f.write("#### 2. ")
            else:
                f.write("#### 1. ")
            
            if unmapped_count <= 5:
                f.write(f"Unmapped Ingredients Need Manual Review ({unmapped_count} total):\n")
            else:
                f.write(f"Many Unmapped Ingredients ({unmapped_count} total):\n")
            
            # Get unmapped ingredient names from the product data
            unmapped_ingredients = self._extract_unmapped_ingredients_from_product(product)
            
            if unmapped_count <= 10:
                for ingredient in unmapped_ingredients[:10]:
                    f.write(f"   - **{ingredient}** - Should be added to ingredient database\n")
            else:
                # Group by category for complex products
                f.write("\n**Key Missing Ingredients:**\n")
                for ingredient in unmapped_ingredients[:15]:
                    f.write(f"   - {ingredient}\n")
                if len(unmapped_ingredients) > 15:
                    f.write(f"   - ... and {len(unmapped_ingredients) - 15} more\n")
            f.write("\n")
        
        # Recommendation
        f.write("### Recommendation:\n")
        if status == 'discontinued':
            f.write("- **Priority:** Medium (product is discontinued)\n")
        elif mapping_rate < 60:
            f.write("- **Priority:** HIGH (active product with many missing ingredients)\n")
        else:
            f.write("- **Priority:** Medium (active product with some missing ingredients)\n")
        
        if unmapped_count > 0:
            f.write(f"- **Action:** Add the {unmapped_count} missing ingredients to your reference database\n")
        if missing_fields:
            f.write(f"- **Action:** Obtain missing information: {', '.join(missing_fields)}\n")
        f.write("- **Impact:** Will improve mapping for future similar products\n\n")
        f.write("---\n\n")
    
    def _extract_unmapped_ingredients_from_product(self, product: Dict) -> List[str]:
        """Extract names of unmapped ingredients from a product"""
        unmapped = []
        
        # Check active ingredients
        for ingredient in product.get('activeIngredients', []):
            if not ingredient.get('mapped', True):
                unmapped.append(ingredient.get('name', 'Unknown'))
        
        # Check inactive ingredients  
        for ingredient in product.get('inactiveIngredients', []):
            if not ingredient.get('mapped', True):
                unmapped.append(ingredient.get('name', 'Unknown'))
        
        return unmapped
    
    def _write_action_items_summary(self, f, review_products: List[Dict]):
        """Write action items summary section"""
        f.write("## Action Items Summary\n\n")
        
        high_priority = []
        medium_priority = []
        low_priority = []
        
        total_unmapped = 0
        missing_upc_count = 0
        
        for product in review_products:
            completeness = product.get('metadata', {}).get('completeness', {})
            mapping_stats = product.get('metadata', {}).get('mappingStats', {})
            
            unmapped_count = mapping_stats.get('unmappedIngredients', 0)
            total_unmapped += unmapped_count
            
            missing_fields = completeness.get('missingFields', [])
            if 'upcSku' in missing_fields:
                missing_upc_count += 1
            
            mapping_rate = mapping_stats.get('mappingRate', 0)
            is_active = product.get('status', 'active') == 'active'
            
            product_name = product.get('fullName', 'Unknown')
            product_id = product.get('id', 'Unknown')
            
            if is_active and mapping_rate < 60:
                high_priority.append(f"**{product_name}** (ID: {product_id}) - {unmapped_count} ingredients to add")
            elif is_active and unmapped_count > 0:
                medium_priority.append(f"**{product_name}** (ID: {product_id}) - {unmapped_count} ingredients to add")
            elif unmapped_count > 0:
                low_priority.append(f"**{product_name}** (ID: {product_id}) - {unmapped_count} ingredients to add")
        
        if high_priority:
            f.write("### High Priority:\n")
            for item in high_priority:
                f.write(f"1. {item}\n")
            f.write("\n")
        
        if medium_priority:
            f.write("### Medium Priority:\n")
            for item in medium_priority:
                f.write(f"1. {item}\n")
            f.write("\n")
        
        if low_priority:
            f.write("### Low Priority:\n")
            for item in low_priority:
                f.write(f"1. {item}\n")
            f.write("\n")
        
        if missing_upc_count > 0:
            f.write("### Additional Actions:\n")
            f.write(f"- **Obtain UPC codes** for {missing_upc_count} products\n\n")
        
        # Impact summary
        f.write("### Expected Impact:\n")
        total_ingredients = sum(p.get('metadata', {}).get('mappingStats', {}).get('totalIngredients', 0) for p in review_products)
        total_mapped = sum(p.get('metadata', {}).get('mappingStats', {}).get('mappedIngredients', 0) for p in review_products)
        
        if total_ingredients > 0:
            current_rate = (total_mapped / total_ingredients) * 100
            potential_rate = ((total_mapped + total_unmapped) / total_ingredients) * 100
            f.write(f"- **Current mapping rate:** {current_rate:.1f}% ({total_mapped} mapped out of {total_ingredients} total ingredients)\n")
            f.write(f"- **After improvements:** ~{potential_rate:.1f}% ({total_unmapped} more ingredients would be mapped)\n")
            f.write("- **Benefit:** Much better data quality for future similar products\n\n")
    
    def _create_batch_logger(self, log_file: Path) -> logging.Logger:
        """Create batch-specific logger"""
        logger_name = f"batch_{log_file.stem}"
        batch_logger = logging.getLogger(logger_name)
        
        # Remove existing handlers
        for handler in batch_logger.handlers[:]:
            batch_logger.removeHandler(handler)
        
        # Add file handler
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        batch_logger.addHandler(handler)
        batch_logger.setLevel(logging.INFO)
        
        return batch_logger


def process_single_file(file_path: str, output_dir: str = None) -> ProcessingResult:
    """
    Process a single DSLD file
    This function is designed to be used with multiprocessing
    """
    start_time = time.time()
    
    try:
        # Load JSON data
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # Initialize enhanced normalizer and validator (create new instances for each process)
        normalizer = EnhancedDSLDNormalizer()
        # Set output directory for enhanced unmapped tracking
        if output_dir:
            normalizer.set_output_directory(Path(output_dir))
        validator = DSLDValidator()

        # Normalize the data
        cleaned_data = normalizer.normalize_product(raw_data)
        
        # Validate the result
        status, missing_fields, validation_details = validator.validate_product(raw_data)
        
        # Get enhanced unmapped ingredients summary
        unmapped = normalizer.get_enhanced_unmapped_summary()
        unmapped_list = [item["name"] for item in unmapped["unmapped"]]
        
        # Calculate mapping statistics for final status decision
        total_ingredients = len(cleaned_data.get("activeIngredients", [])) + len(cleaned_data.get("inactiveIngredients", []))
        unmapped_count = len(unmapped_list)
        mapping_rate = ((total_ingredients - unmapped_count) / total_ingredients * 100) if total_ingredients > 0 else 100
        
        # Update metadata with validation results AND mapping stats
        cleaned_data["metadata"]["completeness"] = {
            "score": validation_details.get("completeness_score", 0),
            "missingFields": missing_fields,
            "criticalFieldsComplete": validation_details.get("critical_fields_complete", False)
        }
        
        cleaned_data["metadata"]["mappingStats"] = {
            "totalIngredients": total_ingredients,
            "mappedIngredients": total_ingredients - unmapped_count,
            "unmappedIngredients": unmapped_count,
            "mappingRate": mapping_rate
        }
        
        # IMPROVED: Adjust status based on actual mapping performance
        if status == STATUS_NEEDS_REVIEW:
            # If product has excellent mapping (90%+) and only missing UPC, promote to success
            if (mapping_rate >= 90.0 and 
                len(missing_fields) == 1 and 
                missing_fields[0] == "upcSku" and
                validation_details.get("critical_fields_complete", False)):
                status = STATUS_SUCCESS
        
        processing_time = time.time() - start_time
        
        return ProcessingResult(
            success=True,
            status=status,
            data=cleaned_data,
            file_path=file_path,
            processing_time=processing_time,
            unmapped_ingredients=unmapped_list
        )
        
    except Exception as e:
        processing_time = time.time() - start_time
        return ProcessingResult(
            success=False,
            status=STATUS_ERROR,
            error=str(e),
            file_path=file_path,
            processing_time=processing_time
        )