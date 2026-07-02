# SCORING_ENGINE_SPEC.md

> **Version note (read `SCORING_VERSIONS.md` first).** This is the **v3-series**
> server-side quality scorer (code 3.0.1 / shipped 3.4.0). It is the only
> scorer in this repo. Reference-data files stamped `schema_version: 4.0.0` are
> a *different version axis* — there is no "v4 scorer." The scorer emits one
> number in two forms: `score_80` (0–80) and `score_100_equivalent`
> (`= score_80/80*100`); e.g. 77/80 = 96.2/100. Personalized "fit for this
> user" scoring is a **separate device-side scorer in the Flutter app** that
> consumes the Section E blocks (`rda_ul_data`, `dietary_sensitivity_data`,
> `prenatal_coverage`) and is out of scope here.

## Scope

This document specifies the current server-side scoring behavior implemented in:
- `score_supplements.py`
- `config/scoring_config.json`

It is code-accurate for the current v3.0 scorer pipeline.

## Scorer Contract

Scorer is arithmetic-only. It expects enriched products as input.

Required product-level fields:
- `dsld_id`
- `product_name`
- `enrichment_version` (or `enriched_date`)

If required product identity fields are missing, scorer returns `NOT_SCORED` error payload.

## Final Score Formula

```text
quality_raw = A + B + C + D + violation_penalty
quality_score = clamp(0, 80, quality_raw)
score_80 = quality_score
score_100_equivalent = (quality_score / 80) * 100
```

Section caps:
- A max 25
- B max 35
- C max 15
- D max 5

## Pre-Section Gates

Order in `score_product()`:

1. B0 gate (banned/recalled immediate fail checks)
2. Mapping gate
3. Regression guard on unmatched + banned exact/alias overlap

### B0 Gate

Input path:
- `contaminant_data.banned_substances.substances[]`

Match-type semantics:
- Hard-fail eligible types: `exact`, `alias`
- Non-hard-fail types (for now): `token_bounded` and other non-exact/alias values -> review-only flag

Rules:
- `status in {"recalled","both"}` + exact/alias -> `BLOCKED`
- `severity_level in {"critical","high"}` + exact/alias -> `UNSAFE`
- `severity_level == "moderate"` + exact/alias -> adds B0 penalty `10`
- `severity_level == "low"` + exact/alias -> advisory only
- Any review-only hit -> `BANNED_MATCH_REVIEW_NEEDED`

### Mapping Gate

Input paths:
- `ingredient_quality_data.total_active`
- `ingredient_quality_data.unmapped_count`
- `ingredient_quality_data.ingredients[]`

Outputs:
- `mapped_coverage`
- `unmapped_actives` (true mapping gap names)
- `unmapped_actives_total`
- `unmapped_actives_excluding_banned_exact_alias`
- `unmapped_actives_banned_exact_alias`

Stop conditions:
- `total_active <= 0` -> stop with `NO_ACTIVES_DETECTED`
- if `feature_gates.require_full_mapping == true` and `mapped_coverage < 1.0` -> stop with `UNMAPPED_ACTIVE_INGREDIENT`

Current config state:
- `require_full_mapping: true`

### Regression Guard

If an unmatched active overlaps banned substances with `exact/alias` match type:
- scorer forces unsafe path (unless already blocked/unsafe by B0)
- adds `UNMAPPED_BANNED_EXACT_ALIAS_GUARD`

Purpose:
- avoid labeling safety-caught unmatched actives as mapping misses
- enforce `UNSAFE/BLOCKED` behavior for this overlap case

## Section A: Ingredient Quality (max 25)

```text
A = min(25, A1 + A2 + A3 + A4 + A5 + probiotic_bonus)
```

### A1 Bioavailability Form (max 13)

Input:
- `ingredient_quality_data.ingredients_scorable` fallback `ingredient_quality_data.ingredients`

Per ingredient:
- mapped ingredient: use `score` and `dosage_importance`
- unmapped ingredient: fallback `score=9.0`, `weight=1.0`

Type effects:
- `single` type: weights forced to `1.0`
- `multivitamin` type: smoothing `avg = 0.7*avg + 0.3*9.0`

Final:
- `A1 = clamp(0,13,(weighted_avg/18)*13)`

### A2 Premium Forms (max 3)

Rule:
- Count unique canonical ingredients with `score >= 14`
- `A2 = clamp(0,3,0.5 * max(0, count - 1))`

### A3 Delivery System (max 3)

Input:
- `delivery_tier` fallback `delivery_data.highest_tier`

Map:
- tier 1 -> 3
- tier 2 -> 2
- tier 3 -> 1
- else -> 0

### A4 Absorption Enhancer (max 3)

Input:
- `absorption_enhancer_paired` fallback `absorption_data.qualifies_for_bonus`

Rule:
- true -> 3
- false -> 0

### A5 Formulation Excellence (max 3)

Subcomponents:
- A5a organic: +1 when verified or valid claim path
- A5b standardized botanical: +1 when threshold/flag met
- A5c synergy cluster: +1 when cluster qualifying logic met

`A5 = A5a + A5b + A5c` (max 3)

### Probiotic Bonus

Applies only if `supp_type == "probiotic"`.

Gate:
- `feature_gates.probiotic_extended_scoring`
- current state: `false`

Default mode (max 3):
- CFU: +1 when total billion > 1
- Diversity: +1 when strain count >= 3
- Prebiotic: +1 when ingredient names contain inulin/FOS/GOS

Extended mode (max 10):
- CFU up to 4
- Diversity up to 4
- Clinical strain token hits up to 3
- Prebiotic terms up to 3
- Survivability keywords up to 2
- total capped to 10

## Section B: Safety & Purity (max 35)

```text
B = clamp(0,35,35 + bonuses - penalties)
bonuses = B3 + B4a + B4b + B4c
penalties = B0_moderate + B1 + B2 + B5 + B6
```

### B1 Harmful Additives (max penalty 5)

Input:
- `contaminant_data.harmful_additives.additives[]`

Severity map:
- high: 2.0
- moderate: 1.0
- low: 0.5
- none: 0.0

Summed and capped at 5.

### B2 Allergen Presence (max penalty 2)

Input:
- `contaminant_data.allergens.allergens[]`

Severity map:
- high: 2.0
- moderate: 1.5
- low: 1.0

Summed and capped at 2.

### B3 Claim Compliance (max bonus 4)

Primary booleans:
- `claim_allergen_free_validated`
- `claim_gluten_free_validated`
- `claim_vegan_validated`

Fallback derives from `compliance_data`.

Points:
- allergen-free +2
- gluten-free +1
- vegan/vegetarian +1

### B4 Quality Certifications (max bonus 21)

#### B4a Named Programs (max 15)
- +5 per named program, cap 15
- IFOS filtered unless omega-like product context

#### B4b GMP (max 4)
- certified: 4
- fda_registered: 2
- none: 0

#### B4c Batch Traceability (max 2)
- COA: +1
- batch lookup/QR: +1

### B5 Proprietary Blends (max penalty 15)

Inputs:
- `proprietary_blends` fallback `proprietary_data.blends`

Per-blend base by disclosure:
- full: 0
- partial: 3
- none: 6

Per-blend penalty:
- `base * impact_ratio`
- impact by mg share when available, else hidden-count ratio

Summed and capped at 15.
Adds flag `PROPRIETARY_BLEND_PRESENT` when blends exist.

### B6 Marketing Claims Penalty (5)

Input:
- `has_disease_claims` and fallbacks

If true:
- penalty 5
- flag `DISEASE_CLAIM_DETECTED`

## Section C: Evidence & Research (max 15)

Input:
- `evidence_data.clinical_matches[]`

Per match:
- `raw = study_base_points(study_type) * evidence_multiplier(evidence_level)`

Study base points:
- systematic_review_meta: 6
- rct_multiple: 5
- rct_single: 4
- clinical_strain: 4
- observational: 2
- animal_study: 2
- in_vitro: 1

Evidence multipliers:
- product-human/product-rct/product: 1.0
- branded-rct: 0.8
- ingredient-human: 0.65
- strain-clinical: 0.6
- preclinical: 0.3

Dose guard:
- when `min_clinical_dose` exists and product dose is lower after unit conversion:
- multiply by `0.25`
- add flag `SUB_CLINICAL_DOSE_DETECTED`

Capping:
- max 5 points per canonical ingredient
- max 15 for section

## Section D: Brand Trust (max 5)

```text
D = min(5, D1 + D2 + min(1.5, D3 + D4 + D5))
```

Components:
- D1 trusted manufacturer: 2
- D2 full disclosure: 1
- D3 physician formulated: 0.5
- D4 high-standard region: 0.5
- D5 sustainable packaging: 0.5

Combined cap:
- `D3 + D4 + D5` capped at 1.5

## Manufacturer Violation Penalty (Post-Section)

Input:
- `manufacturer_data.violations.total_deduction_applied` (preferred)
- item-level fallback sum of `total_deduction_applied` (or legacy `total_deduction`)

Rules:
- deduction is negative
- added directly to `quality_raw`
- lower-bounded at `-25.0`
- if deduction applied, adds `MANUFACTURER_VIOLATION`

## Verdict Derivation

Precedence (first match wins):
1. `BLOCKED` (`b0.blocked`)
2. `UNSAFE` (`b0.unsafe`)
3. `NOT_SCORED` (mapping gate stop)
4. `CAUTION` (`B0_MODERATE_SUBSTANCE` or `BANNED_MATCH_REVIEW_NEEDED`)
5. `POOR` (`quality_score < 32`)
6. `SAFE`

Backward-compatible `safety_verdict` mapping:
- `POOR -> SAFE`
- `NOT_SCORED -> CAUTION`
- others mirror verdict

## Output Fields (Core)

Top-level score fields:
- `quality_score`
- `score_80`
- `score_100_equivalent`
- `verdict`
- `safety_verdict`
- `breakdown`
- `flags`
- `supp_type`
- `mapped_coverage`
- `unmapped_actives`
- `unmapped_actives_total`
- `unmapped_actives_excluding_banned_exact_alias`

Metadata:
- `scoring_metadata.scoring_version`
- `scoring_metadata.output_schema_version`
- `scoring_metadata.scored_date`
- `scoring_metadata.enrichment_version`
- `scoring_metadata.score_basis`
- `scoring_metadata.reason`

## Current Risk Controls to Watch in Production

1. `unmapped_actives_excluding_banned_exact_alias` trend by category  
2. `NOT_SCORED` rate by category (with full-mapping gate on)  
3. `BANNED_MATCH_REVIEW_NEEDED` volume (token-bounded review load)  
4. verdict drift across runs (`SAFE/POOR/CAUTION/UNSAFE/BLOCKED`)  

