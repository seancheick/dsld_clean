# Ingredient Quality Map — v4 Defensibility Audit

Branch: `claude/eloquent-ride-Bq8cO`
Date: 2026-06-06
Source of truth: `scripts/data/ingredient_quality_map.json`

Batch-by-batch audit to make IQM medically/clinically defensible for v4 scoring.
Each batch is an atomic commit with tests. Identifiers verified against official
APIs (UMLS UTS, RxNorm/RxNav, FDA GSRS). No identifiers were invented.

Invariants enforced by new tests:
- `score == min(bio_score + 3 if natural else bio_score, 18)`; `bio_score` int 0–15; `score` int.
- No junk/placeholder CUI/RxCUI; CUI = `C\d{7}`, RxCUI numeric, UNII 10×[A-Z0-9].
- No duplicate CUI or RxCUI across parents; verified-identifier pins.
- Probiotic unspecified/catch-all floor; fatty-acid unspecified ≤ lowest legit specific.

Test files added: `test_iqm_score_invariants.py`, `test_iqm_unspecified_form_floor.py`,
`test_iqm_minerals_calibration.py`, `test_iqm_identifier_integrity.py`,
`test_iqm_vitamins_aliases.py`, `test_iqm_amino_acids.py`, `test_iqm_fatty_acids.py`.
**53 passed, 1 skipped.**

---

## Batches applied

| # | Area | Change | Direction |
|---|------|--------|-----------|
| 1 | Structural | 26 forms: `score=bio+2` → `bio+3` (natural bonus); strontium float→int | +1 each (formula correctness) |
| 2 | Probiotics | `probiotic_unspecified.standard` 10/true/13 → 5/false/5 (bare "Probiotic") | down (de-inflate) |
| 3 | Minerals | inorganic salts natural→false (Ca/Mg carbonate, MgCl, MgSO4, coral, phosphate salts); iodine unspecified natural→false; silicon/fluoride generic 13→6 | down |
| 4 | Identifiers | normalize 11 junk `cui=""` + 23 junk `rxcui=""/"none"` → null + honest notes | hygiene |
| 5 | Vitamins | remove `'Lemon Extract'` (folate) + `'colored with vitamin b2'` (riboflavin) | alias cleanup |
| 6 | Identifiers | populate 10 verified RxCUIs + 6 verified UNIIs (RxNorm/GSRS exact-name) | enrich |
| 7 | Amino acids | remove `'amino acids'`/`'essential amino acids'` from BCAA 2:1:1; BCAA standard + taurine generic natural→false | mixed |
| 8 | Identifiers | **121 CUIs corrected/populated via UMLS** (systemic corruption) | correctness |
| 9 | Identifiers | **82 RxCUIs corrected + 5 nulled via RxNorm** (systemic corruption) | correctness |
| 10 | Fatty acids | dha/epa/fish_oil/ceramides/hemp_seed_oil unspecified 10→8 (above-specific inversion) | down |
| 11 | Review feedback | null 5 salt-only RxCUIs on broad parents; unspecified oils → 8/false/8; fix selenium CSV dup | mixed |
| 12 | Unspecified (file-wide) | drop natural bonus on all 46 remaining `(unspecified)` forms (undisclosed form ≠ natural) | down |
| 13 | Consistency | magnesium glycinate (under l_glycine) + liposomal curcumin natural→false (match canonical parent) | down |

### Clean scans (no action — confirmed not bugs)
- `absorption_structured`: apparent quality↔value/bio "mismatches" are the intended
  design — `bio_score` is *relative within the nutrient*, `quality`/`value` are
  *absolute* (e.g. chromium picolinate bio 14 = best chromium form, quality poor /
  0.028 = chromium is poorly absorbed in absolute terms).
- bio_score=15 ceiling (42 forms): all branded/clinically-defined premium forms
  (Bacognize, Longvida, Niagen, LGG, BB536, CNCM I-745, krill phospholipid, P5P,
  zinc carnosine…) — justified per "exact branded forms can score high".
- `coenzymated_complex` (bio 14/17): notes carry a real absorption rationale
  (pre-converted active forms); coenzyme forms are the food-occurring forms, so
  natural=true is defensible. Left unchanged (flagged, not a clear bug).

### Status: mechanical / structural-consistency / identifier audit COMPLETE
All clear, evidence-grounded bug classes are fixed across ALL categories
(score-formula, identifier junk/format/dup/**systemic corruption**, unspecified
calibration + natural-bonus, alias hijacks/foreign aliases, fatty-acid inversions,
cross-parent natural consistency, absorption-structured consistency, premium ceiling).
**56 tests passing.**

### Headline finding — systemic identifier corruption (batches 8 & 9)
A full UMLS/RxNorm audit of every stored identifier found the `cui` and `rxcui`
fields were largely **corrupt**, mapping to alphabetically/coincidentally
adjacent but unrelated concepts (signature of a broken bulk-population join):
`iron`→"Intermittent Explosive Disorder", `zinc`→"Zygomatic bone",
`vanadium`→"valine", `copper`→"cyclophosphamide", `vitamin_b12`→"clozapine",
`vitamin_a` rxcui→"vasopressin", etc. Also a duplicate CUI (`dandelion` and
`perilla_oil` both held C0950252 = d-limonene). Re-derivation was synonym-safe
(kept only if the stored id appeared in the API search for the name) and
replacements were accepted only on exact canonical substance-name matches;
peptide/enzyme/product/LOINC false-matches were rejected and hand-resolved.
Correct originals (niacin, pyridoxine, biotin, folate) were preserved.

---

## Deferred — needs decision / larger effort (NOT changed)

**Structural (merge/split — blast radius via matcher + id_redirects + consumers):**
- `probiotics` mega-parent duplicates the dedicated `lactobacillus_*` /
  `bifidobacterium_*` / `saccharomyces_boulardii` parents, with inconsistent
  scores for the same strain (LGG 14 vs 15; HN001 13 vs 14; HN019 14 vs 15).
- `acetyl_l_carnitine` duplicates `l_carnitine`'s ALCAR form (15 vs 14).
- `vanadyl_sulfate` duplicates `vanadium`'s forms; `dicalcium_phosphate` /
  `phosphorus` / calcium's phosphate forms overlap.
- `vitamin_k1` overlaps `vitamin_k` (phylloquinone duplicated).
- `vitamin_b9_folate` has overlapping 5-MTHF forms (14 vs 13) + duplicate
  calcium-folinate forms.

**Calibration flags (judgment — review desired):**
- `coenzymated_complex.coenzymated`: vague class/marketing descriptor scored
  bio 14 / score 17 (natural=true). Likely over-scored for a non-specific label.
- Generic fatty-acid `standard` templates (`epa_dha`, `omega_6/7/9`,
  `other_fatty_acids`, `docosapentaenoic_acid_dpa`) at bio 10 / natural true / 13.
- Inorganic-salt natural flips (batch 3) are conservative + criteria-based but
  are the most "review-worthy" calibration choices.

**Missing premium forms (additive — needs per-brand bioavailability evidence):**
- Single-form parents where branded premium forms currently fall into a single
  `(unspecified)` row at bio 5: `quercetin` (Quercefit/phytosome),
  `lutein` (FloraGLO, Lutemax 2020 / marigold), `l_theanine` (Suntheanine),
  `resveratrol` (trans-resveratrol vs polygonum). These UNDER-score premium
  products (conservative), so low urgency, but adding evidence-backed premium
  forms would improve fidelity.

**Identifiers still open:**
- CUIs left null where no verified concept exists (e.g. `ahiflower_seed_oil`);
  `pqq` RxCUI deferred (no clean RxNorm concept).
- `external_ids`/UNII is unpopulated for most parents — a file-wide UNII/GSRS
  enrichment pass (with openFDA key) is a clean future batch.

**Marginal (left as-is, defensible poor-form exceptions):**
- `manuka_honey` unspecified 10 vs "ungraded manuka" 9; `slippery_elm` unspec 8
  vs "outer bark" 4; `curcumin` unspec 5 vs "turmeric powder" 4.

---

## Not yet reviewed (scoring audit remaining)
antioxidants (199), herbs (61), adaptogens, fibers/prebiotics/postbiotics,
enzymes, functional foods, and remaining single-form amino acids. The
file-wide structural scans (score formula, unspecified inversions, junk/dup
identifiers, over-broad aliases) have already been run across ALL categories,
so the clear mechanical bugs in those categories are captured above; what
remains is per-ingredient bio_score calibration review.

---

## Convergence (batch 14 + final scans)
- Batch 14: apigenin extract 13→6, berberine hcl 11→6 (bio_score contradicted
  own poor-bioavailability notes/quality; PubMed-checked).
- Final contradiction scans all clean: synthetic-named-but-natural=true (0),
  high-measured-absorption-but-low-bio (0), high-bio-with-poor-absorption-notes (0).

**The clear, evidence-grounded fix audit is complete (14 batches, 58 tests).**
Every remaining item is either (a) subjective per-ingredient calibration — which
the task scope explicitly excludes ("no broad vibes-based edits; only fix clear
issues with evidence") — or (b) the deferred structural merges, which are safer
executed against the live pipeline `main` than this stale branch. No further
mechanical/data-truth bugs were detectable.

## Evidence-based calibration pass (batches 14–16)
PubMed-verified (NCBI E-utilities) corrections where bio_score reflected clinical
benefit rather than absorption, or created within-parent inversions:
- apigenin extract 13→6, berberine hcl 11→6 (batch 14) — textbook-poor oral
  bioavailability (PMID 41265600, 42120042).
- quercetin: added evidence-backed premium form `quercetin phytosome (quercefit)`
  bio=14 (~20x absorption, PMID 30328058); plain quercetin stays bio=5 (batch 15).
- green tea catechins 13→10 (batch 16) — EGCG poorly bioavailable; was out-scoring
  the parent's own standardized 50% EGCG extract (PMID 41106481).

Premium-tier verification (bio≥13) across antioxidants, herbs/adaptogens, and a
file-wide "non-enhanced out-scores delivery-enhanced sibling" scan: **no further
clear over-scores.** Branded multiplier forms (Longvida 65x, NovaSOL 185x,
CurcuWIN 46x, ubiquinol crystal-free 8x), exact probiotic strains, and
already-well-absorbed actives (taurine, NAC, alpha-GPC, R-ALA, KSM-66) all hold up.

## The one remaining large decision (your call — NOT swept)
The file's original `bio_score` blends *absorption* with *standardization/quality/
potency* (per its own metadata scoring_factors), whereas the audit brief defines
`bio_score` as **absorption/bioavailability only**. Strictly enforcing
absorption-only would demote many standardized/potency-graded extracts (e.g.
patented herb extracts scored high for standardization, cordyceps militaris,
gelatinized maca) — hundreds of scores, a scoring-philosophy change. This is a
deliberate product decision, not a mechanical bug, so it is left for you/Codex to
direct rather than swept unilaterally.

## Hybrid calibration converged (batch 17 + final scan)
- Batch 17: demoted poorly-absorbed flavonoid forms (flavones/flavonols 11→6,
  eriocitrin 11→7, bioflavonoids hesperidin/citrus/rutin 12/11→8/7, unspecified
  9→6). PubMed-supported; enhanced forms (Theracurmin, trans-pterostilbene) kept.
- Final poorly-absorbed-compound scan (curcumin, turmeric, resveratrol, silymarin/
  milk thistle, boswellia, oleuropein, ellagic acid, olive leaf): no further
  over-scores — plain forms already low, enhanced/branded forms appropriately high.

Per the agreed decisions: bio_score = HYBRID (applied — clear poorly-absorbed
non-enhanced forms demoted with evidence; quality-blended scores otherwise kept);
structural merges = assigned to Codex on live `main`. The audit is complete to the
extent achievable as clear, evidence-grounded, non-vibes fixes: **17 batches.**
