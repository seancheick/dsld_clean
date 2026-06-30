"""
Cross-parent consistency for forms that appear under more than one parent.

The same physical form (same name) must carry the same natural flag regardless
of which parent it is listed under. Mismatches found in audit:
- 'magnesium glycinate' (a synthesized amino-acid chelate) was natural=false in
  the magnesium parent but natural=true under l_glycine.
- 'liposomal curcumin' (a synthesized delivery system) was natural=true in the
  curcumin parent but natural=false under turmeric.
Synthesized chelates and delivery systems are not natural-source forms.

Run with: pytest scripts/tests/test_iqm_cross_parent_consistency.py -q
"""

import json
from collections import defaultdict
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'

# Generic form-names that are NOT a shared substance (different ingredients
# legitimately reuse these labels), so they are exempt from the cross-parent
# natural-consistency rule.
GENERIC_FORM_NAMES = {'standard', 'unspecified'}


@pytest.fixture(scope='module')
def entries():
    with open(IQM_PATH, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k != '_metadata'}


class TestCrossParentNaturalConsistency:
    def test_same_form_same_natural(self, entries):
        m = defaultdict(set)
        where = defaultdict(list)
        for k, e in entries.items():
            for fn, f in e.get('forms', {}).items():
                if not isinstance(f, dict) or f.get('natural') is None:
                    continue
                name = fn.strip().lower()
                if name in GENERIC_FORM_NAMES or 'unspecified' in name:
                    continue
                m[name].add(f['natural'])
                where[name].append((k, f['natural']))
        bad = {fn: where[fn] for fn, nats in m.items() if len(nats) > 1}
        assert not bad, "Same form-name with inconsistent natural flag:\n" + \
            "\n".join(f"  {fn}: {locs}" for fn, locs in bad.items())


class TestSynthesizedFormsNotNatural:
    def test_pins(self, entries):
        assert entries['l_glycine']['forms']['magnesium glycinate']['natural'] is False
        assert entries['curcumin']['forms']['liposomal curcumin']['natural'] is False
