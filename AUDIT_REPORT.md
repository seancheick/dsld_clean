# PharmaGuide Pipeline Audit Report

**Date:** 2026-03-06
**Auditor:** Claude (automated audit)
**Pipeline Version:** Enricher v3.x, Scorer v3.1, Schema v5.0.0
**Scope:** Full 8-section audit of the DSLD supplement safety pipeline

---

## Executive Summary

The PharmaGuide pipeline is well-engineered with strong safety architecture. The banned substance database is current through February 2026 FDA actions, and the matching system has robust multi-layer false-positive protection. However, I found **26 action items**: 1 HIGH, 4 MEDIUM, 8 LOW, 13 INFO — spanning dosing, scoring, clinical evidence, cross-DB integrity, and data quality.

**Priority findings by patient safety impact:**
1. **BUG (HIGH):** Folate UL stored in wrong unit causes false over-UL warnings for prenatal vitamins
2. **BUG (MEDIUM):** B0 penalty overwrite — multiple high_risk/watchlist substances use last-write-wins
3. **BUG (MEDIUM):** Clinical evidence entries for Apigenin, Luteolin have inflated evidence_levels contradicting their own notes
4. **BUG (MEDIUM):** Longvida curcumin clinical entry still claims "65x bioavailability" already debunked in IQM
5. **BUG (LOW):** 7-Keto DHEA interaction rule references wrong canonical_id
6. **RISK (MEDIUM):** Magnesium adequacy always "excessive" due to RDA > supplemental UL

---

## 1. CROSS-DB INTEGRITY

### BUGS

- **`ingredient_interaction_rules.json` → `banned_recalled_ingredients.json` ID mismatch**
  - `RULE_BANNED_7KETO_DHEA_PREGNANCY` references `canonical_id: "BANNED_7KETO_DHEA"`
  - Actual ID in banned DB: `"BANNED_7_KETO_DHEA"` (underscore before KETO)
  - File: `scripts/data/ingredient_interaction_rules.json`
  - Impact: This interaction rule (7-Keto DHEA pregnancy warning) won't resolve to the banned entry

- **`clinical_risk_taxonomy.json` metadata count mismatch**
  - `_metadata.total_entries: 32` but the file contains: conditions(14) + drug_classes(9) + severity_levels(5) + evidence_levels(4) + sources(4) = 36
  - File: `scripts/data/clinical_risk_taxonomy.json:7`
  - Impact: Low (metadata only, not consumed by matching logic)

- **`cross_db_overlap_allowlist.json` has 4 orphaned entries:**
  - 3 borax/borate terms (`"borax"`, `"sodium borate"`, `"sodium tetraborate"`) reference `harmful:iqm` overlap, but no borax entries exist in `harmful_additives.json`. These guard overlaps that don't actually exist — either the harmful_additives entries were removed/renamed or never added.
  - `"dl alpha tocopherol"` has normalization mismatches against both IQM (which stores `"dl-alpha-tocopherol"` with hyphens) and harmful_additives (which has `"dl-alpha tocopherol"` with hyphen between dl and alpha). The allowlist term `"dl alpha tocopherol"` (spaces only) won't match either.

### RISKS

- **25 of 28 interaction rules reference non-banned-DB IDs** — The `subject_ref.canonical_id` field references IDs across multiple databases (IQM, harmful_additives, botanicals) without a `source_db` discriminator field. If any consuming code assumes these IDs are in the banned DB, lookups will fail silently.
  - Examples: `aloe_vera`, `caffeine`, `vitamin_k`, `ADD_PROPYLENE_GLYCOL`
  - Suggestion: Add `source_db` field to `subject_ref` for explicit routing

- **Synergy cluster → IQM resolution gap** — Of 408 unique ingredient names across 54 synergy clusters, ~300 do not directly match any top-level IQM key. Synergy clusters use human-readable/form-specific names (e.g., "magnesium glycinate", "ubiquinol", "ksm-66") while IQM uses normalized programmatic keys (e.g., `magnesium`, `coq10`, `ashwagandha`). No visible mapping layer bridges the two naming conventions. If any code path looks up synergy ingredient names directly in IQM, it will fail silently for most entries.

- **12 of 49 cluster refs in `user_goals_to_clusters.json`** use annotative format (`"Biotin (from Hair & Skin Nutrition)"`) that don't match any `standard_name` in `synergy_cluster.json`. The actual cluster names within parentheses DO resolve. Impact depends on how downstream code parses these.

- **Multi-array files have ambiguous `total_entries`** — Files like `banned_match_allowlist.json` (total_entries=5 counts allowlist only, excludes 4 denylist entries), `color_indicators.json` (counts one of four arrays), and `functional_ingredient_groupings.json` count only their primary array, which could mislead consumers expecting a total across all arrays.

### VERIFIED OK

- All 12 `id_redirects.json` canonical_ids exist in banned DB
- All 5 allowlist and 4 denylist entries in `banned_match_allowlist.json` have valid canonical_ids
- All 28 interaction rule subject_refs resolve in their respective target DBs (IQM: 18, banned: 3, botanical: 3, harmful_additives: 1, other_ingredients: 1)
- `_metadata.schema_version` is consistently `"5.0.0"` across all 33 data files
- `_metadata.total_entries: 130` matches actual ingredient count in `banned_recalled_ingredients.json`
- `total_entries` correct for all 23 single-primary-array files

---

## 2. BANNED SUBSTANCE MATCHING ACCURACY

### BUGS

None found. The matching system is well-designed.

### RISKS

- **Token-bounded matching could produce false positives for very short aliases.** The `_is_low_precision_token_alias` filter (enricher line 1449) catches many cases, but any 4+ character alias that isn't in the explicit deny list could still match. Example: if a banned substance had alias "iron" it could match "iron bisglycinate" via token-bounded. Mitigated by: (a) the B0 scorer only trusts exact/alias matches (line 409), not token_bounded; (b) negative_match_terms provide per-entry exclusions.

- **Denylist regex patterns come from JSON data** (enricher line 1602: `re.search(pattern, ing_norm)` where `pattern` from `banned_match_allowlist.json`). If a malformed regex is introduced into the data file, it would crash the enricher. Consider wrapping in try/except.

### VERIFIED OK

- **All recent FDA-flagged substances are covered** (verified against 2025-2026 FDA actions):
  - Meloxicam (`ADULTERANT_MELOXICAM`) — Jan 2026 123Herbals recall
  - Tianeptine (`BANNED_TIANEPTINE` + `SPIKE_TIANEPTINE_ANALOGUES`) — ongoing enforcement
  - 1,4-DMAA (`BANNED_DMAA` + DMAA analogs watchlist) — Modern Warrior Jan 2026 recall
  - Ibutamoren/MK-677 (`BANNED_IBUTAMOREN_MK677`) — Agebox Oct 2025 recall
  - Aniracetam (`NOOTROPIC_ANIRACETAM`) — Modern Warrior recall
  - Phenibut (`BANNED_PHENIBUT`) — ongoing FDA enforcement
  - DMHA (`BANNED_DMHA`) — FDA March 2023 enforcement
  - BMPEA (`BANNED_BMPEA`) — FDA 2015 warnings
  - Sildenafil/Tadalafil (multiple entries including designer analogs)
  - Methocarbamol (`SPIKE_METHOCARBAMOL`) — spiking agent

- **Multi-layer false-positive protection is robust:**
  1. Entity type filtering (skip class/umbrella entries via `match_mode: disabled`)
  2. Negative match terms per entry
  3. Negation pattern detection ("ephedra-free", "contains no X", "X-free")
  4. Low-precision alias filtering for token-bounded matches
  5. Allowlist/denylist system
  6. B0 scorer gates on exact/alias matches only (token_bounded → review only)

- **Word boundary matching** in `_token_bounded_match` uses `(?<![a-z0-9])` / `(?![a-z0-9])` lookbehind/lookahead, preventing substring collisions

Sources for FDA verification:
- [FDA Dietary Supplement Updates](https://www.fda.gov/food/dietary-supplements/whats-new-dietary-supplements)
- [FDA Warning Letters Database](https://www.fda.gov/food/compliance-enforcement-food/warning-letters-related-food-beverages-and-dietary-supplements)
- [Partnership for Safe Medicines - Jan 2026](https://www.safemedicines.org/2026/01/fda-alert-supplements-with-undeclared-drug-ingredients.html)

---

## 3. DOSING ACCURACY

### BUGS

- **Folate UL unit mismatch (HIGH SEVERITY)**
  - File: `scripts/data/rda_optimal_uls.json:1527-1531`
  - The Folate entry has `unit: "mcg DFE"` and `highest_ul: 1000`, with age-specific ULs of 800 (14-18) and 1000 (19+)
  - The NIH/IOM UL for folate is 1,000 mcg **of folic acid** (not DFE). In DFE terms, this equals 1,700 mcg DFE (since 1 mcg folic acid = 1.7 mcg DFE)
  - The unit converter (`scripts/unit_converter.py:168-169`) converts folic acid from mcg to mcg DFE using factor 1.7
  - **Result:** Any product with >588 mcg folic acid triggers a false over-UL warning:
    - 600 mcg folic acid → 1,020 mcg DFE → flagged as 102% UL (actually 60% of real UL)
    - 800 mcg folic acid → 1,360 mcg DFE → flagged as 136% UL (actually 80% of real UL)
    - Most prenatal vitamins (800-1000 mcg folic acid) would be incorrectly flagged
  - **Fix:** Change the Folate UL values in rda_optimal_uls.json to DFE terms: 1,360 mcg DFE (for 14-18) and 1,700 mcg DFE (for 19+). Or add a unit annotation on UL values indicating they are in mcg folic acid.

### RISKS

- **Magnesium RDA > supplemental UL** is a known IOM quirk but causes scoring issues:
  - RDA: 310-420 mg (from diet + supplements)
  - UL: 350 mg (supplemental only)
  - Every magnesium supplement at therapeutic doses (400+ mg) will be flagged `over_ul: true` and get `adequacy_band: "excessive"` (0 points) at `rda_ul_calculator.py:488-489`
  - This is scientifically defensible but penalizes quality magnesium supplements unfairly in scoring

- **Methylfolate DFE conversion factor (1.7)** — `unit_conversions.json:188` uses the same DFE factor as folic acid. This is debated in the literature; 5-MTHF is already the active form, and some experts argue 1:1 DFE conversion is more appropriate. The current 1.7 factor is the conservative/official position.

- **Vitamin E UL note is misleading** — `rda_optimal_uls.json:532` says "UL applies to synthetic alpha-tocopherol only" but per the IOM report, the UL of 1000 mg applies to any form of supplemental alpha-tocopherol (both natural and synthetic). This should be corrected.

- **Omega-3 AI is for ALA, not EPA+DHA** — The AI of 1.1-1.6g in `rda_optimal_uls.json` is for total omega-3 as ALA (alpha-linolenic acid). Most omega-3 supplements contain EPA+DHA (fish oil), not ALA. There is no established AI specifically for EPA+DHA. The file doesn't clarify this distinction, which could lead to incorrect adequacy comparisons for fish oil supplements.

- **Vitamin E unit string mismatch** — `rda_optimal_uls.json` uses `"unit": "mg alpha-tocopherol"` for Vitamin E, while `unit_conversions.json` converts IU to `"mg"`. The unit strings don't match exactly, which could cause comparison failures if the RDA calculator tries to match units between the two files.

### VERIFIED OK (10/10 nutrient spot-check)

| Nutrient | RDA | UL | Status |
|----------|-----|-----|--------|
| Vitamin A | M:900, F:700 mcg RAE | 3000 mcg RAE | Correct per NIH ODS |
| Vitamin D | 15 mcg (14-70), 20 mcg (71+) | 100 mcg | Correct |
| Vitamin C | M:90, F:75 mg | 2000 mg | Correct |
| Iron | M:8, F:18 mg | 45 mg | Correct |
| Calcium | 1000-1300 mg | 2000-3000 mg by age | Correct |
| Magnesium | M:400-420, F:310-320 mg | 350 mg (suppl.) | Correct |
| Zinc | M:11, F:8 mg | 34-40 mg by age | Correct |
| B12 | 2.4 mcg | No UL | Correct |
| Folate | 400 mcg DFE | **See bug above** | UL value incorrect |
| Omega-3 | M:1.6g AI, F:1.1g AI | No UL | Correct |

### Unit Conversion Factors VERIFIED OK

| Conversion | Pipeline Value | NIH/FDA Standard | Status |
|-----------|---------------|-----------------|--------|
| Vitamin D IU→mcg | 0.025 | 0.025 | Correct |
| Vitamin A retinol IU→mcg RAE | 0.3 | 0.3 | Correct |
| Vitamin A beta-carotene (supp) IU→mcg RAE | 0.1 | 0.1 | Correct |
| Vitamin E natural IU→mg | 0.67 | 0.67 | Correct |
| Vitamin E synthetic IU→mg | 0.45 | 0.45 | Correct |
| Folic acid mcg→mcg DFE | 1.7 | 1.7 | Correct |

---

## 4. INGREDIENT QUALITY MAP ACCURACY

### BUGS

- **Curcumin enhanced forms marked `natural: true`** — Meriva (phosphatidylcholine phytosome), Theracurmin (colloidal submicron), BCM-95, CurcuWin, HydroCurc, and Longvida are all engineered delivery technologies, not "natural" in any conventional sense. The base curcumin is plant-derived, but the delivery form is engineered.

### RISKS

- **`natural` flag lacks consistent definition** — Sometimes means "naturally occurring chemical form" (methylcobalamin B12), sometimes "naturally sourced" (cod liver oil), sometimes "plant-derived base ingredient" (curcumin forms). For a medical-grade pipeline, this ambiguity is a consumer safety concern. Methylcobalamin, adenosylcobalamin, and hydroxocobalamin are marked `natural: true` but supplemental forms are synthetically manufactured.

- **Curcumin + BioPerine scored aggressively low** (bio_score=7, only 1 above plain curcumin) based on a single Verhoeven 2025 study debunking piperine enhancement. If this study has limitations or is not replicated, this downgrade may be premature.

- **Missing internationally common forms:** Iron hydroxide polymaltose (Maltofer, widely used outside US), magnesium glycerophosphate (European supplements), magnesium pidolate (common in Italy/France), zinc acetate dihydrate (Cochrane-reviewed cold lozenge form).

- **Synergy cluster ingredient resolution:** The `synergy_cluster.json` ingredient names use simplified names (e.g., "curcumin", "piperine") that must resolve against the IQM's hierarchical structure. The resolution path isn't explicitly validated at enrichment time; a typo in a synergy cluster ingredient name would silently fail to match.

### VERIFIED OK (10/10 bio_score rankings correct)

| Ingredient | Higher Form (score) | Lower Form (score) | Correct? |
|-----------|-------------------|-------------------|----------|
| Magnesium | Glycinate (14) | Oxide (4) | Yes |
| Folate | 5-MTHF (14) | Folic acid (6) | Yes |
| Vitamin B12 | Methylcobalamin (14) | Cyanocobalamin (10) | Yes |
| Iron | Bisglycinate (14) | Ferrous sulfate (8) | Yes |
| Zinc | Picolinate (14) | Oxide (5) | Yes |
| Calcium | Citrate (14) | Carbonate (8) | Yes |
| CoQ10 | Ubiquinol (13) | Ubiquinone (10) | Yes |
| Curcumin | Meriva/phytosome (12) | Plain C3 (6) | Yes |
| Omega-3 | rTG form (14) | Ethyl ester (9) | Yes |
| Vitamin D | D3 (12) | D2 (7) | Yes |

---

## 5. CLINICAL EVIDENCE INTEGRITY

### BUGS

- **LONGVIDA curcumin: cross-file contradiction** (`backed_clinical_studies.json` ~line 971) — Claims "65x higher free curcumin bioavailability" in `notable_studies`, but `ingredient_quality_map.json` already incorporates Verhoeven 2025 debunking this claim (scores Longvida at bio_score=7, states "NO improvement over unformulated curcumin"). The clinical evidence file was not updated to reflect the debunking.

- **APIGENIN: evidence_level contradicts own notes** (`backed_clinical_studies.json` ~line 2904) — Listed as `evidence_level: "ingredient-human"`, `study_type: "rct_multiple"`, but `published_studies` lists only `["mechanistic", "in-vitro"]` and notes say "no dedicated apigenin-alone RCTs exist." Should be `evidence_level: "preclinical"`.

- **LUTEOLIN: same contradiction** (~line 2931) — `evidence_level: "ingredient-human"`, `study_type: "rct_single"`, but `published_studies: ["mechanistic", "animal"]` and notes say "No standalone RCTs." Only human evidence is a combination product (PEA+luteolin).

- **ZYLOFRESH: published_studies contradicts notes** (~line 418) — `evidence_level: "preclinical"` but `published_studies` includes `"RCT"`. Notes explicitly say "No published clinical trials found."

- **SPERMIDINE: published_studies not updated** (~line 2850) — `evidence_level: "ingredient-human"` but `published_studies: ["mechanistic", "animal"]`. Notable_studies cites small human DB-RCTs (n=30, n=37) that aren't reflected in the published_studies array.

- **BIOPERINE: not updated with Verhoeven 2025** (~line 859) — Still cites Shoba 1998 "2000% increase" claim with only Fanca-Berthon 2021 replication concern noted. The IQM already incorporates the stronger Verhoeven 2025 debunking but this file has not been updated.

- **IODINE: study_type inconsistency** (~line 4340) — `study_type: "observational"` but `published_studies` includes `"RCT"`. If actual RCTs exist, study_type should be upgraded.

### RISKS

- **Meriva CRP claim** — Notable_studies states "CRP 168->11 mg/L" which is an extreme drop. Normal CRP is <10 mg/L; 168 mg/L is exceptionally elevated. This may be a unit error (hs-CRP in mg/dL?) or subset data reporting. Should be verified against the Belcaro 2010 publication.

### VERIFIED OK

- Score contribution tier math is correct for sampled entries (tier_1/tier_2/tier_3 brackets match formula)
- Notable study citations verified for KSM-66 Ashwagandha (Chandrasekhar 2012), Setria Glutathione (Richie 2015), MitoQ (Rossman 2018)
- Preclinical entries (Fisetin, AKG) correctly classified as tier_3
- Evidence hierarchy (meta-analysis > RCT > cohort > case study) structurally correct

---

## 6. SCORING LOGIC BUGS

### BUGS

- **B0 penalty overwrite for multiple substances (MEDIUM)**
  - File: `scripts/score_supplements.py:424-429`
  - When a product has multiple high_risk/watchlist banned substances, `moderate_penalty` is assigned (`=`) not accumulated (`max()` or `+=`)
  - Example: Product has [high_risk(-10), watchlist(-5)] → penalty = 5 (last one wins, should be 10 or 15)
  - Example: Product has [watchlist(-5), high_risk(-10)] → penalty = 10 (order-dependent)
  - **Fix:** Use `moderate_penalty = max(moderate_penalty, new_penalty)` for max-of-all behavior, or `moderate_penalty += new_penalty` for cumulative behavior

- **B2 allergen scoring lacks deduplication (LOW)**
  - File: `scripts/score_supplements.py:1026-1029`
  - When a product lists multiple ingredients that trigger the same allergen (e.g., "whey protein" and "milk powder" both flag Milk), the allergen penalty is applied once per triggering ingredient instead of once per unique allergen
  - Impact: Products with multiple dairy/soy/gluten ingredients receive inflated allergen penalties
  - **Fix:** Deduplicate allergen hits by allergen type before applying penalties

- **Adequacy band "excessive" override for Magnesium (DESIGN ISSUE)**
  - File: `scripts/rda_ul_calculator.py:488-489`
  - `if over_ul: return "excessive"` — gives 0 points regardless of pct_rda
  - Magnesium at 100% RDA (400 mg) gets "excessive" (0 pts) because 400 > 350 UL (supplemental)
  - Consider: add an exception for nutrients where UL < RDA (Magnesium), or use a "caution" band instead of "excessive" when amount is within RDA

### RISKS

- **Manufacturer violation penalty can stack to -25** (`score_supplements.py:2023`). Combined with section B penalties (harmful additives, proprietary blends), a product could theoretically lose 60+ points before section A even contributes. The `clamp(0.0, 80.0, ...)` at line 2338 prevents negative scores.

- **`manufacturer_violations.json` user-facing notes overstate penalties** — The human-readable `note` fields in violation entries show pre-multiplier penalty totals. When the scorer applies its own multiplier/cap logic, the actual penalty differs from what's documented. This could mislead anyone debugging scores against the data file.

- **Dual normalization paths** — The enricher's `_normalize_text` and the scorer's internal normalization don't share a single implementation. If they diverge (e.g., one strips parentheticals and the other doesn't), enricher-produced keys may not match scorer expectations.

- **Thread-safety of `_last_b5_blend_evidence`** — This scorer instance variable (`score_supplements.py`) is written during scoring and read for output formatting. In a concurrent/multi-threaded scoring context, this could produce race conditions. Currently single-threaded, but worth noting for future parallelization.

- **Parenthetical content stripping** — The enricher strips parenthetical content from ingredient names during normalization (e.g., "Vitamin D3 (as cholecalciferol)" → "Vitamin D3"). If a database entry's canonical name includes parenthetical content, the stripped form won't match.

### VERIFIED OK

- Score bounds: properly clamped 0-80 (mapped to 0-100 for display at line 2092)
- Section weights sum correctly: A(25) + B(30) + C(20) + D(5) = 80
- No double-counting between sections: B0 penalties feed into section B via `b0_moderate_penalty` parameter, not applied twice
- B0 BLOCKED/UNSAFE correctly short-circuit scoring (line 2231-2287)
- Manufacturer violation penalty correctly capped at -25 (line 2023)
- Section B bonuses capped at 5.0, penalties are unbounded within section (line 1514-1515)
- `_build_core_output` correctly maps 80-scale to 100-scale (line 2092)
- Verdict derivation properly gates on B0 status before computing section scores

---

## 7. PIPELINE DATA FLOW INTEGRITY

### BUGS

None found.

### RISKS

- The pipeline (`run_pipeline.py`) runs Clean → Enrich → Coverage Gate → Score sequentially with proper error gating. A coverage gate (Stage 2.5) blocks scoring if enrichment coverage is too low.

- **Normalization consistency:** The `_normalize_text` function in the enricher (line 958) handles Greek beta, micro sign, dashes, etc. If the cleaner uses a different normalization strategy, ingredients could become unmatchable. The enricher imports from the normalization module for consistency, which is good.

### VERIFIED OK

- Pipeline stages run in correct order with proper gating
- Coverage gate prevents low-quality enriched data from reaching scoring
- `EnrichmentContractValidator` enforces 7 contract rules (sugar consistency, allergen precedence, color consistency, serving basis integrity, claims consistency, provenance integrity, match ledger consistency)
- The enricher's `match_mode` gate correctly skips `disabled` and `historical` banned entries

---

## 8. QUICK WINS

### Identified Improvements

1. **Fix the Folate UL values** — Highest-priority data fix. Change folate UL in `rda_optimal_uls.json` from 1000 to 1700 mcg DFE (or add explicit `ul_unit: "mcg folic acid"` annotation).

2. **Fix B0 moderate_penalty accumulation** — Change `moderate_penalty = 10` (line 425) to `moderate_penalty = max(moderate_penalty, 10)` and similarly for watchlist. Low-effort, prevents order-dependent scoring.

3. **Fix 7-Keto DHEA canonical_id** — Change `BANNED_7KETO_DHEA` to `BANNED_7_KETO_DHEA` in `ingredient_interaction_rules.json`.

4. **Fix clinical_risk_taxonomy metadata count** — Update `total_entries` from 32 to the correct count (14 conditions + 9 drug_classes = 23 if counting primary entities, or 36 for all arrays).

5. **Add try/except around denylist regex patterns** — `enricher line 1602` uses `re.search(pattern, ...)` with patterns from JSON. A malformed regex would crash the entire enrichment run.

6. **Add `source_db` to interaction rule `subject_ref`** — The 28 interaction rules reference IDs across 4+ databases without indicating which DB to look up. This makes cross-DB validation and runtime lookups fragile.

7. **Consider Magnesium UL exception in adequacy banding** — The current system penalizes every therapeutic magnesium supplement. A nutrient-specific exception for cases where IOM UL < RDA would improve scoring accuracy.

8. **Deduplicate B2 allergen hits** — Change allergen penalty loop to collect unique allergen types first, then apply penalty once per type. Prevents double-penalizing products with multiple dairy/soy sources.

9. **Move hardcoded scoring lists to config** — Several lists in `score_supplements.py` (e.g., probiotic strain lists, vitamin form preference lists) are hardcoded. Moving them to a JSON config file would make updates easier and avoid code changes for data corrections.

10. **Replace `json.dumps` in probiotic strain checking** — The scorer uses `json.dumps()` to serialize ingredient data for string searching during probiotic identification. A direct key lookup or set intersection would be both faster and more reliable.

### Dead Code / Unused Fields

- `rda_ai_status` and `ul_status` fields in `rda_optimal_uls.json` data entries are universally `null` — could be removed or populated
- **`ingredient_weights.json` is dead data** — Defined/loaded in `constants.py:30` but never referenced by any scoring or enrichment logic. The file exists in `scripts/data/` but no code path consumes its weights. Can be safely removed or documented as deprecated.

### Performance Notes

- The banned substance matching loops through all 130 banned items × all ingredients per product. This is O(n*m) but with n=130 and m typically <30, performance is acceptable. The match_mode/entity_type gates reduce actual comparisons.

---

## Summary of Action Items

| # | Severity | Category | Description | File |
|---|----------|----------|-------------|------|
| 1 | **HIGH** | Dosing | Folate UL in wrong unit (1000 mcg folic acid stored as if mcg DFE) | `rda_optimal_uls.json` |
| 2 | **MEDIUM** | Scoring | B0 penalty last-write-wins for multiple substances | `score_supplements.py:424-429` |
| 3 | **MEDIUM** | Clinical | APIGENIN evidence_level "ingredient-human" contradicts own notes ("no RCTs") | `backed_clinical_studies.json` |
| 4 | **MEDIUM** | Clinical | LUTEOLIN evidence_level "ingredient-human" contradicts published_studies ["mechanistic","animal"] | `backed_clinical_studies.json` |
| 5 | **MEDIUM** | Clinical | LONGVIDA still claims 65x bioavailability; IQM already has Verhoeven 2025 debunking | `backed_clinical_studies.json` |
| 6 | **LOW** | Cross-DB | 7-Keto DHEA canonical_id typo | `ingredient_interaction_rules.json` |
| 7 | **LOW** | Cross-DB | 4 orphaned entries in cross_db_overlap_allowlist (borax x3, dl-alpha-tocopherol) | `cross_db_overlap_allowlist.json` |
| 8 | **LOW** | Metadata | clinical_risk_taxonomy total_entries wrong | `clinical_risk_taxonomy.json:7` |
| 9 | **LOW** | Clinical | ZYLOFRESH published_studies includes "RCT" but notes say "no clinical trials" | `backed_clinical_studies.json` |
| 10 | **LOW** | Clinical | SPERMIDINE/BIOPERINE published_studies arrays not updated | `backed_clinical_studies.json` |
| 11 | **LOW** | Clinical | IODINE study_type "observational" but published_studies includes "RCT" | `backed_clinical_studies.json` |
| 12 | **LOW** | IQM | Curcumin enhanced forms (Meriva, Theracurmin etc.) marked `natural: true` | `ingredient_quality_map.json` |
| 13 | **INFO** | Robustness | Denylist regex not wrapped in try/except | `enrich_supplements_v3.py:1602` |
| 14 | **INFO** | Cross-DB | Synergy cluster → IQM resolution gap (~300/408 names unresolvable) | `synergy_cluster.json` |
| 15 | **INFO** | Design | interaction_rules subject_ref missing source_db | `ingredient_interaction_rules.json` |
| 16 | **INFO** | Design | Magnesium adequacy always "excessive" | `rda_ul_calculator.py:488` |
| 17 | **INFO** | Data | Vitamin E UL note says "synthetic only" but applies to all forms | `rda_optimal_uls.json:532` |
| 18 | **INFO** | Data | Omega-3 AI is for ALA, not EPA+DHA (undocumented) | `rda_optimal_uls.json:5373` |
| 19 | **INFO** | Data | Vitamin E unit string mismatch between RDA and converter DBs | `rda_optimal_uls.json` / `unit_conversions.json` |
| 20 | **INFO** | IQM | `natural` flag lacks consistent definition across entries | `ingredient_quality_map.json` |
| 21 | **LOW** | Scoring | B2 allergen penalty not deduplicated by allergen type | `score_supplements.py:1026-1029` |
| 22 | **INFO** | Data | `manufacturer_violations.json` notes show pre-multiplier penalties | `manufacturer_violations.json` |
| 23 | **INFO** | Dead Code | `ingredient_weights.json` loaded but never consumed | `constants.py:30` / `ingredient_weights.json` |
| 24 | **INFO** | Robustness | Dual normalization paths between enricher and scorer | `enrich_supplements_v3.py` / `score_supplements.py` |
| 25 | **INFO** | Robustness | `_last_b5_blend_evidence` not thread-safe | `score_supplements.py` |
| 26 | **INFO** | Robustness | Parenthetical stripping may prevent DB key matching | `enrich_supplements_v3.py` |
