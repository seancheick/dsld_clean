"""
Fatty-acid unspecified-form regressions for ingredient_quality_map.json.

Several fatty-acid/oil parents had an 'unspecified' form scored ABOVE one of
their own legitimate specific forms (an unlabeled "DHA" out-scoring a known
ethyl-ester DHA). The unspecified row must sit at or below the lowest
*legitimate* specific form (genuinely poor forms - flaxseed ALA, oxidized,
ethyl ester being the floor here - are the documented exception).

Pins the corrected unspecified bio_scores and guards against the inversion
returning for these parents.

Run with: pytest scripts/tests/test_iqm_fatty_acids.py -q
"""

import json
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'
FIXED = ['dha', 'epa', 'fish_oil', 'ceramides', 'hemp_seed_oil']


@pytest.fixture(scope='module')
def entries():
    with open(IQM_PATH, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k != '_metadata'}


class TestFattyAcidUnspecified:
    def test_unspecified_pinned_to_8(self, entries):
        bad = [(k, entries[k]['forms']['unspecified']['bio_score'])
               for k in FIXED
               if entries[k]['forms']['unspecified']['bio_score'] != 8]
        assert not bad, "fatty-acid unspecified bio_score drifted from 8:\n" + \
            "\n".join(f"  {k}: {b}" for k, b in bad)

    def test_unspecified_not_above_ee_form(self, entries):
        """For these parents the unspecified row must not exceed the
        ethyl-ester / synthetic / refined floor form."""
        for k in FIXED:
            forms = entries[k]['forms']
            uns = forms['unspecified']['bio_score']
            legit = [f['bio_score'] for fn, f in forms.items()
                     if isinstance(f, dict) and 'unspecified' not in fn.lower()
                     and f.get('bio_score') is not None]
            assert uns <= min(legit), f"{k}: unspecified {uns} > min specific {min(legit)}"
