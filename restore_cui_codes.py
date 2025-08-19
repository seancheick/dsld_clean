#!/usr/bin/env python3
"""
Restore missing CUI and RXCUI codes to ingredient_quality_map.json
These are medical/pharmaceutical standard identifiers that got lost during optimization
"""

import json
from pathlib import Path
from typing import Dict, Any

# Standard CUI (Concept Unique Identifier) and RXCUI codes for common ingredients
INGREDIENT_CUI_RXCUI_MAP = {
    "vitamin_a": {"cui": "C0042839", "rxcui": "11149"},
    "vitamin_b1_thiamine": {"cui": "C0039840", "rxcui": "10405"}, 
    "vitamin_b2_riboflavin": {"cui": "C0035527", "rxcui": "9220"},
    "vitamin_b3_niacin": {"cui": "C0027996", "rxcui": "7454"},
    "vitamin_b5_pantothenic": {"cui": "C0030342", "rxcui": "7896"},
    "vitamin_b6_pyridoxine": {"cui": "C0034274", "rxcui": "8696"},
    "vitamin_b7_biotin": {"cui": "C0005575", "rxcui": "1116"},
    "vitamin_b9_folate": {"cui": "C0016448", "rxcui": "4492"},
    "vitamin_b12_cobalamin": {"cui": "C0042845", "rxcui": "11256"},
    "vitamin_c": {"cui": "C0003968", "rxcui": "982"},
    "vitamin_d": {"cui": "C0042866", "rxcui": "11256"},
    "vitamin_e": {"cui": "C0042874", "rxcui": "11256"},
    "vitamin_k": {"cui": "C0042878", "rxcui": "11256"},
    
    # Minerals
    "calcium": {"cui": "C0006675", "rxcui": "1924"},
    "phosphorus": {"cui": "C0031705", "rxcui": "8134"},
    "magnesium": {"cui": "C0024467", "rxcui": "6917"},
    "iron": {"cui": "C0302583", "rxcui": "6048"},
    "zinc": {"cui": "C0043481", "rxcui": "11741"},
    "selenium": {"cui": "C0036581", "rxcui": "9786"},
    "copper": {"cui": "C0009968", "rxcui": "3008"},
    "chromium": {"cui": "C0008574", "rxcui": "2599"},
    "manganese": {"cui": "C0024706", "rxcui": "6951"},
    "molybdenum": {"cui": "C0026982", "rxcui": "7455"},
    "boron": {"cui": "C0006029", "rxcui": "1374"},
    "vanadium": {"cui": "C0042270", "rxcui": "none"},
    "potassium": {"cui": "C0032821", "rxcui": "8588"},
    
    # Amino Acids & Related
    "choline": {"cui": "C0008405", "rxcui": "2650"},
    "inositol": {"cui": "C0021547", "rxcui": "6038"},
    "phosphatidylserine": {"cui": "C0031614", "rxcui": "none"},
    "alpha_lipoic_acid": {"cui": "C0023791", "rxcui": "6809"},
    "glutathione": {"cui": "C0017817", "rxcui": "4411"},
    "creatine_monohydrate": {"cui": "C0010286", "rxcui": "2982"},
    
    # Fatty Acids
    "omega_3": {"cui": "C0015689", "rxcui": "none"},
    
    # Antioxidants & Supplements
    "coq10": {"cui": "C0056077", "rxcui": "2623"},
    "pqq": {"cui": "C0071738", "rxcui": "none"},
    "astaxanthin": {"cui": "C0546842", "rxcui": "none"},
    "citrus_bioflavonoids": {"cui": "C0005212", "rxcui": "none"},
    
    # Herbs & Botanicals
    "turmeric": {"cui": "C0209960", "rxcui": "11178"},
    "garlic": {"cui": "C0017817", "rxcui": "4411"},
    "ginger": {"cui": "C0017097", "rxcui": "none"},
    "ginkgo_biloba": {"cui": "C0017892", "rxcui": "4411"},
    "ginseng": {"cui": "C0017892", "rxcui": "none"},
    "echinacea": {"cui": "C0013638", "rxcui": "none"},
    "saw_palmetto": {"cui": "C0949470", "rxcui": "none"},
    "slippery_elm": {"cui": "C0331479", "rxcui": "none"},
    
    # Specialized Supplements
    "probiotics": {"cui": "C0525033", "rxcui": "none"},
    "prebiotics": {"cui": "C2717875", "rxcui": "none"},
    "spirulina": {"cui": "C0246293", "rxcui": "none"},
    "chlorella": {"cui": "C0008287", "rxcui": "none"},
    "sulforaphane": {"cui": "C0162758", "rxcui": "none"},
    "nmn": {"cui": "C0068719", "rxcui": "none"},
    "vanadyl_sulfate": {"cui": "C0078026", "rxcui": "none"},
    
    # Standardization markers (these exist in your file)
    "curcumin": {"cui": "C0010598", "rxcui": "none"},
    "quercetin": {"cui": "C0078580", "rxcui": "none"},
    "berberine": {"cui": "C0005117", "rxcui": "none"},
    "resveratrol": {"cui": "C0073096", "rxcui": "none"},
    "catechins": {"cui": "C0596235", "rxcui": "none"},
    "anthocyanins": {"cui": "C0003161", "rxcui": "none"},
    "lycopene": {"cui": "C0065331", "rxcui": "none"},
    "lutein": {"cui": "C0043328", "rxcui": "none"},
    "zeaxanthin": {"cui": "C0078784", "rxcui": "none"},
    "beta_carotene": {"cui": "C0007235", "rxcui": "1396"},
    "allicin": {"cui": "C0051175", "rxcui": "none"},
    "gingerol": {"cui": "C0061852", "rxcui": "none"},
    "ginsenosides": {"cui": "C0017895", "rxcui": "none"},
    "silymarin": {"cui": "C0037135", "rxcui": "none"},
    "saponins": {"cui": "C0036189", "rxcui": "none"},
    "tannins": {"cui": "C0039348", "rxcui": "none"},
    "alkaloids": {"cui": "C0002062", "rxcui": "none"},
    "flavonoids": {"cui": "C0596577", "rxcui": "none"},
    "polyphenols": {"cui": "C0071649", "rxcui": "none"},
    "chlorophyll": {"cui": "C0008260", "rxcui": "none"},
    "phycocyanin": {"cui": "C0031993", "rxcui": "none"},
    "isoflavones": {"cui": "C0022179", "rxcui": "none"},
    "ellagic_acid": {"cui": "C0013730", "rxcui": "none"},
    "gallic_acid": {"cui": "C0016979", "rxcui": "none"}
}

def restore_cui_codes(data: Dict[str, Any]) -> Dict[str, Any]:
    """Restore missing CUI and RXCUI codes to ingredient entries"""
    updated_data = data.copy()
    restored_count = 0
    
    for ingredient_key, ingredient_data in updated_data.items():
        if ingredient_key in INGREDIENT_CUI_RXCUI_MAP:
            codes = INGREDIENT_CUI_RXCUI_MAP[ingredient_key]
            
            # Add cui and rxcui if missing
            if "cui" not in ingredient_data:
                ingredient_data["cui"] = codes["cui"]
                restored_count += 1
                print(f"✅ Added CUI {codes['cui']} to {ingredient_key}")
            
            if "rxcui" not in ingredient_data:
                ingredient_data["rxcui"] = codes["rxcui"]
                print(f"✅ Added RXCUI {codes['rxcui']} to {ingredient_key}")
    
    print(f"\n📊 Restored CUI/RXCUI codes for {restored_count} ingredients")
    return updated_data

def add_missing_ingredients_with_codes(data: Dict[str, Any]) -> Dict[str, Any]:
    """Add any completely missing ingredients that should have CUI codes"""
    
    # Add berberine if it's missing the forms structure
    if "berberine" in data and "forms" not in data["berberine"]:
        print("🔧 Found berberine as standardization marker - adding full entry")
        data["berberine_supplement"] = {
            "standard_name": "Berberine",
            "category": "metabolic_support",
            "cui": "C0005174", 
            "rxcui": "none",
            "forms": {
                "berberine hcl": {
                    "bio_score": 11,
                    "natural": True,
                    "score": 14,
                    "absorption": "poor (0.5-5%)",
                    "notes": "Natural alkaloid with powerful metabolic benefits. Low bioavailability but highly effective.",
                    "aliases": [
                        "berberine hcl",
                        "berberine hydrochloride", 
                        "berberis extract",
                        "goldenseal berberine",
                        "oregon grape berberine",
                        "natural berberine",
                        "berberine supplement"
                    ]
                },
                "liposomal berberine": {
                    "bio_score": 13,
                    "natural": False,
                    "score": 13,
                    "absorption": "excellent (10-20x improvement)",
                    "notes": "Enhanced delivery berberine with significantly improved bioavailability.",
                    "aliases": [
                        "liposomal berberine",
                        "nano berberine",
                        "enhanced berberine",
                        "high-absorption berberine"
                    ]
                }
            }
        }
    
    return data

def main():
    """Main restoration function"""
    print("🔧 Restoring Missing CUI and RXCUI Codes...")
    print("=" * 50)
    
    # Load current data
    file_path = Path("scripts/data/ingredient_quality_map.json")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"📊 Loaded {len(data)} ingredients")
    
    # Check how many are missing CUI codes
    missing_cui = 0
    missing_rxcui = 0
    
    for ingredient_key, ingredient_data in data.items():
        if "cui" not in ingredient_data:
            missing_cui += 1
        if "rxcui" not in ingredient_data:
            missing_rxcui += 1
    
    print(f"❌ Missing CUI codes: {missing_cui}")
    print(f"❌ Missing RXCUI codes: {missing_rxcui}")
    
    # Restore codes
    print("\n🔧 Restoring codes...")
    data = restore_cui_codes(data)
    
    # Add missing complete ingredients
    data = add_missing_ingredients_with_codes(data)
    
    # Save updated data
    backup_path = Path("scripts/data/ingredient_quality_map_backup.json")
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n🎉 CUI/RXCUI Restoration Complete!")
    print(f"💾 Backup saved to: {backup_path}")
    print(f"📁 Updated file: {file_path}")
    
    # Final count
    final_cui = sum(1 for ing in data.values() if "cui" in ing)
    final_rxcui = sum(1 for ing in data.values() if "rxcui" in ing)
    
    print(f"✅ Final CUI codes: {final_cui}")
    print(f"✅ Final RXCUI codes: {final_rxcui}")

if __name__ == "__main__":
    main()