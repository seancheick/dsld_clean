# Ingredient Matching Precedence Specification

**Version**: 1.0.0
**Date**: 2026-01-08
**Applies to**: `ingredient_quality_map.json` v3.0.0+

---

## Overview

This document specifies how the enrichment pipeline resolves ingredient matches when multiple potential matches exist. It ensures deterministic, explainable matching behavior across all teams.

---

## Match Priority Levels

Every ingredient in `ingredient_quality_map.json` has a `match_rules.priority` field:

| Priority | Category | Examples | Match Behavior |
|----------|----------|----------|----------------|
| **0** | Specific compounds | `nicotinamide_riboside`, `silymarin`, `honokiol`, `5_htp` | Always wins over parent/category |
| **1** | Parent botanicals | `turmeric`, `milk_thistle`, `magnolia_bark`, `garlic` | Wins over categories, loses to compounds |
| **2** | Generic categories | `probiotics`, `prebiotics`, `omega_3`, `citrus_bioflavonoids` | Only matches if no specific match found |

### Resolution Rule

```
When label text matches multiple ingredients:
  1. Select the match with lowest priority number
  2. If tie, select the match with longest alias match
  3. If still tied, select alphabetically by ingredient key
```

### Match-Source Dimension (implementation note)

The enricher matches against two input texts per ingredient row: the raw
label `name` and the cleaner-derived `standardName`. The implemented sort key
in `_match_quality_map` is:

```
(tier, match_source, priority, -alias_len, form_rank, parent_key, form_key)
```

`match_source` (raw name = 0, standardName = 1, base = 2) ranks ABOVE
`priority` deliberately: what the label literally declares outranks a
derived hint at the same match tier ("raw_name_priority" in ambiguity
reasons). The Resolution Rule above applies among candidates from the SAME
source text. This is a provenance rule, not an exception to the
compound-over-botanical hierarchy: for a single matched text, priority
still decides (audited 2026-07; regression corpus pins this behavior).

---

## Parent-Child Resolution

### Relationship Types

| Type | Direction | Example |
|------|-----------|---------|
| `active_in` | Compound → Botanical | curcumin `active_in` turmeric |
| `contains` | Botanical → Compound | turmeric `contains` curcumin |
| `form_of` | Specific → Generic | vitamin_k1 `form_of` vitamin_k |
| `metabolite_of` | Product → Precursor | 5_htp `metabolite_of` l_tryptophan |
| `source_of` | Source → Nutrient | flaxseed `source_of` omega_3 |
| `category_for` | Category → Member | probiotics `category_for` lactobacillus_acidophilus |

### Resolution Examples

| Label Text | Potential Matches | Winner | Reason |
|------------|-------------------|--------|--------|
| "Curcumin C3 Complex" | curcumin (P0), turmeric (P1) | `curcumin` | Lower priority wins |
| "Turmeric Root Powder" | turmeric (P1) | `turmeric` | Only match |
| "Curcuma longa Extract" | curcumin (P0), turmeric (P1) | `curcumin` | Extract = concentrated compound |
| "Lactobacillus acidophilus" | lactobacillus_acidophilus (P0), probiotics (P2) | `lactobacillus_acidophilus` | Specific strain wins |
| "Probiotic Blend" | probiotics (P2) | `probiotics` | Generic matches category |
| "Silymarin 80%" | silymarin (P0), milk_thistle (P1) | `silymarin` | Compound wins |
| "Milk Thistle Seed" | milk_thistle (P1) | `milk_thistle` | Botanical source |

### Double-Match Prevention

When a compound matches, its parent botanical must NOT also match:

```python
# Pseudocode
if matched_ingredient has relationship["active_in"]:
    parent_id = relationship["target_id"]
    remove parent_id from match candidates
```

---

## Exclusion Rules

### How Exclusions Apply

Each ingredient has `match_rules.exclusions[]` - terms that prevent a match even if alias matches:

```json
{
  "match_rules": {
    "priority": 0,
    "match_mode": "alias_and_fuzzy",
    "exclusions": ["synthetic", "natural", "standard", "unspecified"]
  }
}
```

### Global Exclusions (Applied to All)

These terms are too generic to be meaningful identifiers:

| Term | Reason |
|------|--------|
| `synthetic` | Form descriptor, not identifier |
| `natural` | Form descriptor, not identifier |
| `standard` | Quality descriptor |
| `unspecified` | Placeholder |
| `complex` | Too generic |
| `extract` | Form descriptor (unless part of botanical name) |
| `powder` | Form descriptor |
| `capsule` | Delivery form |

### Exclusion Processing

```
1. Normalize label text (lowercase, strip whitespace)
2. Check if label contains ONLY exclusion terms
3. If yes, skip this match candidate
4. If no, proceed with alias matching
```

**Example**:
- "Natural flavoring" → Does NOT match `vitamin_a` (even if "natural" is in aliases)
- "Curcumin Natural" → DOES match `curcumin` (has meaningful identifier)

---

## Fuzzy Matching Rules

### When Fuzzy Matching is Allowed

| match_mode | Behavior |
|------------|----------|
| `exact` | Alias must match exactly (case-insensitive) |
| `alias_only` | Alias match only, no fuzzy |
| `alias_and_fuzzy` | Try alias first, then fuzzy if no match |

### Fuzzy Matching Constraints

1. **Minimum similarity**: 0.85 (85% string similarity)
2. **Minimum token length**: 4 characters
3. **Prohibited patterns**: Numbers only, single characters

### Fuzzy Match Examples

| Label | Alias | Similarity | Match? |
|-------|-------|------------|--------|
| "Curcumine" | "curcumin" | 0.94 | Yes |
| "L-Carnatine" | "l-carnitine" | 0.91 | Yes |
| "Vitamin" | "vitamin_a" | 0.78 | No (below threshold) |
| "B12" | "vitamin_b12" | 0.60 | No (below threshold) |

---

## Match Order of Operations

```
1. NORMALIZE input label
   - Lowercase
   - Strip whitespace
   - Remove parenthetical dosages: "500mg", "(100 IU)"

2. CHECK exclusions
   - If label is ONLY exclusion terms, return no match

3. EXACT ALIAS match (pass 1)
   - Check all ingredients for exact alias match
   - If multiple matches, apply priority resolution

4. FUZZY match (pass 2, if enabled)
   - If no exact match and match_mode allows fuzzy
   - Apply similarity threshold
   - Apply priority resolution if multiple fuzzy matches

5. PARENT-CHILD resolution
   - If compound matched, remove parent from candidates
   - Return highest-priority match only

6. RETURN match or null
```

---

## Integration Notes for Dev Team

### Using match_rules in Enricher

```python
def resolve_match(label: str, candidates: list) -> dict:
    """
    candidates = list of (ingredient_key, match_data) tuples
    """
    # Sort by priority (lowest first), then by match length
    sorted_candidates = sorted(
        candidates,
        key=lambda x: (
            x[1]['match_rules']['priority'],
            -len(x[1].get('matched_alias', '')),
            x[0]  # alphabetical tiebreaker
        )
    )
    return sorted_candidates[0] if sorted_candidates else None
```

### Using Relationships for Explainability

```python
def get_relationship_context(ingredient_key: str) -> str:
    """Return human-readable relationship context."""
    relationships = iqm[ingredient_key].get('relationships', [])
    for rel in relationships:
        if rel['type'] == 'active_in':
            parent = iqm[rel['target_id']]['standard_name']
            return f"Active compound in {parent}"
        elif rel['type'] == 'form_of':
            parent = iqm[rel['target_id']]['standard_name']
            return f"Form of {parent}"
    return None
```

---

## Ownership Hierarchy (Canonical Reference)

When an alias could belong to multiple ingredients, ownership follows this hierarchy:

```
1. Active compound > Parent botanical
   silymarin > milk_thistle
   curcumin > turmeric
   honokiol > magnolia_bark

2. Specific form > Generic form
   acetyl_l_carnitine > l_carnitine
   nicotinamide_riboside > vitamin_b3_niacin
   vitamin_k1 > vitamin_k

3. Specific strain > Category
   lactobacillus_acidophilus > probiotics
   bifidobacterium_lactis > probiotics

4. Source ingredient > Nutrient category
   flaxseed > omega_3
   fish_oil > omega_3

5. Standalone compound > Metabolic precursor
   5_htp > l_tryptophan
   nmn > vitamin_b3_niacin
```

---

## Testing Requirements

All matching changes must pass:

1. `test_ingredient_quality_map_schema.py` - Schema enforcement
2. `test_ingredient_matching_regression.py` - Real label corpus (Suite 1)
3. `test_ingredient_matching_regression.py` - Collision tests (Suite 2)

### Adding New Test Cases

When adding new ingredients or aliases:

```python
# In test_ingredient_matching_regression.py, add to LABEL_CORPUS:
LABEL_CORPUS = [
    # (label_text, expected_ingredient_key, should_match)
    ("New Compound 500mg", "new_compound", True),
]

# For collision prevention, add to PRIORITY_TESTS:
PRIORITY_TESTS = [
    # (label_text, should_match, should_not_match)
    ("New Compound", "new_compound", "parent_ingredient"),
]
```

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-08 | Initial specification |

---

## Contact

Questions about matching behavior should be directed to the data team responsible for `ingredient_quality_map.json` maintenance.
