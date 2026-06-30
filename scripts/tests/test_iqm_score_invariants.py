"""
Score-formula and bio_score type invariants for ingredient_quality_map.json.

These guard the v4 scoring contract:
- bio_score is an integer in 0..15
- score is an integer
- score == min(bio_score + 3 if natural else bio_score, 18)

The natural bonus is a fixed +3 (see _metadata.scoring_system.natural_bonus.value).
A form that is flagged natural=true MUST receive the full +3 bonus; a form that
is not natural MUST score exactly bio_score. Any drift is a data-truth bug, not
a calibration choice.

Run with: pytest scripts/tests/test_iqm_score_invariants.py -q
"""

import json
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'
NATURAL_BONUS = 3
MAX_SCORE = 18


@pytest.fixture(scope='module')
def entries():
    with open(IQM_PATH, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k != '_metadata'}


def _iter_forms(entries):
    for ing_key, entry in entries.items():
        for form_name, form_data in entry.get('forms', {}).items():
            if isinstance(form_data, dict):
                yield ing_key, form_name, form_data


class TestBioScoreType:
    def test_bio_score_is_int_in_range(self, entries):
        """bio_score must be an integer in 0..15 (no floats, no bools)."""
        bad = []
        for ing, form, f in _iter_forms(entries):
            bs = f.get('bio_score')
            if bs is None:
                continue
            if isinstance(bs, bool) or not isinstance(bs, int) or bs < 0 or bs > 15:
                bad.append((ing, form, repr(bs)))
        assert not bad, (
            f"Found {len(bad)} bio_score values that are not int 0..15:\n"
            + "\n".join(f"  {i}/{fo}: {b}" for i, fo, b in bad[:20])
        )

    def test_score_is_int(self, entries):
        """score must be an integer."""
        bad = []
        for ing, form, f in _iter_forms(entries):
            sc = f.get('score')
            if sc is None:
                continue
            if isinstance(sc, bool) or not isinstance(sc, int):
                bad.append((ing, form, repr(sc)))
        assert not bad, (
            f"Found {len(bad)} non-integer score values:\n"
            + "\n".join(f"  {i}/{fo}: {s}" for i, fo, s in bad[:20])
        )


class TestScoreFormula:
    def test_score_matches_formula(self, entries):
        """score == min(bio_score + 3 if natural else bio_score, 18)."""
        violations = []
        for ing, form, f in _iter_forms(entries):
            bs = f.get('bio_score')
            if bs is None:
                continue
            natural = bool(f.get('natural'))
            expected = min(bs + (NATURAL_BONUS if natural else 0), MAX_SCORE)
            if f.get('score') != expected:
                violations.append((ing, form, bs, natural, f.get('score'), expected))
        assert not violations, (
            f"Found {len(violations)} score/formula mismatches "
            f"(score != min(bio+3 if natural else bio, 18)):\n"
            + "\n".join(
                f"  {i}/{fo}: bio={b} natural={n} score={s} expected={e}"
                for i, fo, b, n, s, e in violations[:30]
            )
        )
