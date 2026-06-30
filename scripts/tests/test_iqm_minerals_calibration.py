"""
Mineral calibration invariants for ingredient_quality_map.json.

Two data-truth rules, both grounded in the metadata's own `natural` criteria
("derived from food or plant sources / natural cofactors / whole-food /
naturally-occurring chelates") and in cross-parent consistency:

1. Inorganic mineral salts (forms named *oxide/*hydroxide/*carbonate/
   *bicarbonate/*chloride/*sulfate) are not food/plant-derived and are not
   natural chelates, so they must NOT carry natural=true. The +3 natural bonus
   on such salts produces absorption-ranking inversions (a poorly-absorbed salt
   outscoring a better-absorbed organic form). Note: organic complexes such as
   calcium fructoborate intentionally do not match these suffixes.

2. A mineral form with unknown identity ("(unspecified)") must not receive the
   natural bonus — you cannot credit naturalness to an unknown form. Every
   dedicated mineral parent already scores its (unspecified) row natural=false.

Plus explicit regression pins for the rows corrected in the minerals batch.

Run with: pytest scripts/tests/test_iqm_minerals_calibration.py -q
"""

import json
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'
SALT_SUFFIXES = ('oxide', 'hydroxide', 'carbonate', 'bicarbonate', 'chloride',
                 'sulfate', 'sulphate')


@pytest.fixture(scope='module')
def entries():
    with open(IQM_PATH, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k != '_metadata'}


def _minerals(entries):
    for k, e in entries.items():
        if e.get('category') == 'minerals' or e.get('category_enum') == 'minerals':
            yield k, e


class TestMineralNaturalFlag:
    def test_inorganic_salts_not_natural(self, entries):
        """Inorganic mineral salts must not be flagged natural=true."""
        bad = []
        for k, e in _minerals(entries):
            for fn, f in e.get('forms', {}).items():
                if not isinstance(f, dict):
                    continue
                if fn.strip().lower().endswith(SALT_SUFFIXES) and f.get('natural'):
                    bad.append((k, fn))
        assert not bad, (
            "Inorganic mineral salts flagged natural=true (no +3 bonus allowed):\n"
            + "\n".join(f"  {k}/{fn}" for k, fn in bad)
        )

    def test_unspecified_minerals_not_natural(self, entries):
        """Unknown-identity mineral forms must not receive the natural bonus."""
        bad = []
        for k, e in _minerals(entries):
            for fn, f in e.get('forms', {}).items():
                if not isinstance(f, dict):
                    continue
                if 'unspecified' in fn.lower() and f.get('natural'):
                    bad.append((k, fn))
        assert not bad, (
            "Unspecified mineral forms flagged natural=true:\n"
            + "\n".join(f"  {k}/{fn}" for k, fn in bad)
        )


class TestMineralRegressionPins:
    """Pin the specific corrections made in the minerals batch."""

    PINS = {
        ('silicon', 'standard'): (6, False, 6),
        ('fluoride', 'standard'): (6, False, 6),
        ('iodine', 'iodine (unspecified)'): (6, False, 6),
        ('calcium', 'calcium carbonate'): (8, False, 8),
        ('calcium', 'coral calcium'): (6, False, 6),
        ('magnesium', 'magnesium carbonate'): (6, False, 6),
        ('magnesium', 'magnesium chloride'): (9, False, 9),
        ('magnesium', 'magnesium sulfate'): (5, False, 5),
        ('phosphorus', 'phosphate salts'): (10, False, 10),
    }

    def test_pins(self, entries):
        bad = []
        for (parent, form), (bio, nat, sc) in self.PINS.items():
            f = entries[parent]['forms'][form]
            got = (f.get('bio_score'), f.get('natural'), f.get('score'))
            if got != (bio, nat, sc):
                bad.append((parent, form, got, (bio, nat, sc)))
        assert not bad, (
            "Mineral regression pin mismatches (got vs expected):\n"
            + "\n".join(f"  {p}/{fn}: {g} != {e}" for p, fn, g, e in bad)
        )
