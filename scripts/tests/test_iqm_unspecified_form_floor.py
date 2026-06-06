"""
Unspecified-form floor policy for ingredient_quality_map.json.

Policy notes / scope:
  A global "unspecified < min(specific)" rule is intentionally NOT enforced,
  because for many vitamins/minerals the lowest specific form is a *degraded*
  or *wrong* form (e.g. oxide, oxidized isomer, vitamin D2) that legitimately
  scores below a neutral unspecified row. Forcing unspecified below those would
  be incorrect.

  What we DO enforce is the probiotic identity floor, which is unambiguous and
  consistent across the database: a probiotic row carrying NO genus/species/
  strain identity (a "(unspecified)" form, or the bare `probiotic_unspecified`
  catch-all parent) must be scored conservatively. Strain identity, CFU, and
  survivability are scored elsewhere in the pipeline, so a bare "Probiotic"
  label must not inherit premium strain evidence.

Run with: pytest scripts/tests/test_iqm_unspecified_form_floor.py -q
"""

import json
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'
PROBIOTIC_UNSPEC_CEILING = 7


@pytest.fixture(scope='module')
def entries():
    with open(IQM_PATH, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k != '_metadata'}


def _is_probiotic(entry):
    return entry.get('category') == 'probiotics' or entry.get('category_enum') == 'probiotics'


class TestProbioticUnspecifiedFloor:
    def test_probiotic_unspecified_forms_are_conservative(self, entries):
        """Probiotic forms with no strain/species identity must be conservatively
        scored (bio_score <= 7) and not flagged natural (no +3 bonus on an
        unknown-identity row)."""
        bad = []
        for key, entry in entries.items():
            if not _is_probiotic(entry):
                continue
            for form_name, form in entry.get('forms', {}).items():
                if not isinstance(form, dict):
                    continue
                is_unspec = (
                    'unspecified' in form_name.lower()
                    or key == 'probiotic_unspecified'
                )
                if not is_unspec:
                    continue
                bs = form.get('bio_score')
                if bs is not None and bs > PROBIOTIC_UNSPEC_CEILING:
                    bad.append((key, form_name, 'bio_score', bs))
                if form.get('natural'):
                    bad.append((key, form_name, 'natural', True))
        assert not bad, (
            "Probiotic unspecified/catch-all rows must be conservative "
            f"(bio_score <= {PROBIOTIC_UNSPEC_CEILING}, natural=false):\n"
            + "\n".join(f"  {k}/{fn}: {field}={v}" for k, fn, field, v in bad)
        )

    def test_bare_probiotic_catchall_matches_convention(self, entries):
        """The bare `probiotic_unspecified` parent must match the (unspecified)
        convention used by every dedicated probiotic parent: bio_score 5,
        natural false, score 5."""
        parent = entries.get('probiotic_unspecified')
        assert parent is not None, "probiotic_unspecified parent missing"
        form = parent['forms']['standard']
        assert form['bio_score'] == 5, form['bio_score']
        assert form['natural'] is False, form['natural']
        assert form['score'] == 5, form['score']
