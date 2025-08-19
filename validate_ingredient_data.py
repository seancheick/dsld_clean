#!/usr/bin/env python3
"""
Ingredient Data Validation Script
=================================

Performs comprehensive validation of harmful additives and passive inactive 
ingredients databases to ensure data consistency and prevent scoring conflicts.

Usage:
    python validate_ingredient_data.py

Author: PharmaGuide Data Quality Team
Version: 1.0.0
"""

import json
import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class IngredientDataValidator:
    """Validates ingredient data for consistency and quality"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.harmful_file = data_dir / "harmful_additives.json"
        self.passive_file = data_dir / "passive_inactive_ingredients.json"
        
        self.harmful_data = {}
        self.passive_data = {}
        
        self.errors = []
        self.warnings = []
        
    def load_data(self):
        """Load ingredient data from JSON files"""
        try:
            with open(self.harmful_file, 'r') as f:
                self.harmful_data = json.load(f)
            logger.info(f"Loaded {len(self.harmful_data.get('harmful_additives', []))} harmful additives")
            
            with open(self.passive_file, 'r') as f:
                self.passive_data = json.load(f)
            logger.info(f"Loaded {len(self.passive_data.get('passive_inactive_ingredients', []))} passive ingredients")
            
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            raise
    
    def validate_structure(self):
        """Validate basic file structure"""
        # Check harmful additives structure
        if "harmful_additives" not in self.harmful_data:
            self.errors.append("Missing 'harmful_additives' key in harmful_additives.json")
        
        # Check passive ingredients structure
        if "passive_inactive_ingredients" not in self.passive_data:
            self.errors.append("Missing 'passive_inactive_ingredients' key in passive_inactive_ingredients.json")
        
        logger.info("Structure validation complete")
    
    def check_overlaps(self) -> List[Dict]:
        """Check for overlapping ingredients between harmful and passive lists"""
        harmful_terms = set()
        passive_terms = set()
        
        # Extract all terms from harmful additives
        for item in self.harmful_data.get("harmful_additives", []):
            name = item.get("standard_name", "").lower()
            if name:
                harmful_terms.add(name)
            
            for alias in item.get("aliases", []):
                harmful_terms.add(alias.lower())
        
        # Extract all terms from passive ingredients
        for item in self.passive_data.get("passive_inactive_ingredients", []):
            name = item.get("standard_name", "").lower()
            if name:
                passive_terms.add(name)
                
            for alias in item.get("aliases", []):
                passive_terms.add(alias.lower())
        
        # Find overlaps
        overlaps = harmful_terms.intersection(passive_terms)
        
        if overlaps:
            self.warnings.append(f"Found {len(overlaps)} overlapping ingredients: {sorted(list(overlaps))}")
        
        logger.info(f"Overlap check complete - found {len(overlaps)} overlaps")
        return list(overlaps)
    
    def validate_risk_levels(self):
        """Validate risk level classifications"""
        valid_risk_levels = {"high", "moderate", "low", "none"}
        
        for item in self.harmful_data.get("harmful_additives", []):
            risk_level = item.get("risk_level", "").lower()
            if risk_level not in valid_risk_levels:
                self.errors.append(f"Invalid risk level '{risk_level}' for {item.get('standard_name', 'unknown')}")
            
            # Check for "none" risk level - should be moved to passive
            if risk_level == "none":
                self.warnings.append(f"'{item.get('standard_name')}' has 'none' risk level - consider moving to passive list")
        
        logger.info("Risk level validation complete")
    
    def validate_categories(self):
        """Validate category consistency"""
        categories = defaultdict(int)
        
        for item in self.harmful_data.get("harmful_additives", []):
            category = item.get("category", "")
            categories[category] += 1
        
        logger.info(f"Found {len(categories)} unique categories in harmful additives")
        
        # Check for inconsistent category naming
        potential_duplicates = []
        category_list = list(categories.keys())
        
        for i, cat1 in enumerate(category_list):
            for cat2 in category_list[i+1:]:
                if cat1 and cat2:
                    # Check for similar categories that might need standardization
                    if cat1.replace("_", " ").replace("-", " ").lower() in cat2.replace("_", " ").replace("-", " ").lower():
                        potential_duplicates.append((cat1, cat2))
        
        if potential_duplicates:
            self.warnings.append(f"Potential category duplicates found: {potential_duplicates}")
    
    def validate_required_fields(self):
        """Validate that all required fields are present"""
        required_harmful = ["id", "standard_name", "risk_level", "category", "notes", "last_updated"]
        required_passive = ["id", "standard_name", "category", "notes", "last_updated"]
        
        # Check harmful additives
        for item in self.harmful_data.get("harmful_additives", []):
            for field in required_harmful:
                if not item.get(field):
                    self.errors.append(f"Missing required field '{field}' in harmful additive: {item.get('id', 'unknown')}")
        
        # Check passive ingredients
        for item in self.passive_data.get("passive_inactive_ingredients", []):
            for field in required_passive:
                if not item.get(field):
                    self.errors.append(f"Missing required field '{field}' in passive ingredient: {item.get('id', 'unknown')}")
        
        logger.info("Required fields validation complete")
    
    def validate_aliases(self):
        """Validate alias consistency and detect duplicates"""
        all_aliases = defaultdict(list)
        
        # Collect all aliases
        for item in self.harmful_data.get("harmful_additives", []):
            item_id = item.get("id", "unknown")
            for alias in item.get("aliases", []):
                all_aliases[alias.lower()].append(f"harmful:{item_id}")
        
        for item in self.passive_data.get("passive_inactive_ingredients", []):
            item_id = item.get("id", "unknown")
            for alias in item.get("aliases", []):
                all_aliases[alias.lower()].append(f"passive:{item_id}")
        
        # Find duplicate aliases
        duplicates = {alias: locations for alias, locations in all_aliases.items() if len(locations) > 1}
        
        if duplicates:
            self.warnings.append(f"Found {len(duplicates)} duplicate aliases across files")
            for alias, locations in list(duplicates.items())[:5]:  # Show first 5
                self.warnings.append(f"Duplicate alias '{alias}' in: {locations}")
        
        logger.info(f"Alias validation complete - found {len(duplicates)} duplicates")
    
    def check_scientific_accuracy(self):
        """Check for scientifically questionable classifications"""
        questionable = []
        
        for item in self.harmful_data.get("harmful_additives", []):
            name = item.get("standard_name", "").lower()
            risk = item.get("risk_level", "").lower()
            
            # Check for potentially misclassified items
            if "stevia" in name and risk != "none":
                questionable.append(f"Stevia classified as '{risk}' - should likely be 'none'")
            
            if "monk fruit" in name and risk != "none":
                questionable.append(f"Monk fruit classified as '{risk}' - should likely be 'none'")
            
            if "erythritol" in name and risk == "low":
                questionable.append(f"Erythritol classified as '{risk}' - recent studies suggest 'moderate'")
        
        if questionable:
            self.warnings.extend(questionable)
        
        logger.info("Scientific accuracy check complete")
    
    def generate_report(self) -> str:
        """Generate comprehensive validation report"""
        report = []
        report.append("=" * 60)
        report.append("INGREDIENT DATA VALIDATION REPORT")
        report.append("=" * 60)
        report.append("")
        
        # Summary
        report.append(f"Harmful Additives: {len(self.harmful_data.get('harmful_additives', []))}")
        report.append(f"Passive Ingredients: {len(self.passive_data.get('passive_inactive_ingredients', []))}")
        report.append(f"Errors Found: {len(self.errors)}")
        report.append(f"Warnings Found: {len(self.warnings)}")
        report.append("")
        
        # Errors
        if self.errors:
            report.append("CRITICAL ERRORS:")
            report.append("-" * 20)
            for error in self.errors:
                report.append(f"❌ {error}")
            report.append("")
        
        # Warnings
        if self.warnings:
            report.append("WARNINGS:")
            report.append("-" * 20)
            for warning in self.warnings:
                report.append(f"⚠️  {warning}")
            report.append("")
        
        # Recommendations
        report.append("RECOMMENDATIONS:")
        report.append("-" * 20)
        if not self.errors and not self.warnings:
            report.append("✅ All validations passed! Data quality is excellent.")
        else:
            if self.errors:
                report.append("• Fix all critical errors before deploying to production")
            if self.warnings:
                report.append("• Review warnings and implement fixes as needed")
                report.append("• Consider implementing automated data quality checks")
                report.append("• Schedule regular data audits")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def run_validation(self) -> str:
        """Run all validation checks and return report"""
        logger.info("Starting ingredient data validation...")
        
        self.load_data()
        self.validate_structure()
        self.check_overlaps()
        self.validate_risk_levels()
        self.validate_categories()
        self.validate_required_fields()
        self.validate_aliases()
        self.check_scientific_accuracy()
        
        report = self.generate_report()
        
        logger.info("Validation complete!")
        return report

def main():
    """Main validation script"""
    data_dir = Path(__file__).parent / "scripts" / "data"
    
    if not data_dir.exists():
        print(f"Error: Data directory not found at {data_dir}")
        return
    
    validator = IngredientDataValidator(data_dir)
    report = validator.run_validation()
    
    print(report)
    
    # Save report to file
    report_file = Path(__file__).parent / "ingredient_validation_report.txt"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"\nReport saved to: {report_file}")

if __name__ == "__main__":
    main()