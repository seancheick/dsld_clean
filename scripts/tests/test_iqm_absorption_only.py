"""
Absorption-only policy invariants for ingredient_quality_map.json.

Under the absorption-only bio_score policy, local/luminal-effect ingredients
(targeted-effect forms) must NOT be scored as systemic-absorption winners.
bio_score reflects systemic absorption; functional efficacy of non-absorbed
actives is scored on a separate axis.

Extended per category as the sweep proceeds.

Run with: pytest scripts/tests/test_iqm_absorption_only.py -q
"""

import json
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'
LOCAL_EFFECT_BIO_CAP = 6  # fibers etc. are not systemically absorbed


@pytest.fixture(scope='module')
def entries():
    with open(IQM_PATH, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k != '_metadata'}


class TestFiberAbsorptionCap:
    def test_fibers_not_systemic_winners(self, entries):
        bad = []
        for k, e in entries.items():
            if e.get('category') != 'fibers':
                continue
            for fn, f in e.get('forms', {}).items():
                if isinstance(f, dict) and (f.get('bio_score') or 0) > LOCAL_EFFECT_BIO_CAP:
                    bad.append((k, fn, f.get('bio_score')))
        assert not bad, (
            f"Fiber forms with bio_score > {LOCAL_EFFECT_BIO_CAP} (fibers are "
            "luminal-acting, not systemically absorbed):\n"
            + "\n".join(f"  {k}/{fn}: bio={b}" for k, fn, b in bad)
        )
