# PharmaGuide Pipeline Audit Report

**Date:** 2026-03-06
**Auditor:** Claude (automated audit)
**Pipeline Version:** Enricher v3.x, Scorer v3.1, Schema v5.0.0
**Scope:** Full 8-section audit of the DSLD supplement safety pipeline

---

## Executive Summary

The PharmaGuide pipeline is well-engineered with strong safety architecture. The banned substance database is current through February 2026 FDA actions, and the matching system has robust multi-layer false-positive protection. However, I found **3 confirmed bugs** (1 dosing, 1 scoring, 1 cross-DB), **several risks** worth monitoring, and **multiple quick wins**.

**Priority findings by patient safety impact:**
1. **BUG (HIGH):** Folate UL stored in wrong unit causes false over-UL warnings for prenatal vitamins
2. **BUG (MEDIUM):** B0 penalty overwrite — multiple high_risk/watchlist substances use last-write-wins
3. **BUG (LOW):** 7-Keto DHEA interaction rule references wrong canonical_id
4. **RISK (MEDIUM):** Magnesium adequacy always "excessive" due to RDA > supplemental UL

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

### RISKS

- **25 of 28 interaction rules reference non-banned-DB IDs** — The `subject_ref.canonical_id` field references IDs across multiple databases (IQM, harmful_additives, botanicals) without a `source_db` discriminator field. If any consuming code assumes these IDs are in the banned DB, lookups will fail silently.
  - Examples: `aloe_vera`, `caffeine`, `vitamin_k`, `ADD_PROPYLENE_GLYCOL`
  - Suggestion: Add `source_db` field to `subject_ref` for explicit routing

- **12 of 49 cluster refs in `user_goals_to_clusters.json`** use annotative format (`"Biotin (from Hair & Skin Nutrition)"`) that don't match any `standard_name` in `synergy_cluster.json`. The actual cluster names within parentheses DO resolve. Impact depends on how downstream code parses these.

### VERIFIED OK

- All 12 `id_redirects.json` canonical_ids exist in banned DB
- All 5 allowlist and 4 denylist entries in `banned_match_allowlist.json` have valid canonical_ids
- `_metadata.schema_version` is consistently `"5.0.0"` across all 33 data files
- `_metadata.total_entries: 130` matches actual ingredient count in `banned_recalled_ingredients.json`
- `cross_db_overlap_allowlist.json` has 23 well-documented entries with clear rationale for each overlap

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

None found in spot-checked entries.

### RISKS

- **Synergy cluster ingredient resolution:** The `synergy_cluster.json` ingredient names use simplified names (e.g., "curcumin", "piperine") that must resolve against the IQM's hierarchical structure. The resolution path isn't explicitly validated at enrichment time; a typo in a synergy cluster ingredient name would silently fail to match.

### VERIFIED OK (from IQM structure analysis)

The IQM uses a hierarchical structure (nutrient → form → properties) with `bio_score` rankings. The standard bioavailability hierarchy is correct for the common forms examined:
- Magnesium glycinate/bisglycinate ranks higher than oxide (correct)
- Methylfolate ranks higher than folic acid (correct)
- Methylcobalamin ranks higher than cyanocobalamin (correct)
- D3 (cholecalciferol) ranks higher than D2 (ergocalciferol) (correct)

---

## 5. CLINICAL EVIDENCE INTEGRITY

### BUGS

None found.

### RISKS

- The `backed_clinical_studies.json` (177 entries) uses `evidence_level` and `score_contribution` tiers. The hierarchy (meta-analysis > RCT > cohort > case study) should be periodically cross-referenced against PubMed for accuracy of claims, especially for ingredients where new large-scale studies may have changed the evidence landscape.

### VERIFIED OK

- Evidence level classifications are structurally consistent with standard evidence hierarchy
- Score contribution tiers align with evidence strength (higher evidence = higher score contribution)

---

## 6. SCORING LOGIC BUGS

### BUGS

- **B0 penalty overwrite for multiple substances (MEDIUM)**
  - File: `scripts/score_supplements.py:424-429`
  - When a product has multiple high_risk/watchlist banned substances, `moderate_penalty` is assigned (`=`) not accumulated (`max()` or `+=`)
  - Example: Product has [high_risk(-10), watchlist(-5)] → penalty = 5 (last one wins, should be 10 or 15)
  - Example: Product has [watchlist(-5), high_risk(-10)] → penalty = 10 (order-dependent)
  - **Fix:** Use `moderate_penalty = max(moderate_penalty, new_penalty)` for max-of-all behavior, or `moderate_penalty += new_penalty` for cumulative behavior

- **Adequacy band "excessive" override for Magnesium (DESIGN ISSUE)**
  - File: `scripts/rda_ul_calculator.py:488-489`
  - `if over_ul: return "excessive"` — gives 0 points regardless of pct_rda
  - Magnesium at 100% RDA (400 mg) gets "excessive" (0 pts) because 400 > 350 UL (supplemental)
  - Consider: add an exception for nutrients where UL < RDA (Magnesium), or use a "caution" band instead of "excessive" when amount is within RDA

### RISKS

- **Manufacturer violation penalty can stack to -25** (`score_supplements.py:2023`). Combined with section B penalties (harmful additives, proprietary blends), a product could theoretically lose 60+ points before section A even contributes. The `clamp(0.0, 80.0, ...)` at line 2338 prevents negative scores.

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

### Dead Code / Unused Fields

- `rda_ai_status` and `ul_status` fields in `rda_optimal_uls.json` data entries are universally `null` — could be removed or populated

### Performance Notes

- The banned substance matching loops through all 130 banned items × all ingredients per product. This is O(n*m) but with n=130 and m typically <30, performance is acceptable. The match_mode/entity_type gates reduce actual comparisons.

---

## Summary of Action Items

| # | Severity | Category | Description | File |
|---|----------|----------|-------------|------|
| 1 | **HIGH** | Dosing | Folate UL in wrong unit (1000 mcg folic acid stored as if mcg DFE) | `rda_optimal_uls.json` |
| 2 | **MEDIUM** | Scoring | B0 penalty last-write-wins for multiple substances | `score_supplements.py:424-429` |
| 3 | **LOW** | Cross-DB | 7-Keto DHEA canonical_id typo | `ingredient_interaction_rules.json` |
| 4 | **LOW** | Metadata | clinical_risk_taxonomy total_entries wrong | `clinical_risk_taxonomy.json:7` |
| 5 | **INFO** | Robustness | Denylist regex not wrapped in try/except | `enrich_supplements_v3.py:1602` |
| 6 | **INFO** | Design | interaction_rules subject_ref missing source_db | `ingredient_interaction_rules.json` |
| 7 | **INFO** | Design | Magnesium adequacy always "excessive" | `rda_ul_calculator.py:488` |
