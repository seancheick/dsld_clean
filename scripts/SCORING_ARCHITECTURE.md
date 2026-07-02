# SCORING_ARCHITECTURE.md — the one-brain model

PharmaGuide was conflating three different questions into one product number.
They are separate concerns and live in separate layers. This is the target
architecture (largely already built; this document names it and pins the
server↔app contract).

```
Product Quality   = how well-made is this product for its role   (SERVER, /100, market-fair)
Personal Fit      = is it supportive / risky for THIS person      (DEVICE, per profile)
Stack Coverage    = does my whole routine cover needs w/o excess  (DEVICE, per stack)
```

A prenatal without DHA or full choline is **not** automatically a bad prenatal.
It may be a high-quality *base* meant to pair with a DHA/choline companion. That
fact belongs in **Stack Coverage**, not as a product-quality penalty.

## Layer 1 — Product Quality (this repo, server-side)

- The v3-series scorer (`score_supplements.py`). Canonical output is **/100**
  (`score`, `display` = "NN/100"); the 0-80 `score_80`/`quality_score` are an
  internal representation kept for stability gates and snapshots. See
  `SCORING_VERSIONS.md`.
- Population-agnostic: bioavailable forms, safety/purity, evidence, brand trust.
- Deliberately strict: 95+ is rare and should stay rare (real prenatal-multi
  max is ~90.8 across 1,449 products). Do **not** lower this globally.

## Layer 2 — Personal Fit (Flutter app, device-side)

- Consumes the enrichment's **Section E** blocks this repo produces but never
  scores: `rda_ul_data`, `dietary_sensitivity_data`.
- Uses the user's profile (life stage, conditions) to flag support/risk.
- Existing Flutter foundation: `StackUlChecker` (RDA/UL totals incl.
  Pregnancy/Lactation rows), `NutrientAccumulationPanel` (totals + UL warnings).

## Layer 3 — Stack Coverage (Flutter app, device-side)

- Consumes this repo's `prenatal_coverage` ledger + `product_role` (below).
- Existing Flutter foundation: `CoverageAnalyzer`
  (Supported / Partially supported / Underdosed / Unaddressed) and
  `goal_matches_underdosed` in `products_core`.
- **The missing piece Codex identified:** the Nutrients tab only shows nutrients
  that are *present*. Absent priority nutrients are invisible. The server now
  supplies the "what's absent" data (`prenatal_coverage.summary.missing`) so the
  app can render **Priority Gaps** for a pregnancy/TTC goal or pregnancy
  condition — as neutral coverage, not scary orange warnings.

## Server → App contract (what this repo now emits)

Every enriched product carries two device-side, **non-scored** blocks
(`"scoring_impact": "none"`; regression-pinned that the scorer ignores them):

### `enriched["prenatal_coverage"]`
Pregnancy-anchor completeness vs pregnancy RDA/AI + UL:
```
anchors.<folate|iron|iodine|vitamin_d|vitamin_b12|choline|dha|calcium> = {
  present, amount_per_day, unit, pregnancy_target, pregnancy_ul,
  pct_of_target, status ∈ {missing, below_target, meets_target, above_ul}
}
summary.{missing, below_target, meets_target, above_ul}   # anchor name lists
is_prenatal_positioned                                     # affirmative only (see below)
```

### `enriched["product_role"]`
```
role ∈ {
  prenatal_complete, prenatal_base,
  prenatal_dha_companion, prenatal_choline_companion,
  general_multi, targeted_gap_filler, single_ingredient,
  probiotic, prebiotic, herbal_blend, unclassified
}
is_prenatal_positioned, is_prenatal_by_composition,
core_anchors_present[], completeness_present[], completeness_missing[],
claims_complete, completeness_claim_mismatch
```

- `prenatal_base` = carries the prenatal core (folate/iodine/D/B12) but is
  missing a completeness nutrient (iron/DHA/choline). **Not penalized.**
- `prenatal_complete` = core + all completeness nutrients present.
- `completeness_claim_mismatch` = the product *markets* itself "complete /
  all-in-one" but is only a base. This is a claim/completeness signal for the
  app, still not a server score penalty.
- `is_prenatal_positioned` is affirmative-only: a pregnancy **caution**
  ("Women (not pregnant or lactating)", "not for use if pregnant") does **not**
  count as positioning.

## Suggested app behavior (Layer 2/3, not in this repo)

- Product detail (base): "High-quality prenatal base. Does not include DHA —
  check your stack coverage."
- Stack coverage: "DHA is not covered in your current stack. Many prenatal
  routines add DHA separately." · "Choline: partly covered — 110 mg of 450 mg
  pregnancy AI."
- If the user's stack already contains a DHA/choline product
  (`user_stacks.ingredient_keys`), mark the anchor satisfied at the STACK level
  and suppress the gap.
- Fairness context on the score: "88/100 · Top 2% of prenatal multis" (compute
  percentile from the exported catalog, not in the intrinsic score).

## Deferred — role-aware SCORING (needs explicit approval; score-moving)

Codex's stronger proposal — let the scorer itself cap/qualify by role (missing
DHA does not crush `prenatal_base`, but caps a product that *claims*
`prenatal_complete`) and re-weight content-verification certs (USP/NSF content
verified > generic/sport for label-accuracy trust), plus tighten near-UL
handling for pregnancy-sensitive nutrients (preformed vitamin A, iron, iodine,
selenium, niacin) — **moves scores across all ~13k products**. It must be a
separate, explicitly versioned scorer change: bump `config/scoring_config.json`
version, re-baseline the export, diff the distribution, and update the golden
fixtures in the same commit. Not done here to keep the current change
score-neutral. `product_role` above is the data enabler for it.
