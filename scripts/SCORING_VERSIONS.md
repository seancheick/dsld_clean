# SCORING_VERSIONS.md — read this before trusting a version number

There is **one** server-side quality scorer in this repo, and it is **v3-series**.
"v4" almost always refers to the **data-schema** version or the **separate
on-device profile scorer**, not this scorer. This document exists because those
axes are easy to conflate.

## The three independent version axes

| Axis | Where it lives | Current value | What it means |
|---|---|---|---|
| **Quality scorer** | `score_supplements.py` (`self.VERSION`, from `config/scoring_config.json._documentation.version`) | **3.0.1** (code) / **3.4.0** (shipped, per Supabase `export_manifest.scoring_version`) | The 0–80 quality algorithm (Sections A–D). This is "the scoring system." |
| **Reference-data schema** | `_metadata.schema_version` inside `data/*.json` (29 files) | **4.0.0** | The shape of the *reference databases*, NOT the scorer. A file saying `"schema_version": "4.0.0"` does **not** mean "scoring v4." |
| **Output schema** | `scoring_metadata.output_schema_version` | see config | The shape of the scorer's JSON output. |

If you see `4.0.0`, check which axis it is. The scorer has never been v4.

## There is no "v4 scorer" in this repo

- The only scorer module is `score_supplements.py`. `score_stability_gates.py`
  is a stability gate, not a scorer. `scripts/archive/` contains no scorer.
- `git grep` for a v4 scorer finds nothing. The manifest that the app actually
  ships (`export_manifest`) reports `scoring_version = 3.4.0`.

## Two scorers exist, but only one is here (this is the real confusion)

The pipeline is deliberately split:

1. **Server-side quality score (this repo, v3-series).** Product-intrinsic
   quality: bioavailable forms, safety/purity, evidence, brand trust. Produces
   `score_80` / `score_100_equivalent` / `verdict`. Population-agnostic.

2. **Device-side profile score (the Flutter app — NOT in this repo).** Personal
   fit for a given user (life stage, conditions, existing stack). It consumes
   the enrichment's **Section E** blocks that this repo produces but never
   scores itself: `rda_ul_data`, `dietary_sensitivity_data`, and the new
   `prenatal_coverage` ledger. Enrichment comments that say "for device-side
   scoring / user profile scoring on device" refer to this app-layer scorer.

A reviewer inspecting "the current multi/prenatal scorer" and seeing a
100-scale that depends on clinical matches, certifications, RDA/UL rows and
parsed claims is describing **either** the `score_100_equivalent` view of the
v3 scorer **or** the device-side profile scorer — not a third system.

## `score_80` and `score_100_equivalent` are the same scorer

```
score_100_equivalent = (score_80 / 80) * 100
```

So `77/80` and `96.2/100` are one number in two representations, produced by one
scorer in one pass. Grade words are keyed off the 100 view (`_grade_word`):
Exceptional ≥90, Excellent ≥80, Good ≥70, Fair ≥60, Below Avg ≥50, Low ≥32.
(See the external-audit note below: ≥90 is intentionally rare in the real
catalog — max observed among 1,449 prenatal multis is ~90.8.)

## The `prenatal_coverage` ledger is data, not score

`enriched["prenatal_coverage"]` reports pregnancy-anchor completeness (folate,
iron, iodine, vitamin D, B12, choline, DHA, calcium) for the app's stack /
"what's missing or underdosed" view. It carries `"scoring_impact": "none"` and
the v3 scorer does not read it (regression-pinned in
`tests/test_prenatal_coverage_ledger.py::TestScoringIsolation`). A base prenatal
that ships DHA/choline as a companion product is reported as `missing` those
anchors **without any score penalty** — role-fairness is an app-layer display
decision, not a quality deduction.

## If you want to change scoring behavior

Edit `score_supplements.py` + `config/scoring_config.json` and bump the scorer
version there. Do **not** infer scorer behavior from a data file's
`schema_version`. Spec: `SCORING_ENGINE_SPEC.md` (code-accurate for the current
v3 scorer).
