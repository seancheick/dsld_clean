# Prenatal Scoring — External-Audit Response & Fairness Plan

Context: a second reviewer (Codex) generated a synthetic prenatal that scored
~96/100 and asked whether the scorer is fair to the real market. This is my
assessment and what shipped in response.

## Is the synthetic 96 realistic? No — and that's fine.

Codex's own catalog query is the key evidence: among **1,449 scored
`multi_or_prenatal` products, avg ≈ 68.9, max ≈ 90.8, exactly 1 product ≥ 90,
0 ≥ 95.** So a 95+ is aspirational, not market-normal. The synthetic label hits
95+ because it is a *union of every anchor at ideal forms* — which, as Codex
notes, is physically a daily pack (2,000 mg myo-inositol + 450 mg choline +
300 mg DHA + full mineral panel doesn't fit 4 capsules). The scorer is right to
make 95+ rare; the synthetic is a benchmark fixture, not a shippable SKU.

**Verdict: the scorer is not too harsh.** It rewards the right things (folate,
iron, iodine, vitamin D, B12 as anchors; 5-MTHF / methyl-B12 / D3 / chelated
forms; DHA + choline as differentiators; third-party verification; clean
excipients), which lines up with NIH ODS pregnancy guidance.

## The real problem Codex found: too *soft* at the top, for one reason

A product can score "Exceptional" while **missing DHA or having token choline**,
because strong verification + broad coverage can compensate. Example: the
current top prenatal, Thorne Basic Prenatal (~90.8), has excellent forms and
certification but no DHA on its label. That is fair as a *quality* score, but
misleading if a user reads 90.8/"Exceptional" as "complete prenatal."

The fix is **not** to dock points for missing companion nutrients — that would
unfairly punish a legitimate "base multi + separate DHA/choline" product line
(Needed, MegaFood, etc. deliberately split these). The fix is to **separate
quality from completeness** and make completeness visible.

## What shipped in this repo (server-side, data-only)

**`prenatal_coverage` ledger** on every enriched product — a completeness map,
not a score:

- 8 pregnancy anchors (folate, iron, iodine, vitamin D, B12, choline, DHA,
  calcium) vs the pregnancy RDA/AI + UL from `rda_optimal_uls.json`.
- Per anchor: `present`, `amount_per_day`, `pct_of_target`, and a status in
  `{missing, below_target, meets_target, above_ul}`.
- `is_prenatal_positioned` role hint (name/targetGroups say prenatal/pregnancy).
- `"scoring_impact": "none"` — the v3 scorer does not read it
  (regression-pinned). Completeness is an **app-layer display / stack**
  decision, not a quality deduction.

This is deliberately the minimal, safe server-side change: it gives the Flutter
app the data to render "what's missing / underdosed" in the stack and to flag
gaps *by user goal or condition* (exactly what the user described), without
moving any score or making the server guess a product's marketed role.

## What belongs in the app layer (Flutter), not here

These are Codex's good ideas that are **display/personalization**, so they live
device-side where the user profile and stack are known — not in the
population-agnostic server scorer:

1. **Role-aware labeling.** "Strong base prenatal — pair with DHA/choline" vs
   "Complete prenatal." Drive it from `is_prenatal_positioned` +
   `prenatal_coverage.summary`.
2. **Stack-aware completeness.** If the user's stack already contains a DHA or
   choline product, mark the anchor satisfied at the *stack* level and suppress
   the "missing" flag. `user_stacks` already carries `ingredient_keys`.
3. **Category percentile.** "88/100 · top 1% of prenatal multis" reads fairer
   than "not elite," and matches the real distribution (max ≈ 90.8). Compute
   from the exported catalog, not in the intrinsic score.
4. **Goal/condition gating.** Myo-inositol / D-chiro-inositol are PCOS/metabolic
   *profile-fit*, not universal prenatal quality — surface them under the goal
   section, don't let them inflate a general prenatal score.

## Open server-side question (not changed yet — needs your call)

Codex suggests tightening near-UL handling for pregnancy-sensitive nutrients
(preformed vitamin A, iron, iodine, selenium, niacin) and making
content-verification certs (USP/NSF *content* verified) count more than a
generic/sport cert for *label-accuracy* trust. Both are real and defensible,
but they **move scores across the whole catalog**, so they should be a separate,
explicitly-versioned scorer change (bump `scoring_config` version, re-baseline
the 13k-product export, diff the distribution) rather than folded into this
data-only change. Flagged for a follow-up; not done here to keep this commit
score-neutral.

## Bottom line

Keep the scoring strict (95+ stays rare). The gap Codex found is a *clarity*
gap, not a strictness gap: users shouldn't infer completeness from one number.
The coverage ledger closes it without penalizing legitimate companion-product
strategies, and the heavier "role-aware score caps / cert re-weighting" ideas
are staged as an explicit future scorer version rather than slipped in.
