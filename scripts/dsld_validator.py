"""
DSLD Data Validator Module
Handles validation, completeness checking, and data quality assessment
"""
import re
from typing import Dict, List, Tuple, Optional, Any, Set
from datetime import datetime
import logging

from constants import (
    REQUIRED_FIELDS,
    SEVERITY_LEVELS,
    RISK_LEVELS,
    HARMFUL_CATEGORIES,
    STATUS_SUCCESS,
    STATUS_NEEDS_REVIEW,
    STATUS_INCOMPLETE,
    STATUS_ERROR
)

logger = logging.getLogger(__name__)


class DSLDValidator:
    """Validates DSLD product data for completeness and quality"""
    
    def __init__(self):
        self.critical_fields = set(REQUIRED_FIELDS["critical"])
        self.important_fields = set(REQUIRED_FIELDS["important"])
        self.optional_fields = set(REQUIRED_FIELDS["optional"])
        
    def validate_product(self, product_data: Dict[str, Any]) -> Tuple[str, List[str], Dict[str, Any]]:
        """
        Validate a product and determine its processing status
        
        Args:
            product_data: Raw product data from DSLD
            
        Returns:
            Tuple of (status, missing_fields, validation_details)
        """
        try:
            missing_fields = []
            validation_details = {
                "completeness_score": 0,
                "critical_fields_complete": True,
                "data_quality_issues": [],
                "validation_timestamp": datetime.utcnow().isoformat()
            }
            
            # Check critical fields
            missing_critical = self._check_fields(product_data, self.critical_fields)
            if missing_critical:
                missing_fields.extend(missing_critical)
                validation_details["critical_fields_complete"] = False
                
            # Check important fields
            missing_important = self._check_fields(product_data, self.important_fields)
            missing_fields.extend(missing_important)
            
            # Check optional fields
            missing_optional = self._check_fields(product_data, self.optional_fields)
            
            # Calculate completeness score (only count critical + important fields)
            critical_important_fields = len(self.critical_fields) + len(self.important_fields)
            missing_critical_important = len(missing_critical) + len(missing_important)
            present_critical_important = critical_important_fields - missing_critical_important
            validation_details["completeness_score"] = round((present_critical_important / critical_important_fields) * 100, 2)
            
            # Validate specific data quality issues
            quality_issues = self._check_data_quality(product_data)
            validation_details["data_quality_issues"] = quality_issues
            
            # Determine status with improved logic
            if missing_critical:
                # Missing critical fields = incomplete
                status = STATUS_INCOMPLETE
            elif len(missing_important) > 2:
                # Too many missing important fields = incomplete
                status = STATUS_INCOMPLETE
            elif quality_issues and len(quality_issues) > 3:
                # Many quality issues = needs review
                status = STATUS_NEEDS_REVIEW
            elif len(missing_important) > 1 or (missing_important and quality_issues):
                # Multiple missing important fields OR combination of issues = needs review
                status = STATUS_NEEDS_REVIEW
            elif missing_important and missing_important[0] != "upcSku":
                # Missing important field other than UPC = needs review
                status = STATUS_NEEDS_REVIEW
            elif quality_issues and quality_issues != ["invalid_upc_sku_format"]:
                # Quality issues OTHER than just invalid UPC format = needs review
                # Invalid UPC format alone is common and shouldn't trigger review
                status = STATUS_NEEDS_REVIEW
            else:
                # All good! (including products with only invalid UPC format)
                status = STATUS_SUCCESS
                
            return status, missing_fields, validation_details
            
        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            return STATUS_ERROR, [], {"error": str(e)}
    
    def _check_fields(self, data: Dict[str, Any], required_fields: Set[str]) -> List[str]:
        """Check which required fields are missing or empty"""
        missing = []
        for field in required_fields:
            value = data.get(field)
            if value is None or (isinstance(value, (str, list, dict)) and not value):
                missing.append(field)
        return missing
    
    def _check_data_quality(self, data: Dict[str, Any]) -> List[str]:
        """Check for specific data quality issues"""
        issues = []
        
        # Validate UPC/SKU format if present (but missing UPC/SKU is handled by completeness check)
        upc_sku = data.get("upcSku")
        if upc_sku and not self.validate_upc_sku(upc_sku):
            issues.append("invalid_upc_sku_format")
            
        # Check for empty ingredient rows
        ingredients = data.get("ingredientRows", [])
        if not ingredients:
            issues.append("no_ingredients")
            
        # Note: Discontinued status is informational only and should not trigger review
        # Products can still be sold/scanned even if discontinued by manufacturer
            
        return list(set(issues))  # Remove duplicates
    
    @staticmethod
    def validate_upc_sku(upc_sku: str) -> bool:
        """
        Validate UPC or SKU format based on retail standards
        
        Args:
            upc_sku: UPC or SKU string
            
        Returns:
            bool: True if valid UPC (12 digits) or valid SKU (alphanumeric, reasonable length)
        """
        if not upc_sku or not str(upc_sku).strip():
            return False
            
        # Remove common prefixes and clean the code
        clean_code = str(upc_sku).strip()
        # Remove common prefixes like #, Rev., etc.
        clean_code = re.sub(r'^(#|Rev\.|SKU:?|Item:?|Code:?)\s*', '', clean_code, flags=re.IGNORECASE)
        clean_code = re.sub(r'[\s-]', '', clean_code)
        
        # Check if it's a valid UPC (12 digits for UPC-A, 6 digits for UPC-E, 8 digits for EAN-8, 13 for EAN-13)
        if re.match(r'^\d{6}$|^\d{8}$|^\d{12}$|^\d{13}$', clean_code):
            return True
            
        # Check if it's a valid SKU (alphanumeric with common special chars, 2-40 characters)
        # More lenient to accept various SKU formats
        if re.match(r'^[A-Za-z0-9\-_#./]{2,40}$', clean_code):
            return True
            
        # Accept version-style codes (e.g., "Rev. 04", "v1.2")
        if re.match(r'^(v|ver|version|rev|revision)\.?\s*\d+(\.\d+)?$', upc_sku.lower().strip()):
            return True
            
        return False
    
    @staticmethod
    def validate_date_format(date_str: str) -> bool:
        """Validate ISO 8601 date format"""
        try:
            datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return True
        except:
            return False
    
    @staticmethod
    def validate_severity_level(level: Optional[str]) -> bool:
        """Validate severity level is from allowed values"""
        return level in SEVERITY_LEVELS or level is None
    
    @staticmethod
    def validate_risk_level(level: Optional[str]) -> bool:
        """Validate risk level is from allowed values"""
        return level in RISK_LEVELS or level is None
    
    @staticmethod
    def validate_harmful_category(category: Optional[str]) -> bool:
        """Validate harmful category is from allowed values"""
        return category in HARMFUL_CATEGORIES or category is None
    
    def validate_cleaned_product(self, cleaned_data: Dict[str, Any]) -> List[str]:
        """
        Validate the cleaned product data structure
        
        Args:
            cleaned_data: Cleaned product data
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check required structure
        if not isinstance(cleaned_data.get("id"), str):
            errors.append("id must be string")
            
        # Validate arrays are arrays
        array_fields = [
            "targetGroups", "images", "activeIngredients", 
            "inactiveIngredients", "statements", "claims"
        ]
        for field in array_fields:
            if field in cleaned_data and not isinstance(cleaned_data[field], list):
                errors.append(f"{field} must be array")
                
        # Validate ingredient structure
        for ing_type in ["activeIngredients", "inactiveIngredients"]:
            ingredients = cleaned_data.get(ing_type, [])
            for i, ing in enumerate(ingredients):
                # Check required ingredient fields
                if not isinstance(ing.get("name"), str):
                    errors.append(f"{ing_type}[{i}] missing name")
                    
                # Validate allergen fields if present
                if ing.get("allergen") is True:
                    if not ing.get("allergenType"):
                        errors.append(f"{ing_type}[{i}] missing allergenType")
                    if not self.validate_severity_level(ing.get("allergenSeverity")):
                        errors.append(f"{ing_type}[{i}] invalid allergenSeverity")
                        
                # Validate harmful fields
                if not self.validate_harmful_category(ing.get("harmfulCategory")):
                    errors.append(f"{ing_type}[{i}] invalid harmfulCategory")
                    
                # Validate forms is array
                if "forms" in ing and not isinstance(ing["forms"], list):
                    errors.append(f"{ing_type}[{i}] forms must be array")
                    
        # Validate dates
        date_fields = ["discontinuedDate"]
        for field in date_fields:
            if field in cleaned_data and cleaned_data[field] is not None:
                if not self.validate_date_format(cleaned_data[field]):
                    errors.append(f"{field} invalid date format")
                    
        # Validate status
        if cleaned_data.get("status") not in ["active", "discontinued"]:
            errors.append("status must be 'active' or 'discontinued'")
            
        return errors


def check_completeness(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Quick completeness check for a product
    
    Args:
        product_data: Product data to check
        
    Returns:
        Completeness details
    """
    validator = DSLDValidator()
    status, missing_fields, details = validator.validate_product(product_data)
    
    return {
        "status": status,
        "missing_fields": missing_fields,
        "completeness_score": details.get("completeness_score", 0),
        "critical_fields_complete": details.get("critical_fields_complete", False),
        "issues": details.get("data_quality_issues", [])
    }