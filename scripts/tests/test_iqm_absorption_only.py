"""
bio_score semantics invariants for ingredient_quality_map.json.

Per the agreed model, bio_score is scored differently by active type:
- SYSTEMIC actives (vitamins/minerals/amino acids; and systemic-TARGET
  ingredients that happen to be poorly absorbed): bio_score = systemic
  absorption. Poorly-absorbed systemic-target ingredients must score low.
- NON-systemic / local actives (probiotics, mushrooms, fibers, demulcents,
  phytosterols, digestive enzymes): bio_score = form quality + delivery to the
  site of action (the probiotic model) - NOT systemic absorption. These are
  intentionally NOT flattened, so they have no absorption cap here.

This test pins the systemic-but-poorly-absorbed values (which stay low) so they
can't be re-inflated.

Run with: pytest scripts/tests/test_iqm_absorption_only.py -q
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


class TestSystemicPoorlyAbsorbedStayLow:
    """Systemic-TARGET ingredients that are genuinely poorly absorbed orally
    must not be scored as well-absorbed (these are not 'form-quality' carve-outs;
    the benefit requires systemic absorption that does not occur)."""

    PINS = {
        # hyaluronic acid: large polymer, MW-limited oral absorption
        ('hyaluronic_acid', 'high molecular weight HA'): 6,
        ('hyaluronic_acid', 'acetylated HA'): 8,
        # large systemic enzymes degraded/poorly absorbed orally
        ('superoxide_dismutase', 'sod supplement'): 5,
        ('glutathione_peroxidase', 'glutathione peroxidase enzyme'): 5,
        # nattokinase: intact-protein oral absorption limited/debated
        ('nattokinase', 'nattokinase standard'): 8,
        ('nattokinase_nsk_sd', 'nsk-sd'): 8,
    }

    def test_pins(self, entries):
        bad = []
        for (p, fn), want in self.PINS.items():
            got = entries[p]['forms'][fn].get('bio_score')
            if got != want:
                bad.append((p, fn, got, want))
        assert not bad, "Systemic poorly-absorbed bio_score drifted:\n" + \
            "\n".join(f"  {p}/{fn}: {g} != {w}" for p, fn, g, w in bad)
