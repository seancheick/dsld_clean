# Pipeline Audit Fixes — 2026-07

Deep correctness audit of the clean (`enhanced_normalizer.py`) and enrich
(`enrich_supplements_v3.py`) stages, triggered by two bugs found while building
the prenatal reference label:

- **A4 absorption bonus dead for every product** — enrichment read
  `enhancer.get('name')` but `absorption_enhancers.json` only defines
  `standard_name` (fixed previously).
- **Allergen negation false positive** — the cleaner parsed *"Contains no
  milk, egg, …"* as containing those allergens (fixed previously).

The audit hunted siblings of those two bug classes (wrong dict key vs the real
DB schema, falsy short-circuits, regex polarity, first-match-wins ordering,
normalization asymmetry, numeric errors, enrichment→scorer contract drift)
across all pipeline code, cross-checked against a ground-truth schema map of
all 27 reference DBs.

## Verified green (no change needed)

- Banned / harmful / allergen **live** matchers: correct payload + entry keys,
  correct negation guards — no silent match-death on the safety path.
- Every reference-DB read in `enrich_supplements_v3.py` (delivery, botanicals,
  synergy, evidence, strains, RDA, quality map forms, cert rules).
- `proprietary_blend_detector.py`, `batch_processor.py` DB access.
- IU/unit conversion factors (`unit_conversions.json` ↔ converters) and dose
  parsing (commas, ranges, `<`/`>`).
- Enrichment→scorer projected-field contract (`_project_scoring_fields`).

## Fixes in this change

### 1. Company-name fuzzy matching cross-matched distinct companies (HIGH)
`_fuzzy_company_match` scored `max(WRatio, partial_ratio) >= 0.85`;
`partial_ratio` returns ~1.0 for any substring containment, so
"HUM Nutrition" ≈ "Goli Nutrition Inc." (0.87) and brand
"Country Life Gut Connection" ≈ "Garden of Life" (0.855 — observed on a real
DSLD product). Replaced with: normalized-equal → multi-token subset
(same-name variations, ≥0.75) → single distinctive leading brand token
("Thorne" ⊂ "Thorne Research", ≥6 chars, non-possessive) → otherwise
near-exact WRatio (≥0.90). Substring containment alone never matches.

### 2. Violation penalties applied on any fuzzy hit (HIGH)
`_check_violations` attached a violator's `total_deduction_applied` (worth up
to −25 points) on any fuzzy match. Now requires match confidence ≥ 0.95
(normalized-exact or same-name variation); weaker hits are recorded in an
audit-only `near_misses` list with **no deduction**.

### 3. Top-manufacturer resolution was iteration-order dependent (MEDIUM)
`_check_top_manufacturer` returned on the first fuzzy hit inside the per-entry
loop, so an early weak fuzzy match preempted a later exact match; the fuzzy
path also ignored aliases. Now two passes: exact across the whole list first,
then best-scoring fuzzy across all entries (std_name + aliases).

### 4. `normalize_company_name` ate word endings (MEDIUM)
The corporate-suffix regex allowed zero separators, stripping glued 2-letter
suffixes: "Costco" → "cost", "Visa" → "vi". The suffix now must be its own
token (preceded by whitespace or a comma).

### 5. Delivery detection substring false positives (MEDIUM)
`_collect_delivery_data` matched DB keys as raw substrings: "raw" (tier 3)
matched inside "Strawberry" → spurious A3 bonus. Keys now match on word
boundaries via precompiled patterns.

### 6. Ingredient names/forms invisible to pattern scanners (MEDIUM)
`_get_all_product_text` omitted active-ingredient names and form names,
contradicting `enhanced_delivery.json`'s own detection_note ("search …
ingredient forms + product name"). A product whose only delivery signal was an
ingredient like "Liposomal Vitamin C" earned no A3 credit. Names and form
names are now part of the searchable text (this also lets branded-ingredient
evidence gating see ingredient-level brand mentions).

### 7. Exclusion rule dropped valid labels (LOW, latent)
Per MATCHING_PRECEDENCE.md, a candidate is skipped only when the label is
ONLY exclusion terms ("Natural flavoring"), never when a real identifier is
present ("Curcumin Natural"). The code skipped on ANY exclusion hit. Latent
today (all `exclusions[]` are empty) — fixed to spec before it can misfire.

### 8. Cleaner alias-collision winner was JSON file order (LOW)
`_build_enhanced_indices` resolved collided alias variations "keep first" in
raw `ingredient_quality_map.json` iteration order. Entries are now iterated in
`match_rules.priority` order (P0 compound > P1 botanical > P2 category,
alphabetical tiebreak), so "first" == "highest priority" per spec.

### 9–11. Dead-code key mismatches (cleanup; zero scoring impact)
- `_process_contacts` read payload key `manufacturers` (real key:
  `top_manufacturers`) and a per-entry `score_contribution` that doesn't
  exist, and substring-matched names. Now recognizes contacts by normalized
  exact match (std_name + aliases) into a new `isTopManufacturer` flag;
  `manufacturerScore` is retained as a deprecated always-None field.
  (Authoritative trust remains enrichment's exact-only `_check_top_manufacturer`.)
- `_check_banned_recalled`'s substring pass iterated legacy section names that
  no longer exist in the v3 DB (single `ingredients` payload) → the pass was
  silently dead. It now iterates the dynamically discovered arrays, restricted
  to critical/high-severity items. (Function currently has no callers.)
- The fast-lookup delivery entry read `points` (nonexistent); it now carries
  the DB's real `tier`.

## Deliberate non-change: match_source vs priority ordering

`_match_quality_map`'s sort key ranks `match_source` (raw label name >
derived standardName) above `match_rules.priority`. The audit flagged this as
a spec deviation; investigation showed it is deliberate provenance handling
(dedicated "raw_name_priority" ambiguity reasons + logging) and the regression
corpus pins it. Changing it would churn scores without a demonstrated defect.
Documented in MATCHING_PRECEDENCE.md ("Match-Source Dimension") instead.

## Verification

- New regression tests written **before** each fix:
  `tests/test_company_match_hardening.py` (10),
  `tests/test_delivery_detection_hardening.py` (10),
  `tests/test_precedence_hardening.py` (3) — all failing pre-fix on the bug
  cases, all passing post-fix.
- Full suite green (only pre-existing, documented
  `test_missing_match_tokens_report_empty` environment failure remains).
- Before/after corpus run (4 real DSLD products + prenatal reference label):
  the ONLY behavioral delta is the intended one — "Digestive Balance" (brand
  "Country Life Gut Connection") no longer fuzzy-misattributes to
  "Garden of Life". All scores/verdicts/tiers otherwise identical; the
  prenatal label holds at 77.0/80 SAFE.
