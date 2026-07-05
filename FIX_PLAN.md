# Pipeline Fix Plan

Companion to `CODE_REVIEW_FINDINGS.md` (2026-07-05). Fixes are grouped into four phases ordered by user impact. Each item lists the file(s), the change, and the regression test to add. **After each phase: run the full test suite plus a full pipeline run on a fixed input set, then diff scored outputs against the pre-fix baseline** (score deltas are expected and should be reviewed, not feared — today's outputs contain the bugs).

Baseline to capture BEFORE any fix: one full pipeline run's `scored/` output + `reports/`, committed or archived, so every phase's score drift is measurable.

---

## Phase 1 — Safety-inverting output & silent data loss (P0)

**1.1 Colors identity corruption** — `enhanced_normalizer.py:1912-1940`
Move the explicit-dye check to run only after alias/probiotic/vitamin lookups fail; replace substring with whole-token equality; skip when the name resolves in `ingredient_alias_lookup`.
Test: `Riboflavin`, `Beta-Carotene`, `Mixed Tocopherols`, `Turmeric Root Extract`, `Lutein` map to themselves; `FD&C Red 40` still maps to artificial colors.

**1.2 Safety-DB generic-key collapse** — `enhanced_normalizer.py:1797-1815, :978` (+ data)
Stop indexing `preprocess_text(standard_name)` for harmful/banned lookups; index curated aliases/`label_tokens` only; add a guard rejecting single-generic-token keys (`vitamins`, `chromium`, `corn`, `green tea`…). Stop stripping `d-`/`dl-`/`natural `/`synthetic `/`organic ` and ` extract/ powder/ oil/ concentrate` from *identity* keys (`normalization.py:247-265`) — keep a separate fuzzy-only key if wanted.
Test: `Chromium` (plain) not harmful; `d-Alpha Tocopherol` not "Synthetic Vitamins"; `Green Tea Extract` not banned-matched; `Lemon Oil` not folate; `dl-alpha tocopherol` (explicit) still flagged.

**1.3 Negation inversion in statement parsing** — `enhanced_normalizer.py:2620-2738`
Skip `contains:` extraction for negated statements (`contains no|does not contain|free of/from` and the `Formulation re: Does NOT Contain` type); require allergen-context keyword match; never synthesize `"Contains: X"` warnings from non-positive text.
Test: the Country-Life-style statement produces zero allergens and zero synthesized warnings; a real `"Contains milk and soy."` still yields both.

**1.4 Allergen suppression trio** — `enrich_supplements_v3.py:4397-4443, 4491-4503, 4606`
(a) Delete the `_is_negated` call from the structured ingredient-row branch. (b) Apply statement negation per clause (split on `.`/`;`). (c) Marketing "X-Free"/targetGroup claims no longer suppress parsed/ingredient allergens — emit both + a conflict.
Test: milk-ingredient + "no artificial colors" text → milk flagged; "Made without gluten. Contains milk and soy." → milk+soy; milk + "Dairy Free" targetGroup → milk flagged with conflict.

**1.5 Jurisdiction gate for banned verdicts** — `enrich_supplements_v3.py:4154-4171`, `score_supplements.py:327-397`, `banned_recalled_ingredients.json`
Export `jurisdictions` + derived `banned_in_us` (US jurisdiction status, else `legal_status_enum ∈ {banned_federal, not_lawful_as_supplement, controlled_substance}`); B0 hard-fails only when US-applicable; non-US bans → `REGIONAL_RESTRICTION` advisory flag. Fix DB rollups (Garcinia, Kava). **Policy decision #1 below.**
Test: Garcinia Cambogia product → not UNSAFE, carries regional flag; DMAA/ephedra (US-banned) still UNSAFE/BLOCKED.

**1.6 Nutrition extraction last-write-wins** — `enhanced_normalizer.py:2994-3077`
Exact-name matching (`sodium`, `sugars`, `total sugars`, `calories`…), first-match-wins, never overwrite with a quantity-less row; add trans-fat/sat-fat/cholesterol capture (or delete the dead-comment machinery).
Test: Sodium 140 mg + inactive Sodium Benzoate → 140 mg; "Calories from Fat 15" doesn't clobber calories; Sodium Hyaluronate ≠ sodium.

**1.7 Unit reconciliation** — `rda_ul_calculator.py:280-292`, `unit_converter.py:131-145, 193-207, 221`, `enrich_supplements_v3.py:7003-7052, 7336, 7368-7391`
(a) `compute_nutrient_adequacy` converts `amount` to `nutrient_data['unit']` (mass-convert mg/mcg/g) before dividing; unreconcilable → `scoring_eligible=False`. (b) `convert_nutrient` falls through to `convert_mass` when no vitamin rule. (c) Load `unit_aliases` from `unit_conversions.json` and canonicalize. (d) Handle both µ (U+00B5) and μ (U+03BC) everywhere (also `normalization.py:61`, scorer `norm_text`). (e) Sugar/sodium: explicit unit map for `Milligram(s)/Gram(s)/mcg` spellings. (f) Strip comma thousands in the RDA collector.
Test: Copper 2 mg → 222% "high"; Calcium 1 g → 100%; Magnesium 0.4 g → over_ul true; Taurine 1000 mg ≈ 200%; sodium 55 "Milligram(s)" → 55 mg; "5 μg" B12 converts; "1,000 mg" not dropped.

**1.8 Orchestration data loss** — `batch_processor.py`, `clean_dsld_data.py`, `run_pipeline.py`
(a) After resume filtering, reset `state.last_completed_batch = -1` (indices renumber) — or drop batch-index resume; add end-of-run invariant `processed == total` else exit non-zero. (b) `_write_json_output` re-raises; mark files processed only after a successful write. (c) Each stage clears (or archives) its own output subdir at start; enrich/score verify an input manifest. (d) `clean run()` returns failure above an error threshold. (e) Route validator-crash (`status=error`) products to quarantine with data. (f) Atomic writes for score outputs + state file + `update_standardized_identifiers` (with `.bak`).
Test: simulated interrupt + resume processes exactly the remaining files; failed write fails the run; rerun with fewer batches leaves no stale files; 100% clean failure → non-zero exit.

**1.9 Manufacturer violation matching** — `enrich_supplements_v3.py:998-1009, 6111-6146`
Violations require exact/alias company match (mirror the trusted-bonus rule); if fuzzy is kept, ≥0.93 + token-set equality + min 2 tokens; never substring-1.0.
Test: "Guru Nanak Herbals" gets no "Guru Inc." deduction; exact violator still deducted.

**1.10 Blend detector** — `proprietary_blend_detector.py:193-197, 281, 334-336, 455` + `proprietary_blends_penalty.json`
Dedupe via `DetectedBlend.dedupe_key` (per `blend_id`), keep richest-disclosure copy; `float(x.replace(",",""))`; word-boundary term compile; statement-derived hits require blend context (amount or sub-ingredient list) before `disclosure="none"`; move "Whey Protein Blend" out of Stimulant Blends and prune generic terms ("Fruit Blend", "plant blend"…).
Test: blend in 2 fields → 1 detection; "1,000 mg" sub-ingredient doesn't kill detection; "Tropical Fruit Blend Flavor" → no blend; whey blend ≠ stimulant.

---

## Phase 2 — Systematic score accuracy (P1)

**2.1 GMP tiers** — `enrich:5291-5296, 5875-5882`, `score_supplements.py:906-915`: `claimed = gmp_found or nsf_gmp` (exclude `fda_registered`); projection tests `fda_registered` first; scorer stops treating `claimed` as certified. Test: "FDA registered facility" → b4b 2.0.

**2.2 Quality-map identity cluster** — data + `enrich:3470-3479`
Fix `curcumin` alias on the turmeric-powder form; resolve all 28 alias collisions + 17 alias-vs-standard-name clashes; add a build-time assertion (extend `test_ingredient_quality_map_schema.py`) that no preprocessed alias maps to >1 entry. Reorder `candidate_sort_key` to put `priority` above `match_source` (keep tier first only if that's the intended semantics — **policy decision #2**). Enforce global exclusions (bare `synthetic/standard/unspecified/...` → no match). Decide fuzzy pass: implement per spec as lowest tier with 0.85 + min-4-char guards, or update spec/DB `match_mode` (**policy decision #3**).
Test: "Curcumin" → curcumin at better-than-powder form; "Citrus Bioflavonoids"/"Quercetin" → quercetin; "Synthetic" → no match; alias-collision assertion green.

**2.3 Branded tokens** — `enhanced_normalizer.py:3341`, `enrich:1519, 1639`, IQM data: keep full `name` (token only in `branded_token_extracted`); on token match-failure retry with `raw_source_text`; add aliases for the 8 orphan tokens. Test: Albion Mg and Zn rows stay distinct and map to chelate forms.

**2.4 Scorer correctness** — `score_supplements.py`
(a) B0: scan all substances; BLOCKED precedence over UNSAFE. (b) Mapping gate stops on zero *scorable* actives (`NO_SCORABLE_ACTIVES`). (c) Multivitamin A1: `avg = max(avg, floor)` if a floor is intended (**policy decision #4**). (d) Fix regression-guard sizing (drive off the overlap set, not `min(unmapped_count_raw, …)`). (e) Fail-closed on empty severity for exact/alias hits. (f) Gate on `enrichment_status` (failed/validation_failed → NOT_SCORED). (g) Config: either thread `scoring_config.json` values through B/C/D/verdicts/grades or delete the dead keys and document hardcoding; remove or implement `shadow_mode` (**policy decision #5**). (h) Product-weighted batch averages.
Tests: order-swapped substances list → BLOCKED; blend-header-only product → NOT_SCORED; config poor_threshold change takes effect (or key removed).

**2.5 Serving/dose basis** — `enhanced_normalizer.py:4328-4375, 4650-4653`, `enrich:6798-6802, 6902-6988, 7385-7391, 7460`
Read `servingSizeQuantity/Unit/Order` from the quantity entry (not dv_group); align canonical-variant selection with enrichment's serving policy (or emit linkage); parse frequency ("N times daily") and divide intake units by `basis_count`; exclude precaution statements; capture full directions text (stop at end-of-notes, all direction statements); adequacy at min servings / UL at max (or emit both); restore per-group RDA data (or compute per-sex pairs) (**policy decision #6**); cap no-UL nutrients at "high"; folate UL on folic-acid basis (**policy decision #7**).
Test: child/adult variant product → basis and quantity from the same serving; "2 capsules twice daily" → 4/day; "Do not exceed 6" not a dose; Iron 18 mg reports both sexes (or documented profile); Vitamin K mega-dose ≠ "excessive"; 665 mcg methylfolate ≠ over-UL.

**2.6 Crash-to-loss paths** — `enrich:2687+2762 (None-coalesce + fix dead >1.0 branch), 6905-6917 (safe-float incl. fractions), 7326-7484 (per-ingredient try + stable fallback schema incl. safety keys)`; `normalizer:2999 (isinstance guard), 4961-4964 (fullmatch/anchor exclusion patterns)`; unify failure shapes on `EMPTY_ENRICHMENT_SCHEMA` (extended, with `_empty_rda_ul_payload`); `(as …)` capture `([^)]+)`.
Test: each crash fixture now enriches; one bad ingredient doesn't erase `safety_flags`; "(less than 2% caffeine)" active survives; "Calcium (as calcium citrate) (from limestone)" → citrate form.

**2.7 Cross-text false positives** — `enrich:3622-3625, 3800-3860, 3916-3949, 5942-5978`
Standardization % from the ingredient's own notes, or window-bound near the marker; synergy: one cluster-slot per physical ingredient + unit-convert before `min_effective_dose`; delivery terms word-boundary + require proximity to name/physicalState for generic terms; `_brand_mentioned` checks brand tokens only (add `brand_tokens` to brand studies).
Test: plain Ginkgo gets no 98%; Magnesium-only product ≤1 cluster and no A5c; "micellar casein" ≠ tier-1 delivery; generic astaxanthin ≠ AstaReal RCT.

**2.8 Probiotic counts** — `normalizer:3244-3266`, `enrich:6276-6291, 6441-6469, patterns :718-720`
Stop double-emitting nested rows (or dedupe strain counting by `normalized_key`); parse statement CFU once at product scope; add scientific-notation pattern; require CFU-context token near "billion" in free text.
Test: 3-strain fish-oil-style nesting counts 3; "Total 50 billion CFU" statement counts once; "5 x 10^9 CFU" = 5B; "2 billion people" ≠ CFU.

**2.9 Scorable classification** — `enrich:1863-2185, 2460-2482` + `constants.py:880`
Word-boundary excipient/botanical-part matching; potency regex trailing `\b` + both mus; `hierarchyType.get('type')`; remove/invert the `'blend'`-suffix carve-out; multi-form unmatched share scored conservatively (9 or parent unspecified); promoted no-dose enhancers excluded from the D2 missing-dose test; quantity-less single ingredients → `undisclosed_quantity`, not `proprietaryBlend`, and transparency vacuous-100 fixed; clean-claims `\bNo\s+` + statement-type gating.
Test: Watercress scorable; "omega-3 gold" no potency; "Energy Blend 500 mg" header not an active; 80%-unmatched dual form ≠ full premium; BioPerine promotion keeps D2; single NP strain not a "fully transparent proprietary blend"; "Contains Amino Acids…" ≠ "Soy Free".

**2.10 Banned-matching coverage (safety FNs)** — `enrich:1195-1211, 4073-4091, 4178-4187, 4602-4603`
Keep single-token non-dictionary short aliases (BHA/CBD/BVO…); fold `match_rules.label_tokens` into the alias set; normalize hyphen/space in `negative_match_terms` and also test against `standard_name`; token-bounded fallback for ingredient-list allergens ("Whey Protein Isolate", "Sodium Caseinate" → milk).
Test: "hemp extract (CBD)" flagged; "Ephedra Free Herbal Blend" not flagged; caseinate → milk.

---

## Phase 3 — Make the guardrails guard (P2)

**3.1 Coverage gate** — real field paths for the three correctness checks + a canary test built from a *real* enriched fixture (not fabricated dicts); missing `match_ledger`/failed `enrichment_status` = blocking; ImportError fails closed; unknown ledger domains use `get_domain_threshold`; revisit absolute-count downgrade (≤2-unmatched WARN) and <50-batch downgrade; expose `strict_mode` in `run_pipeline`.
**3.2 Wire the contract validator** into `run_pipeline` as stage 2.4 (fail on `severity=error`); fix Rules B/E.4 paths; implement or remove `strict_mode`.
**3.3 Stability gates** — emit `caution_triggers`/`immediate_fail` in `scoring_metadata` (or repoint to `flags`); fix `rate_applicable` ordering; `--expected-change` must parse content and match specific failures.
**3.4 Regression snapshot** — errors → alerts; store per-product `{id: score}` and compare; exclude timestamps from manifest hashes; compare verdict/unmatched files.
**3.5 Identity chain verifier** — stage dirs as CLI args; fail when expected products are missing; treat ledger count fields as lists.
**3.6 Exit codes & sampling** — preflight folds configs/scripts/schema into exit code and `--quick` checks JSON validity; format/claims/pipeline_audit exit non-zero on their own FAIL conditions and randomize sampling; delete `validate_json_files.py`.
**3.7 Misc contracts** — `serving_basis.form_factor` (or validator reads top-level); ledger `raw_source_path` from `source_section` (makes `UNMAPPED_INACTIVE_INGREDIENT` satisfiable); record claims domain + unmatched additives; fix `manufacturing_region` (`group(3)`); `_extract_country` via `contactDetails`; unified enrich failure schema (2.6 overlap); enrich CLI per-flag dir overrides; cleaning config `output_directory` double-`cleaned/` fix; worker future timeouts; dotfile filtering; fd cleanup.

---

## Phase 4 — Hygiene & dead code (P3)

Delete or wire: `fuzzy_matcher.py` + `_fuzzy_ingredient_match`, `_process_ingredient_parallel`, `compute_scoring_eligibility`, `legacy_coverage`, `is_certified_organic` projection, `quantityVariants`, `constants.UNIT_CONVERSIONS`, dormant JSONs, `_extract_ingredient_features`, discarded `_process_contacts` output, tmp configs (update `preflight` required list), stale `xfail` markers, archived-script test (`test_missing_match_tokens_report_empty`).
Data hygiene: dedupe 618 redundant aliases; backfill `strontium` match_rules + 22 `category_enum`; refresh IQM `_metadata.statistics`; supplemental-only `ul_basis` for magnesium (+ boron/vanadium notes); β-carotene supplement factor 0.15; reconcile CBD/7-keto/green-tea dual classification (**policy decision #8**); prune 2-char harmful aliases to token-bounded-only; "corn syrup" single ownership.
Cosmetics: verdict rounding boundary; unweighted averages; report timestamping; `proprietaryBlendDisclosure` multi-blend + "Not disclosed" strings; `LABEL_CONTRADICTION_DETECTED` emission; SCORING_LOGIC.md marked deprecated or rewritten to match code.

---

## Recommended execution order & effort

| Phase | Items | Est. effort | Score impact |
|---|---|---|---|
| 1 | 10 clusters | 3–5 days | Large — removes false UNSAFE/allergen/harmful flags, 1000× dose errors, data loss |
| 2 | 10 clusters | 4–6 days | Medium-large — systematic scoring corrections |
| 3 | 7 clusters | 2–3 days | None directly — restores regression detection before/while shipping 1–2 |
| 4 | cleanup | 1–2 days | None |

Suggested sequence: **capture baseline → 3.4 (per-product regression compare) first**, then Phase 1, re-baseline, Phase 2, then the rest of Phase 3, then Phase 4. Every fix lands with its regression test; run `pytest scripts/tests` + a full pipeline diff per cluster.

## Policy decisions needed (product owner input)

1. **Jurisdiction policy**: is the app US-market-only (gate UNSAFE on US applicability) or multi-region (carry per-region verdicts)?
2. **Matching precedence**: is "printed label over standardized name" (`match_source` above `priority`) intended, or should the spec's priority-first rule win?
3. **Fuzzy matching**: implement the documented 0.85 fuzzy pass, or officially retire it (update spec + `match_mode` data)?
4. **Multivitamin A1**: floor (never lowers) or blend (current, lowers premium multis)?
5. **`shadow_mode`**: implement real shadow semantics or delete the flag?
6. **RDA profile**: emit per-sex/per-group adequacy (restores `data_by_group`) or a single documented conservative profile?
7. **Folate**: DFE convention for methylfolate (×1.7 vs 1:1) and UL basis (folic-acid-only per IOM)?
8. **CBD et al.**: remove from the scorable quality map (not lawful as supplement) or keep dual-listed with B0 precedence?
