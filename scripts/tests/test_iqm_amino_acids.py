"""
Amino-acid alias and natural-flag regressions for ingredient_quality_map.json.

- 'amino acids' / 'essential amino acids' must not be aliases of a specific
  branded BCAA ratio: those generic class terms (and EAAs, which are not BCAAs)
  would hijack any generic amino-acid label into a premium BCAA score.
- A generic/synthetic amino-acid form must not carry the natural +3 bonus when
  its own specific forms are natural=false and/or its notes state it is
  synthetic (BCAA 'standard'; taurine '(generic)'). The natural bonus belongs on
  genuinely food-derived rows (e.g. 'taurine from food').

Run with: pytest scripts/tests/test_iqm_amino_acids.py -q
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


class TestBcaaAliases:
    def test_no_generic_amino_acid_aliases_on_bcaa(self, entries):
        aliases = {a.lower().strip()
                   for a in entries['branched_chain_amino_acids']['forms']['bcaa 2:1:1']['aliases']}
        assert 'amino acids' not in aliases
        assert 'essential amino acids' not in aliases


class TestAminoAcidNaturalFlags:
    PINS = {
        ('branched_chain_amino_acids', 'standard'): (10, False, 10),
        ('taurine', 'taurine (generic)'): (14, False, 14),
    }

    def test_generic_forms_not_natural(self, entries):
        bad = []
        for (p, fn), (bio, nat, sc) in self.PINS.items():
            f = entries[p]['forms'][fn]
            got = (f.get('bio_score'), f.get('natural'), f.get('score'))
            if got != (bio, nat, sc):
                bad.append((p, fn, got, (bio, nat, sc)))
        assert not bad, "\n".join(f"  {p}/{fn}: {g} != {e}" for p, fn, g, e in bad)

    def test_taurine_food_outscores_generic(self, entries):
        """The genuinely natural food form should not be out-scored by the
        synthetic generic form."""
        forms = entries['taurine']['forms']
        assert forms['taurine from food']['score'] >= forms['taurine (generic)']['score']
