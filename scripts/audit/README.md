# IQM Identifier Audit — Review & Replay Guide

These CSVs are the **reviewable evidence** for the CUI/RxCUI corrections found
during the v4 defensibility audit (branch `claude/eloquent-ride-Bq8cO`, on
`seancheick/dsld_clean`). They are an **audit source, not a branch to merge** —
the branch base is very stale relative to current pipeline `main`.

Each row: `parent, standard_name, old_id, old_resolved, new_id (current), new_resolved, concept_type`.
Old/new names were resolved via the live UMLS UTS and RxNorm RxNav APIs.

## Files
- `iqm_cui_changes.csv` — 121 CUI corrections/populations.
- `iqm_rxcui_changes.csv` — RxCUI corrections, nulls, and review-bucket rows.

## `concept_type` buckets
- **exact/base (accept):** new id resolves to the exact ingredient concept
  (e.g. `zinc → 11416 zinc`, `taurine → 10337 taurine`, `gaba → 4617`,
  `5_htp → 94 5-hydroxytryptophan`). Safe to replay.
- **extract/preparation (review):** new id is an extract/preparation concept
  (e.g. `ginkgo biloba extract`, `milk thistle seed extract`,
  `saw palmetto extract`). Acceptable **only** if the parent is explicitly an
  extract parent; otherwise hold for form-level assignment.
- **null (salt-only or unverifiable):** parent left null because RxNorm
  resolves only to a salt-specific PIN on a broad parent (choline, glucosamine,
  l_carnitine, l_lysine, vitamin_b6) or no verifiable concept exists (selenium,
  ashwagandha, cryptoxanthin, pqq, sulforaphane). Each carries a note.

## Recommended replay onto current `main` (do NOT merge the branch)
1. **Commit 1 — CUI:** apply the `exact/base` CUI rows; review the
   `extract/preparation` CUI rows against whether the parent is botanical/extract.
2. **Commit 2 — RxCUI exact + intentional nulls:** apply `exact/base` RxCUI rows
   and the `null` rows.
3. **Commit 3 (separate review) — RxCUI extract/preparation:** only where the
   parent is explicitly an extract parent.

Guards already on the branch (replicate on main): `test_iqm_identifier_integrity.py`
enforces no-junk, format, no-duplicate-CUI, no-duplicate-RxCUI, and verified-id pins.
