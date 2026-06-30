"""
Alias-hygiene regressions for vitamin parents in ingredient_quality_map.json.

Cross-ingredient / non-ingredient aliases let a product's unrelated label text
hijack a vitamin form's score. These pins lock out specific bugs found during
the vitamins audit:
- 'Lemon Extract' was listed as an alias of vitamin B9 (folate) (unspecified) —
  lemon extract is not folate.
- 'colored with vitamin b2' was an alias on the riboflavin form — a colorant
  declaration phrase, not a supplemental-form synonym.

Run with: pytest scripts/tests/test_iqm_vitamins_aliases.py -q
"""

import json
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'


@pytest.fixture(scope='module')
def entries():
    with open(IQM_PATH, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k != '_metadata'}


def _all_aliases_lower(entry):
    out = []
    for f in entry.get('forms', {}).values():
        if isinstance(f, dict):
            out.extend(a.lower().strip() for a in f.get('aliases', []))
    return out


class TestVitaminForeignAliasesRemoved:
    def test_no_lemon_extract_in_folate(self, entries):
        assert 'lemon extract' not in _all_aliases_lower(entries['vitamin_b9_folate'])

    def test_no_colorant_phrase_in_riboflavin(self, entries):
        assert 'colored with vitamin b2' not in _all_aliases_lower(entries['vitamin_b2_riboflavin'])
