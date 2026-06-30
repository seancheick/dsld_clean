"""
Notes-vs-score consistency for ingredient_quality_map.json.

bio_score is absorption/bioavailability only. A form whose own notes explicitly
state poor / low / minimal / local-only absorption must not carry a high
bio_score - clinical efficacy is scored elsewhere and must not inflate the
absorption score (audit task rule: "If notes say 'clinical benefits' but not
absorption, do not use that alone to justify high bio_score").

Fixed in batch 14: apigenin extract (13->6) and berberine hcl (11->6), both of
which had quality=poor and notes stating poor/low bioavailability (PubMed-
supported; basis for their enhanced-delivery research).

Run with: pytest scripts/tests/test_iqm_notes_score_consistency.py -q
"""

import json
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'
NEG_ABSORPTION = [
    'poor absorption', 'poorly absorbed', 'minimal systemic', 'local action',
    'not absorbed', 'low bioavailability', 'not systemically',
    'negligible absorption', 'poor oral', 'poor bioavailability',
    'not well absorbed', 'limited absorption', 'low absorption',
]
HIGH = 11


@pytest.fixture(scope='module')
def entries():
    with open(IQM_PATH, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k != '_metadata'}


class TestNotesVsScore:
    def test_no_high_bio_with_poor_absorption_notes(self, entries):
        bad = []
        for k, e in entries.items():
            for fn, f in e.get('forms', {}).items():
                if not isinstance(f, dict):
                    continue
                notes = (f.get('notes') or '').lower()
                bio = f.get('bio_score') or 0
                if bio >= HIGH and any(n in notes for n in NEG_ABSORPTION):
                    bad.append((k, fn, bio))
        assert not bad, (
            f"Forms with bio_score >= {HIGH} whose notes state poor/low absorption "
            "(absorption score must not reflect clinical efficacy):\n"
            + "\n".join(f"  {k}/{fn}: bio={b}" for k, fn, b in bad)
        )

    def test_pins(self, entries):
        assert entries['apigenin']['forms']['apigenin extract']['bio_score'] == 6
        assert entries['berberine_supplement']['forms']['berberine hcl']['bio_score'] == 6

    def test_green_tea_catechins_not_above_standardized(self, entries):
        """Generic 'green tea catechins' must not out-score the parent's own
        standardized 50% EGCG extract (EGCG/catechins are poorly bioavailable;
        the bonus belongs to delivery-enhanced/standardized forms)."""
        forms = entries['green_tea_extract']['forms']
        assert forms['green tea catechins']['bio_score'] <= \
            forms['green tea extract (50% EGCG)']['bio_score']
