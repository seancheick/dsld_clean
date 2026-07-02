#!/usr/bin/env python3
"""
Generate a raw DSLD-format label for a prenatal multivitamin optimized to score
high on the PharmaGuide scoring engine (score_supplements.py v3.0).

Design goals (mapped to scoring sections):
- Section A: premium bioavailable forms (A1/A2), tier-1 liposomal delivery (A3),
  Vitamin D3 -> Calcium/Magnesium absorption pairing (A4), organic + standardized
  botanical (ginger) + synergy clusters (A5).
- Section B: ZERO penalties (no allergens present, clean other-ingredients,
  no proprietary blends, no disease-claim trigger words) -> B = 35.
- Section C: many ingredients matching backed_clinical_studies -> saturates at 15.
- Section D: recognized manufacturer (FullWell), full disclosure, physician
  formulated, USA-made, sustainable glass packaging.
All doses are between the US pregnancy RDA/AI and the pregnancy UL.
"""
import json, os

# (order name, form, quantity, unit) -- name chosen to match BOTH the quality-map
# form alias AND (where possible) a backed_clinical_studies alias.
actives = [
    # name,                          form (premium),                          qty,   unit,     notes
    ("Vitamin A (as Beta-Carotene)", "Beta-Carotene from Mixed Carotenoids",  770,   "mcg RAE","100% as provitamin A beta-carotene from mixed carotenoids; no preformed retinol, safe in pregnancy"),
    ("Vitamin C",                    "Liposomal Vitamin C",                   120,   "mg",     "Liposomal delivery for enhanced absorption"),
    ("Vitamin D3",                   "Cholecalciferol (D3)",                  50,    "mcg",    "2,000 IU cholecalciferol; supports healthy glucose metabolism and calcium absorption"),
    ("Vitamin E",                    "Mixed Tocopherols",                     15,    "mg",     "Natural full-spectrum mixed tocopherols"),
    ("Vitamin K2",                   "Menaquinone-7 (MK-7)",                  90,    "mcg",    "All-trans MK-7 directs calcium to bone"),
    ("Thiamine",                     "Benfotiamine",                          3,     "mg",     "Lipid-soluble B1 (benfotiamine) supports healthy nerve function"),
    ("Riboflavin",                   "Riboflavin-5-Phosphate",                1.6,   "mg",     "Active coenzyme form of B2"),
    ("Niacin (as Niacinamide)",      "Niacinamide",                           18,    "mg",     "Non-flushing niacinamide"),
    ("Vitamin B6",                   "Pyridoxal 5'-Phosphate (P-5-P)",        25,    "mg",     "Active P-5-P; supports healthy nausea response in pregnancy"),
    ("Folate",                       "L-5-Methyltetrahydrofolate",            1000,  "mcg DFE","1,000 mcg DFE as L-5-MTHF (active folate); bypasses MTHFR conversion"),
    ("Vitamin B12",                  "Methylcobalamin",                       100,   "mcg",    "Active methylated B12"),
    ("Biotin",                       "d-Biotin",                              30,    "mcg",    ""),
    ("Pantothenic Acid",             "Pantethine",                            6,     "mg",     "Active pantethine form of B5"),
    ("Choline",                      "Alpha-GPC",                             450,   "mg",     "450 mg choline as Alpha-GPC; supports fetal brain development"),
    ("Calcium",                      "Calcium Citrate",                       200,   "mg",     "Gentle, well-absorbed calcium citrate"),
    ("Iron",                         "Iron Bisglycinate",                     27,    "mg",     "Gentle chelated iron bisglycinate (Ferrochel); low constipation"),
    ("Magnesium Glycinate",          "Magnesium Glycinate",                   200,   "mg",     "Chelated magnesium bisglycinate; supports healthy blood sugar"),
    ("Zinc",                         "Zinc Bisglycinate",                     15,    "mg",     "Chelated zinc bisglycinate"),
    ("Copper",                       "Copper Bisglycinate",                   1000,  "mcg",    "Balances zinc"),
    ("Selenium",                     "Selenomethionine",                      60,    "mcg",    "Organic selenomethionine; thyroid and antioxidant support"),
    ("Iodine",                       "Potassium Iodide",                      220,   "mcg",    "Predictable-dose potassium iodide for thyroid and fetal brain"),
    ("Chromium",                     "Chromium Picolinate",                   45,    "mcg",    "Supports healthy insulin sensitivity and glucose metabolism"),
    ("Manganese",                    "Manganese Bisglycinate",                2,     "mg",     ""),
    ("Molybdenum",                   "Molybdenum Glycinate",                  50,    "mcg",    ""),
    ("Myo-Inositol",                 "Myo-Inositol",                          2000,  "mg",     "Supports healthy insulin sensitivity and ovarian/metabolic function"),
    ("D-Chiro-Inositol",             "D-Chiro-Inositol",                      50,    "mg",     "Clinically studied 40:1 myo:D-chiro-inositol ratio for healthy glucose metabolism"),
    ("DHA",                          "Algal Triglyceride",                    300,   "mg",     "Vegan algal DHA omega-3; supports fetal brain and eye development"),
    ("Ginger Extract",               "Ginger Root Extract",                   100,   "mg",     "Organic ginger standardized to 5% gingerols; supports a healthy nausea response"),
]

ingredient_rows = []
iid = 900000
for i, (name, form, qty, unit, notes) in enumerate(actives, start=1):
    iid += 1
    ingredient_rows.append({
        "order": i,
        "ingredientId": iid,
        "description": "",
        "notes": notes,
        "quantity": [{
            "servingSizeOrder": 1,
            "servingSizeQuantity": 2,
            "operator": "=",
            "quantity": qty,
            "unit": unit,
            "dailyValueTargetGroup": [{
                "name": "Pregnant/Lactating women",
                "operator": None,
                "percent": None,
                "footnote": ""
            }],
            "servingSizeUnit": "Capsule(s)"
        }],
        "nestedRows": [],
        "name": name,
        "category": "botanical" if "Ginger" in name else "vitamin",
        "ingredientGroup": name,
        "uniiCode": "0",
        "alternateNames": [],
        "forms": [{
            "order": 1,
            "ingredientId": iid + 500000,
            "prefix": "as",
            "percent": None,
            "name": form,
            "category": "botanical" if "Ginger" in name else "vitamin",
            "ingredientGroup": name,
            "uniiCode": "0"
        }]
    })

# Clean "other ingredients" (excipients) — all GRAS, non-harmful, no allergens.
other_ingredients = {
    "ingredients": [
        {"order": 1, "name": "Organic Rice Hull Concentrate", "forms": []},
        {"order": 2, "name": "Vegetable Cellulose Capsule", "forms": []},
        {"order": 3, "name": "Organic Acacia Gum", "forms": []},
        {"order": 4, "name": "Sunflower Lecithin", "forms": []},
    ]
}

statements = [
    {"type": "FDA Statement of Identity", "notes": "Prenatal Multivitamin Dietary Supplement"},
    {"type": "Formulation re: Other", "notes":
        "Physician-Formulated for pregnant and nursing women, including those managing "
        "blood sugar. Features fully active, bioavailable nutrient forms: L-5-MTHF active "
        "folate, methylcobalamin B12, P-5-P B6, chelated iron bisglycinate, and vegan algal DHA. "
        "Supports healthy glucose metabolism, insulin sensitivity, fetal brain and neural tube "
        "development, and a healthy nausea response."},
    {"type": "Seals/Symbols", "notes":
        "USP Verified. NSF Certified. Informed Choice Certified. Certified Organic. "
        "NSF GMP Registered facility. Non-GMO Project Verified. Certified Gluten-Free (GFCO). "
        "Certified Vegan."},
    {"type": "Formulation re: Other", "notes":
        "Manufactured in the USA in an NSF GMP Registered, cGMP Certified facility. "
        "Certificate of Analysis (COA) available for every batch. Scan the QR code on each "
        "bottle for batch lookup and full traceability. Third-party tested for heavy metals and purity."},
    {"type": "Seals/Symbols", "notes":
        "Free from all 9 major FDA allergens. Certified Gluten-Free (GFCO). Dairy-Free. "
        "Soy-Free. 100% Vegan. Non-GMO Project Verified."},
    {"type": "Formulation re: Other", "notes":
        "Packaged in a 100% recyclable amber glass bottle. Plastic-free, sustainable packaging."},
    {"type": "Suggested/Recommended/Usage/Directions", "notes":
        "Suggested Use: Take 2 capsules daily with food, or as directed by your healthcare "
        "practitioner. Liposomal delivery technology enhances nutrient absorption."},
    {"type": "FDA Disclaimer Statement", "notes":
        "These statements have not been evaluated by the Food and Drug Administration. This "
        "product is not intended to diagnose, treat, cure or prevent any disease. Consult your "
        "healthcare provider before use if pregnant, nursing, or managing a medical condition."},
]

label = {
    "src": "engineered/prenatal_diabetic_optimized.json",
    "id": 900001,
    "fullName": "Complete Prenatal Multivitamin with Active Folate, DHA & Myo-Inositol (Liposomal)",
    "brandName": "FullWell",
    "brandIpSymbol": "®",
    "upcSku": "0 00000 00001 7",
    "productVersionCode": "Not Present",
    "servingsPerContainer": "30",
    "percentDvFootnote": "Not Present",
    "netContents": [{"order": 1, "quantity": 60, "unit": "Capsule(s)", "display": "60 Capsule(s)"}],
    "physicalState": {"langualCode": "E0159", "langualCodeDescription": "Capsule"},
    "servingSizes": [{
        "order": 1, "minQuantity": 2, "maxQuantity": 2,
        "minDailyServings": 1, "maxDailyServings": 1,
        "unit": "Capsule(s)", "notes": "", "inSFB": True
    }],
    "targetGroups": ["Pregnant/Lactating women", "Vegetarian", "Vegan", "Organic", "Gluten Free"],
    "productType": {"langualCode": "A1306", "langualCodeDescription": "Multivitamin/Mineral"},
    "contacts": [{
        "contactId": 99001,
        "text": "Manufactured for",
        "types": ["Manufacturer"],
        "contactDetails": {
            "id": 99001, "name": "FullWell", "streetAddress": "",
            "city": "", "state": "", "country": "USA", "zipCode": "",
            "phoneNumber": "", "email": "", "webAddress": "fullwellfertility.com"
        }
    }],
    "statements": statements,
    "claims": [
        {"langualCode": "P0265", "langualCodeDescription": "Structure/Function"},
        {"langualCode": "P0115", "langualCodeDescription": "All Other"}
    ],
    "ingredientRows": ingredient_rows,
    "otherIngredients": other_ingredients,
}

outdir = os.path.join(os.path.dirname(__file__), "work", "raw")
os.makedirs(outdir, exist_ok=True)
path = os.path.join(outdir, "prenatal_diabetic_optimized.json")
with open(path, "w") as f:
    json.dump(label, f, indent=1)
print("Wrote", path)
print("Active ingredient count:", len(ingredient_rows))
