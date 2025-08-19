#!/usr/bin/env python3
"""
Generate Detailed Review Report
Quick script to manually generate the detailed review report when it's missing
"""
import json
import sys
from pathlib import Path
from datetime import datetime

def generate_detailed_review_report():
    """Generate detailed review report for products needing manual attention"""
    
    # Set paths
    needs_review_dir = Path("output/needs_review")
    reports_dir = Path("output/reports")
    reports_dir.mkdir(exist_ok=True)
    report_file = reports_dir / "detailed_review_report.md"
    
    print(f"Looking for review files in: {needs_review_dir}")
    
    # Find all needs_review files
    review_files = list(needs_review_dir.glob("*.json"))
    if not review_files:
        print("No products need review - no detailed review report needed")
        return
    
    print(f"Found {len(review_files)} review files")
    
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
            print(f"Warning: Could not read review file {file_path}: {str(e)}")
    
    if not review_products:
        print("No products found in review files")
        return
    
    print(f"Found {len(review_products)} products needing review")
    
    # Generate the report
    write_detailed_review_report(report_file, review_products)
    print(f"✅ Detailed review report saved to: {report_file}")

def write_detailed_review_report(report_file: Path, review_products: list):
    """Write the detailed review report in markdown format"""
    
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
        f.write("- **High numbers of unmapped ingredients** requiring manual curation\n")
        f.write("- **Quality issues** that need manual verification\n\n")
        f.write("---\n\n")
        
        # Process each product
        for i, product in enumerate(review_products, 1):
            write_product_review_section(f, product, i)
            
            # Add separator between products
            if i < len(review_products):
                f.write("---\n\n")
        
        # Action items summary
        write_action_items_summary(f, review_products)
        
        # Files location
        f.write("---\n\n")
        f.write("## Files Location:\n")
        f.write("- **Detailed products:** `output/needs_review/needs_review_batch_*.json`\n")
        f.write("- **Full unmapped ingredients list:** `output/unmapped/unmapped_ingredients.json`\n")
        f.write("- **This report:** `output/reports/detailed_review_report.md`\n")

def write_product_review_section(f, product: dict, product_num: int):
    """Write individual product review section"""
    # Basic info
    f.write(f"## Product {product_num}: {product.get('fullName', 'Unknown Product')}\n")
    f.write(f"**Product ID:** {product.get('id', 'Unknown')}\n")
    f.write(f"**Brand:** {product.get('brandName', 'Unknown')}\n")
    
    # UPC info
    upc = product.get('upcSku', '')
    upc_valid = product.get('upcValid', False)
    if upc:
        status_icon = "✅" if upc_valid else "❌"
        f.write(f"**UPC:** {upc} {status_icon}\n")
    else:
        f.write(f"**UPC:** ❌ Missing\n")
    
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
    metadata = product.get('metadata', {})
    completeness = metadata.get('completeness', {})
    mapping_stats = metadata.get('mappingStats', {})
    
    f.write("### Why It Needs Review:\n")
    
    # Completeness score
    comp_score = completeness.get('score', 0)
    f.write(f"- **Completeness score:** {comp_score:.1f}%")
    if comp_score >= 90:
        f.write(" ✅\n")
    elif comp_score >= 75:
        f.write(" ⚠️\n")
    else:
        f.write(" ❌\n")
    
    # Missing fields
    missing_fields = completeness.get('missingFields', [])
    if missing_fields:
        f.write(f"- **Missing fields:** {', '.join(missing_fields)}\n")
    
    # Mapping rate
    mapping_rate = mapping_stats.get('mappingRate', 0)
    f.write(f"- **Ingredient mapping rate:** {mapping_rate:.1f}%")
    if mapping_rate >= 90:
        f.write(" ✅\n")
    elif mapping_rate >= 75:
        f.write(" ⚠️\n")
    else:
        f.write(" ❌\n")
    
    # Unmapped ingredients
    unmapped_count = mapping_stats.get('unmappedIngredients', 0)
    if unmapped_count > 0:
        f.write(f"- **Unmapped ingredients:** {unmapped_count}\n")
    
    # Quality flags
    quality_flags = metadata.get('qualityFlags', {})
    flags_to_check = [
        ('hasHarmfulAdditives', 'Contains harmful additives'),
        ('hasAllergens', 'Contains allergens'),
        ('hasProprietary', 'Has proprietary blends'),
        ('hasUnsubstantiatedClaims', 'Has unsubstantiated claims')
    ]
    
    for flag_key, flag_desc in flags_to_check:
        if quality_flags.get(flag_key, False):
            f.write(f"- **{flag_desc}** ⚠️\n")
    
    f.write("\n")
    
    # Ingredient breakdown
    active_count = len(product.get('activeIngredients', []))
    inactive_count = len(product.get('inactiveIngredients', []))
    f.write(f"**Ingredients:** {active_count} active, {inactive_count} inactive\n\n")

def write_action_items_summary(f, review_products: list):
    """Write action items summary"""
    f.write("---\n\n")
    f.write("## Action Items Summary\n\n")
    
    # Count common issues
    missing_upc = sum(1 for p in review_products if not p.get('upcSku'))
    low_mapping = sum(1 for p in review_products 
                     if p.get('metadata', {}).get('mappingStats', {}).get('mappingRate', 100) < 75)
    has_harmful = sum(1 for p in review_products 
                     if p.get('metadata', {}).get('qualityFlags', {}).get('hasHarmfulAdditives', False))
    discontinued = sum(1 for p in review_products if p.get('status') == 'discontinued')
    
    f.write("### Priority Actions:\n")
    if missing_upc > 0:
        f.write(f"1. **Add UPC codes** for {missing_upc} products\n")
    if low_mapping > 0:
        f.write(f"2. **Review unmapped ingredients** for {low_mapping} products\n")
    if has_harmful > 0:
        f.write(f"3. **Verify harmful additives** for {has_harmful} products\n")
    if discontinued > 0:
        f.write(f"4. **Note:** {discontinued} products are discontinued (informational only)\n")
    
    f.write("\n### Next Steps:\n")
    f.write("1. Review each product's specific issues listed above\n")
    f.write("2. Add missing UPC codes where possible\n")
    f.write("3. Check unmapped ingredients against reference databases\n")
    f.write("4. Verify harmful additive classifications\n")
    f.write("5. Re-run processing after making corrections\n\n")

if __name__ == "__main__":
    generate_detailed_review_report()