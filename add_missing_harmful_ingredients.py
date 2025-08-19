#!/usr/bin/env python3
"""
Add missing harmful ingredients that are popular in supplements
"""

import json
from pathlib import Path
from datetime import datetime

def add_missing_harmful_ingredients():
    # File path
    data_dir = Path("scripts/data")
    harmful_file = data_dir / "harmful_additives.json"
    
    # Load current data
    with open(harmful_file, 'r') as f:
        harmful_data = json.load(f)
    
    # Get existing IDs to avoid duplicates
    existing_ids = {item['id'] for item in harmful_data['harmful_additives']}
    
    # Missing harmful ingredients to add
    missing_ingredients = [
        {
            "id": "ADD_BHT",
            "standard_name": "BHT (Butylated Hydroxytoluene)",
            "aliases": [
                "BHT", "butylated hydroxytoluene", "E321",
                "2,6-di-tert-butyl-4-methylphenol", 
                "2,6-bis(1,1-dimethylethyl)-4-methylphenol",
                "antioxidant 264"
            ],
            "risk_level": "moderate",
            "category": "preservative_antioxidant_synthetic",
            "notes": "Synthetic antioxidant linked to hormone disruption, liver toxicity, and potential carcinogenicity. Can accumulate in body fat. Banned in some countries for use in food.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_BHA", 
            "standard_name": "BHA (Butylated Hydroxyanisole)",
            "aliases": [
                "BHA", "butylated hydroxyanisole", "E320",
                "tert-butyl-4-methoxyphenol",
                "2-tert-butyl-4-methoxyphenol",
                "3-tert-butyl-4-methoxyphenol"
            ],
            "risk_level": "high",
            "category": "preservative_antioxidant_synthetic",
            "notes": "Synthetic antioxidant classified as reasonably anticipated to be a human carcinogen by the US National Toxicology Program. Linked to hormone disruption and liver damage.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_TBHQ",
            "standard_name": "TBHQ (Tertiary Butylhydroquinone)",
            "aliases": [
                "TBHQ", "tertiary butylhydroquinone", "E319",
                "tert-butylhydroquinone",
                "2-(1,1-dimethylethyl)-1,4-benzenediol"
            ],
            "risk_level": "moderate",
            "category": "preservative_antioxidant_synthetic",
            "notes": "Petroleum-derived antioxidant. High doses can cause nausea, vomiting, and tinnitus. Limited safety data for long-term use. May interfere with immune function.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_POTASSIUM_SORBATE",
            "standard_name": "Potassium Sorbate",
            "aliases": [
                "potassium sorbate", "E202",
                "potassium (E,E)-hexa-2,4-dienoate",
                "sorbic acid potassium salt"
            ],
            "risk_level": "low",
            "category": "preservative_synthetic",
            "notes": "Synthetic preservative that can form potentially mutagenic compounds when combined with nitrites. May cause allergic reactions in sensitive individuals.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_SORBIC_ACID",
            "standard_name": "Sorbic Acid",
            "aliases": [
                "sorbic acid", "E200",
                "(E,E)-hexa-2,4-dienoic acid",
                "2,4-hexadienoic acid"
            ],
            "risk_level": "low",
            "category": "preservative_synthetic",
            "notes": "Synthetic preservative derived from petroleum. Generally considered safe but may cause contact dermatitis in sensitive individuals.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_SODIUM_METABISULFITE",
            "standard_name": "Sodium Metabisulfite",
            "aliases": [
                "sodium metabisulfite", "E223",
                "sodium pyrosulfite", "disodium disulfite",
                "Na2S2O5"
            ],
            "risk_level": "moderate",
            "category": "preservative_antioxidant",
            "notes": "Sulfite preservative that can trigger severe asthma attacks in sensitive individuals. May cause headaches, nausea, and allergic reactions. Can destroy thiamine (vitamin B1).",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_SULFUR_DIOXIDE",
            "standard_name": "Sulfur Dioxide",
            "aliases": [
                "sulfur dioxide", "sulphur dioxide", "E220",
                "SO2", "sulfurous acid anhydride"
            ],
            "risk_level": "moderate",
            "category": "preservative_gas",
            "notes": "Gaseous preservative that can trigger severe asthma attacks and allergic reactions. Destroys thiamine (vitamin B1). Particularly dangerous for asthmatics.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_PROPYLENE_GLYCOL",
            "standard_name": "Propylene Glycol", 
            "aliases": [
                "propylene glycol", "E1520",
                "1,2-propanediol", "propane-1,2-diol",
                "PG", "methyl ethyl glycol"
            ],
            "risk_level": "low",
            "category": "solvent_humectant",
            "notes": "Industrial solvent used as a humectant and solvent. Generally recognized as safe but can cause central nervous system depression at high doses. May accumulate in kidneys.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_YELLOW_6",
            "standard_name": "Yellow 6 (Sunset Yellow)",
            "aliases": [
                "Yellow 6", "sunset yellow", "E110",
                "FD&C Yellow No. 6", "orange yellow S",
                "CI 15985"
            ],
            "risk_level": "high",
            "category": "colorant_artificial",
            "notes": "Petroleum-derived artificial color linked to hyperactivity in children, allergic reactions, and potential carcinogenicity. Banned in some European countries.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_YELLOW_5",
            "standard_name": "Yellow 5 (Tartrazine)",
            "aliases": [
                "Yellow 5", "tartrazine", "E102",
                "FD&C Yellow No. 5", "acid yellow 23",
                "CI 19140"
            ],
            "risk_level": "high", 
            "category": "colorant_artificial",
            "notes": "Coal tar-derived artificial color strongly linked to hyperactivity in children, asthma, hives, and other allergic reactions. Requires warning labels in EU.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_SODIUM_BENZOATE_STANDALONE",
            "standard_name": "Sodium Benzoate (Standalone)",
            "aliases": [
                "sodium benzoate", "E211",
                "benzoic acid sodium salt",
                "sodium salt of benzoic acid"
            ],
            "risk_level": "moderate",
            "category": "preservative_synthetic",
            "notes": "Synthetic preservative that can form benzene (carcinogen) when exposed to heat, light, or vitamin C. May cause hyperactivity in children and allergic reactions.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_POTASSIUM_BENZOATE",
            "standard_name": "Potassium Benzoate",
            "aliases": [
                "potassium benzoate", "E212",
                "benzoic acid potassium salt"
            ],
            "risk_level": "moderate",
            "category": "preservative_synthetic", 
            "notes": "Similar concerns to sodium benzoate. Can form benzene under certain conditions. May cause allergic reactions and hyperactivity in sensitive individuals.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_CALCIUM_PROPIONATE",
            "standard_name": "Calcium Propionate",
            "aliases": [
                "calcium propionate", "E282",
                "propionic acid calcium salt"
            ],
            "risk_level": "low",
            "category": "preservative_synthetic",
            "notes": "Synthetic preservative that may affect behavior and learning in children. Can cause stomach irritation and may interfere with mineral absorption.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_MICROPLASTICS",
            "standard_name": "Microplastics/Nanoplastics",
            "aliases": [
                "microplastics", "nanoplastics", "plastic particles",
                "polymer particles", "synthetic particles"
            ],
            "risk_level": "high",
            "category": "contaminant_environmental",
            "notes": "Microscopic plastic particles found contaminating many supplements. Can cross blood-brain barrier and accumulate in organs. Long-term health effects unknown but concerning.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_HEAVY_METAL_LEAD",
            "standard_name": "Lead Contamination",
            "aliases": [
                "lead", "Pb", "lead acetate",
                "lead compounds", "heavy metal lead"
            ],
            "risk_level": "high",
            "category": "heavy_metal_contaminant",
            "notes": "Toxic heavy metal contaminant with no safe level. Causes neurological damage, especially in children. Common in bone meal calcium, herbs from certain regions.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_HEAVY_METAL_CADMIUM",
            "standard_name": "Cadmium Contamination", 
            "aliases": [
                "cadmium", "Cd", "cadmium compounds",
                "heavy metal cadmium"
            ],
            "risk_level": "high",
            "category": "heavy_metal_contaminant",
            "notes": "Toxic heavy metal that accumulates in kidneys and bones. Causes kidney disease, bone disease, and cancer. Common in cacao, zinc supplements.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_HEXANE_RESIDUE",
            "standard_name": "Hexane Residue",
            "aliases": [
                "hexane", "n-hexane", "hexane solvent",
                "petroleum hexane", "solvent residue"
            ],
            "risk_level": "moderate",
            "category": "solvent_residue",
            "notes": "Petroleum-derived solvent used in oil extraction. Residues can remain in supplements. Neurotoxic at high levels and may affect reproductive health.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "ADD_METHYLENE_CHLORIDE",
            "standard_name": "Methylene Chloride Residue",
            "aliases": [
                "methylene chloride", "dichloromethane", "DCM",
                "methylene dichloride", "solvent residue"
            ],
            "risk_level": "high",
            "category": "solvent_residue",
            "notes": "Chlorinated solvent used in caffeine extraction. Probable human carcinogen. Can cause central nervous system depression and liver damage.",
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        }
    ]
    
    # Add new ingredients that don't already exist
    added_count = 0
    for ingredient in missing_ingredients:
        if ingredient["id"] not in existing_ids:
            harmful_data["harmful_additives"].append(ingredient)
            added_count += 1
            print(f"Added: {ingredient['standard_name']} (Risk: {ingredient['risk_level']})")
        else:
            print(f"Skipped (already exists): {ingredient['standard_name']}")
    
    # Save updated file
    with open(harmful_file, 'w') as f:
        json.dump(harmful_data, f, indent=2)
    
    print(f"\nAdded {added_count} new harmful ingredients")
    print(f"Total harmful ingredients: {len(harmful_data['harmful_additives'])}")

if __name__ == "__main__":
    add_missing_harmful_ingredients()