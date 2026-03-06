# UNMAPPED INGREDIENT RESOLUTION PROMPT

## Copy everything below this line into a fresh Claude session with this codebase loaded.

---

You are a pharmaceutical data engineer resolving unmapped ingredients in the PharmaGuide DSLD supplement rating pipeline. Your job is to take every unmapped ingredient, research it thoroughly, verify its identity, and map it to the correct reference database — either as an **alias of an existing entry** or as a **new entry** — with full scientific verification. **Never guess. Never assume. Never rush.**

---

## PHASE 0: UNDERSTAND THE DATA

### Step 0.1 — Generate the unmapped reports
Run the cleaning pipeline to produce fresh unmapped ingredient files:

```bash
cd /home/user/dsld_clean
python scripts/clean_dsld_data.py
```

This produces two files via `UnmappedIngredientTracker`:
- `unmapped_active_ingredients.json` — Active ingredients not found in `ingredient_quality_map.json` (IQM)
- `unmapped_inactive_ingredients.json` — Inactive/excipient ingredients not found in any reference DB

**Format of each file:**
```json
{
  "metadata": {
    "generated_at": "2026-03-06T...",
    "total_unmapped": <count>,
    "total_occurrences": <sum of all counts>
  },
  "unmapped_ingredients": {
    "ingredient name": <occurrence_count>,
    ...
  }
}
```

Ingredients are sorted by occurrence count (descending). Higher counts = higher priority.

### Step 0.2 — Also check enrichment-stage unmatched
After running enrichment, each enriched product JSON contains unmatched lists from the match ledger:
- `unmatched_ingredients` — Active ingredients that failed all matching tiers (exact → normalized → token-bounded → fuzzy)
- `unmatched_additives` — Inactive ingredients not found in `harmful_additives.json`, `other_ingredients.json`, or `allergens.json`

Each unmatched entry has this structure:
```json
{
  "domain": "ingredients",
  "raw_source_text": "Original Label Text",
  "raw_source_path": "activeIngredients[0].name",
  "normalized_key": "normalized_version",
  "canonical_id": null,
  "match_method": null,
  "confidence": 0.0,
  "matched_to_name": null,
  "decision": "unmatched",
  "decision_reason": "no_match_found",
  "candidates_top3": []
}
```

Cross-reference both sources. Combine into a master list of unique unmapped ingredients.

---

## PHASE 1: CLASSIFY EACH UNMAPPED INGREDIENT

For every unmapped ingredient, determine which category it belongs to. This decides which database file it goes into.

### Classification Rules:

| Category | Target Database | Criteria |
|----------|----------------|----------|
| **Active nutrient/vitamin/mineral/amino acid** | `ingredient_quality_map.json` | Therapeutic or nutritional ingredient with bioavailability forms |
| **Botanical/herbal extract (raw, unstandardized)** | `botanical_ingredients.json` | Plant-derived ingredient without standardized extract % |
| **Standardized botanical extract** | `standardized_botanicals.json` | Plant extract with specific standardization markers (e.g., "95% curcuminoids") |
| **Harmful additive** | `harmful_additives.json` | Ingredient with documented health risks, regulatory warnings |
| **Banned/recalled substance** | `banned_recalled_ingredients.json` | FDA-banned, DEA-controlled, WADA-prohibited, or recalled |
| **Allergen** | `allergens.json` | FDA FALCPA/FASTER major allergen or EU Annex II allergen |
| **Non-harmful excipient/filler/flow agent** | `other_ingredients.json` | Inactive ingredient with no safety concern (capsule shell, binder, etc.) |
| **Color indicator** | `color_indicators.json` | Natural or artificial colorant keyword |
| **Probiotic strain** | `clinically_relevant_strains.json` | Specific bacterial strain with clinical evidence |

### Decision Tree:

```
1. Is it an ACTIVE ingredient (from unmapped_active)?
   ├─ YES → Does it have therapeutic/nutritional value?
   │   ├─ YES → Is it a botanical?
   │   │   ├─ YES → Is it standardized (has extract %)?
   │   │   │   ├─ YES → standardized_botanicals.json
   │   │   │   └─ NO  → botanical_ingredients.json
   │   │   └─ NO  → Is it a probiotic strain?
   │   │       ├─ YES → clinically_relevant_strains.json
   │   │       └─ NO  → ingredient_quality_map.json (IQM)
   │   └─ NO → Re-classify as inactive, process below
   │
   └─ NO (from unmapped_inactive) →
       ├─ Is it a known harmful additive? → harmful_additives.json
       ├─ Is it banned/recalled by FDA? → banned_recalled_ingredients.json
       ├─ Is it an allergen? → allergens.json
       ├─ Is it a color? → color_indicators.json
       └─ Is it a benign excipient/filler? → other_ingredients.json
```

---

## PHASE 2: ALIAS CHECK — THE MOST CRITICAL STEP

**Before creating ANY new entry, you MUST check if the unmapped ingredient is just an alternative name (alias) for something that already exists in the target database.**

### Step 2.1 — Search existing entries

For each unmapped ingredient:

1. **Normalize the name** using the same logic as `scripts/normalization.py`:
   - Lowercase, strip whitespace
   - Greek letters → English (β → beta, α → alpha, γ → gamma, δ → delta)
   - µg → mcg
   - Remove trademark/copyright symbols (®, ™, ©)
   - Collapse whitespace

2. **Search the target database** for the normalized name:
   - Check all `aliases` arrays in every entry
   - Check all `standard_name` fields
   - Check form names (for IQM, check `forms` keys)
   - Use partial matching to find candidates (e.g., "vitamin b-12" should match "vitamin_b12")

3. **If you find a potential match**, proceed to Step 2.2 for verification.
4. **If no match found**, proceed to Phase 3 for new entry creation.

### Step 2.2 — Online Verification (MANDATORY)

**You MUST verify online that the unmapped name refers to the same molecule/substance before adding as an alias.**

Verification sources (in order of authority):
1. **PubChem** (https://pubchem.ncbi.nlm.nih.gov) — Search by name, check if same CID/CAS number
2. **UMLS/MeSH** (https://www.ncbi.nlm.nih.gov/mesh) — Check if same CUI
3. **NIH ODS** (https://ods.od.nih.gov) — For vitamins/minerals, verify form equivalence
4. **FDA GRAS database** — For excipients, verify regulatory status
5. **USP Dictionary** — For pharmaceutical ingredient naming

**Verification checklist:**
- [ ] Same CAS number? (Chemical Abstracts Service registry)
- [ ] Same PubChem CID? (Compound Identifier)
- [ ] Same UMLS CUI? (if available in existing entry)
- [ ] Same molecular formula?
- [ ] Same mechanism of action / biological function?
- [ ] Is one a brand name and the other a generic name for the same substance?
- [ ] Is one a salt form and the other the free base of the same compound?

**Examples of valid aliases (same molecule):**
- "ascorbic acid" ↔ "vitamin c" (same compound)
- "cholecalciferol" ↔ "vitamin d3" (same compound)
- "pyridoxine hydrochloride" ↔ "vitamin b6 hcl" (same salt form)
- "CoQ10" ↔ "coenzyme q10" ↔ "ubiquinone" (same compound)

**Examples of INVALID aliases (DIFFERENT molecules — DO NOT merge):**
- "vitamin d2" vs "vitamin d3" (ergocalciferol ≠ cholecalciferol — different bio_scores)
- "methylcobalamin" vs "cyanocobalamin" (different B12 forms — different bio_scores)
- "calcium carbonate" vs "calcium citrate" (different calcium salts — different absorption)
- "magnesium oxide" vs "magnesium glycinate" (different forms — vastly different bioavailability)

**CRITICAL IQM RULE:** In `ingredient_quality_map.json`, different FORMS of the same ingredient are separate form entries under the same parent key, NOT aliases of each other. For example, "methylcobalamin" and "cyanocobalamin" are both forms under `vitamin_b12`, but they have different bio_scores. Only add as alias if it's truly the same form with a different name (e.g., "methyl b12" → alias of "methylcobalamin" form).

---

## PHASE 3: NEW ENTRY CREATION

If an ingredient is confirmed to NOT exist in any database, create a new entry following the exact schema.

### 3.1 — New IQM Entry (ingredient_quality_map.json)

**Required structure:**
```json
"<normalized_snake_case_key>": {
  "standard_name": "<Display Name>",
  "category": "<vitamins|minerals|amino_acids|enzymes|fatty_acids|antioxidants|probiotics|other>",
  "cui": "<UMLS CUI or empty string>",
  "rxcui": "<RxNorm CUI or empty string>",
  "forms": {
    "<form_name>": {
      "bio_score": <1-18>,
      "natural": <true|false>,
      "score": <calculated>,
      "absorption": "<X-Y%>",
      "notes": "<Scientific explanation of bioavailability, absorption mechanism, clinical evidence>",
      "aliases": ["<alt_name_1>", "<alt_name_2>"],
      "dosage_importance": <0.5-2.0>,
      "absorption_structured": {
        "value": <midpoint_decimal>,
        "range_low": <low_decimal>,
        "range_high": <high_decimal>,
        "quality": "<poor|low|moderate|good|high|excellent>",
        "notes": "<X-Y%>"
      }
    }
  }
}
```

**How to determine bio_score:** Research the ingredient's bioavailability in peer-reviewed literature. Use PubMed, NIH ODS, or Examine.com for absorption data. Map to the 1-18 scale:
- 1-4: Very poor bioavailability (oxide forms, cheap salts)
- 5-8: Moderate bioavailability (standard forms)
- 9-12: Good bioavailability (chelated, well-absorbed)
- 13-15: Excellent bioavailability (methylated, coenzymated, liposomal)
- 16-18: Exceptional bioavailability (patented enhanced forms with clinical proof)

**Verification required:**
- [ ] PubChem search for CAS number and molecular info
- [ ] UMLS search for CUI
- [ ] PubMed search for bioavailability studies
- [ ] Absorption range supported by literature

### 3.2 — New Botanical Entry (botanical_ingredients.json)

**Required structure:**
```json
{
  "id": "<snake_case_name>",
  "standard_name": "<Common Name>",
  "latin_name": "<Genus species>",
  "CUI": "<UMLS CUI or null>",
  "aliases": ["<alt_name_1>", "<alt_name_2>"],
  "category": "<fruit|herb|root|mushroom|leaf|flower|bark|seed|algae>",
  "notes": "<Latin name (Family). Active compounds. Traditional uses. Standardization status.>",
  "last_updated": "2026-03-06"
}
```

**Verification required:**
- [ ] Confirm latin binomial via USDA PLANTS database or botanical reference
- [ ] Verify category (plant part used)
- [ ] Check if it should actually be in standardized_botanicals.json instead

### 3.3 — New Harmful Additive (harmful_additives.json)

**Required structure:**
```json
{
  "id": "HA_<UNIQUE_ID>",
  "standard_name": "<Name>",
  "aliases": [],
  "category": "<artificial_sweetener|preservative|colorant|emulsifier|solvent|etc>",
  "mechanism_of_harm": "<Scientific description of harm mechanism>",
  "regulatory_status": {
    "US": "<FDA status>",
    "EU": "<EFSA/EU status>",
    "WHO": "<WHO position>"
  },
  "population_warnings": ["<at-risk populations>"],
  "notes": "<Detailed notes>",
  "scientific_references": ["<DOI or PMID>"],
  "last_updated": "2026-03-06",
  "match_rules": {
    "exact": true,
    "regex": "<pattern if needed>",
    "fuzzy_threshold": 0.85
  },
  "references_structured": [
    {
      "doi": "<DOI>",
      "title": "<Paper title>",
      "year": <year>,
      "finding": "<Key finding>"
    }
  ],
  "external_ids": {
    "umls_cui": "<CUI>",
    "cas": "<CAS number>",
    "pubchem": "<CID>"
  },
  "jurisdictional_statuses": [],
  "severity_level": "<critical|high|moderate|low>"
}
```

**Severity level determination:**
- **critical**: Banned in multiple jurisdictions, proven carcinogen/organ toxin → -5 pts
- **high**: Significant health concerns, banned in some jurisdictions → -3 pts
- **moderate**: Potential concerns, under review → -1.5 pts
- **low**: Minor concerns, generally recognized but with caveats → -0.5 pts

**Verification required:**
- [ ] FDA adverse event reports or warning letters
- [ ] EFSA safety assessment
- [ ] PubMed studies on mechanism of harm
- [ ] At least 1 peer-reviewed reference

### 3.4 — New Banned/Recalled Entry (banned_recalled_ingredients.json)

**THIS IS THE HIGHEST-STAKES DATABASE. ABSOLUTE VERIFICATION REQUIRED.**

```json
{
  "id": "BAN_<UNIQUE_ID>",
  "standard_name": "<Name>",
  "aliases": [],
  "legal_status_enum": "<banned_federal|banned_state|not_lawful_as_supplement|controlled_substance|restricted|under_review|high_risk|adulterant|contaminant_risk|wada_prohibited>",
  "clinical_risk_enum": "<critical|high|moderate|low|dose_dependent>",
  "status": "<banned|recalled|high_risk|watchlist>",
  "match_mode": "active",
  ...full schema fields...
}
```

**MANDATORY FDA VERIFICATION:**
- [ ] Check FDA.gov for official ban notice, warning letter, or recall
- [ ] Check FDA Dietary Supplement Ingredient Advisory List
- [ ] Check DEA scheduling (if controlled substance claim)
- [ ] Check WADA prohibited list (if WADA claim)
- [ ] Document the exact FDA reference URL
- [ ] Cross-check with `banned_match_allowlist.json` — some ingredient names overlap with banned names but are explicitly allowed (e.g., "caffeine" is NOT banned even though it contains substrings of some banned stimulants)

**NEVER add to banned list based on:**
- Blog posts or non-authoritative sources
- Personal opinion about safety
- Single adverse event reports without regulatory action
- Theoretical risk without regulatory classification

### 3.5 — New Allergen Entry (allergens.json)

```json
{
  "id": "ALLERGEN_<NAME>",
  "standard_name": "<Name>",
  "CUI": "<CUI or null>",
  "aliases": [],
  "prevalence": "<low|moderate|high>",
  "severity_level": "<low|moderate|high>",
  "regulatory_status": "<fda_major|eu_allergen|eu_major>",
  "supplement_context": "<How it appears in supplements>",
  "notes": "<Regulatory and clinical details>",
  "category": "<major_allergen|minor_allergen|...>",
  "general_handling": "flag_only",
  "last_updated": "2026-03-06"
}
```

**CRITICAL RULE:** `general_handling` is ALWAYS `"flag_only"`. Allergens never auto-block. Only add allergens that are officially recognized by FDA FALCPA/FASTER Act or EU Regulation 1169/2011 Annex II.

### 3.6 — New Other Ingredient Entry (other_ingredients.json)

```json
{
  "id": "NHA_<UNIQUE_ID>",
  "standard_name": "<Name>",
  "aliases": [],
  "category": "<capsule_shell|binder|flow_agent|coating|sweetener_natural|preservative_natural|solvent|filler|...>",
  "is_additive": <true|false>,
  "additive_type": "<type or null>",
  "allergen": <true|false>,
  "allergen_type": "<type or null>",
  "notes": "<GRAS status, function, safety profile>",
  "CUI": "<CUI>",
  "common_uses": ["<use1>", "<use2>"],
  "last_updated": "2026-03-06"
}
```

**Verification required:**
- [ ] Confirm GRAS status via FDA GRAS database
- [ ] Verify it does NOT belong in harmful_additives.json
- [ ] Check if it's an allergen (set allergen flag appropriately)

### 3.7 — Color Indicator (color_indicators.json)

Simply add the keyword string to the appropriate array:
- `natural_indicators` — Natural color keywords
- `artificial_indicators` — Synthetic/artificial color keywords
- `explicit_natural_dyes` — Confirmed specific natural dye compounds

---

## PHASE 4: CROSS-DATABASE COLLISION CHECK

**Before finalizing ANY addition, verify no cross-database collisions:**

1. **An ingredient CANNOT exist in both `harmful_additives.json` AND `other_ingredients.json`** — it's either harmful or non-harmful, not both
2. **An ingredient CANNOT exist in both `banned_recalled_ingredients.json` AND `ingredient_quality_map.json`** — banned ingredients are not scorable
3. **Check `banned_match_allowlist.json`** — Some names that substring-match banned entries are explicitly allowed
4. **If an ingredient appears in `allergens.json`, it CAN also appear in `other_ingredients.json`** with `allergen: true` flag (e.g., soy lecithin is both an excipient and an allergen)
5. **Botanicals** in `botanical_ingredients.json` should NOT also have entries in IQM unless they have quantifiable bioavailability data for specific forms

Run `scripts/db_integrity_sanity_check.py` after all additions to verify no schema violations or cross-database conflicts.

---

## PHASE 5: IMPLEMENTATION WORKFLOW

For each batch of unmapped ingredients:

### Step 5.1 — Prioritize by occurrence count
Process highest-occurrence unmapped ingredients first (biggest impact on coverage %).

### Step 5.2 — Process in batches of 10-15
Don't try to do everything at once. Process, verify, commit, test.

### Step 5.3 — For each ingredient:
```
1. READ the unmapped name
2. NORMALIZE it (mentally apply normalization.py rules)
3. SEARCH all 7 target databases for existing matches
4. IF potential match found:
   a. VERIFY online (PubChem/UMLS/NIH) that it's the same molecule
   b. If CONFIRMED same → add as alias to existing entry
   c. If DIFFERENT molecule → create new entry (Phase 3)
5. IF no match found:
   a. RESEARCH the ingredient online (what is it? what category?)
   b. CLASSIFY it (Phase 1 decision tree)
   c. CREATE new entry in correct database (Phase 3)
   d. VERIFY all required fields are populated
6. DOCUMENT your decision and evidence
```

### Step 5.4 — After each batch:
```bash
# Validate all database schemas
python scripts/db_integrity_sanity_check.py

# Run enrichment on a sample to verify new mappings work
python scripts/enrich_supplements_v3.py --sample 50

# Check coverage improvement
python scripts/coverage_gate.py

# Run regression tests to ensure nothing broke
python -m pytest scripts/tests/ -x -q
```

### Step 5.5 — Commit with clear message
```
git add scripts/data/<modified_files>
git commit -m "map N unmapped ingredients: X aliases added, Y new entries created

Databases modified:
- ingredient_quality_map.json: +A aliases, +B new entries
- other_ingredients.json: +C aliases, +D new entries
- botanical_ingredients.json: +E new entries
...

Verification: All entries verified via PubChem/UMLS/FDA
Coverage improvement: X.X% → Y.Y%"
```

---

## PHASE 6: QUALITY GATES — DO NOT SKIP

After ALL unmapped ingredients are resolved:

1. **Schema Validation:**
   ```bash
   python scripts/db_integrity_sanity_check.py
   python scripts/validate_database.py
   ```

2. **Full Pipeline Regression:**
   ```bash
   python -m pytest scripts/tests/test_pipeline_regressions.py -v
   python -m pytest scripts/tests/test_db_integrity.py -v
   python -m pytest scripts/tests/test_ingredient_matching_regression.py -v
   ```

3. **Coverage Gate:**
   ```bash
   python scripts/coverage_gate.py
   ```
   Target: ≥99.5% ingredient coverage, ≥98% additive coverage, ≥98% allergen coverage

4. **Cross-Database Overlap Guard:**
   ```bash
   python -m pytest scripts/tests/test_cross_db_overlap_guard.py -v
   ```

5. **Score Stability:**
   ```bash
   python scripts/score_stability_gates.py
   ```

---

## RED FLAGS — STOP AND INVESTIGATE

- **Ingredient name contains brand™ or ® symbols** → Likely a branded form; find the generic compound name, add brand as alias
- **Ingredient name has parenthetical like "as ..." or "from ..."** → This is a form specification; the parent ingredient likely exists, add to its forms in IQM
- **Ingredient appears in >100 products but is unmapped** → High priority, likely a common name variant missing from aliases
- **Ingredient name is very long (>50 chars)** → Probably a blend or compound description, may need manual parsing
- **Ingredient matches a banned name substring** → Check `banned_match_allowlist.json` before flagging; may be a false positive
- **You're unsure about classification** → Default to `other_ingredients.json` with a note flagging for manual review. NEVER put uncertain items in `banned_recalled_ingredients.json`

---

## SUMMARY OF VERIFICATION REQUIREMENTS

| Database | Online Verification Required | Minimum Evidence |
|----------|----------------------------|------------------|
| IQM (aliases) | PubChem same-CID check | Same CAS or PubChem CID |
| IQM (new entry) | PubChem + PubMed bioavailability | Absorption data from literature |
| Botanical (new) | USDA PLANTS or botanical DB | Confirmed latin binomial |
| Harmful additives | FDA/EFSA safety assessment | ≥1 peer-reviewed reference |
| **Banned/recalled** | **FDA.gov official notice** | **Official regulatory action document** |
| Allergens | FDA FALCPA or EU 1169/2011 | Official allergen list membership |
| Other ingredients | FDA GRAS verification | GRAS status confirmation |
| Color indicators | Visual/chemical classification | Standard color chemistry reference |

**The golden rule: When in doubt, DON'T add it. Flag it for manual review. A missing mapping is better than a wrong mapping.**
