"""
Mushroom (fungal active) scoring + classification contract.

Mushrooms are non-systemic / local-matrix actives: bio_score = fungal active-form
quality + delivery-to-site (fruiting body, extract standardization, beta-glucan;
mycelium-on-grain penalty), NOT systemic absorption. They are tagged with
orthogonal fungal fields rather than a category hack (category_enum stays a valid
bucket - 'herbs' - until a coordinated vocab migration adds 'mushrooms').

Locks the contract so it does not drift.

Run with: pytest scripts/tests/test_iqm_mushrooms.py -q
"""

import json
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'
MUSHROOMS = ['lions_mane', 'reishi', 'cordyceps', 'cordycepsprime', 'ahcc']


@pytest.fixture(scope='module')
def entries():
    with open(IQM_PATH, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k != '_metadata'}


class TestFungalClassification:
    def test_orthogonal_fungal_fields(self, entries):
        for k in MUSHROOMS:
            e = entries[k]
            assert e.get('source_origin') == 'fungal', k
            assert e.get('ingredient_domain') == 'fungal_mushroom', k
            assert e.get('local_matrix_active') is True, k

    def test_category_is_valid_bucket(self, entries):
        """Stay in a valid runtime bucket until a coordinated 'mushrooms' vocab
        migration (do NOT use botanical/mushroom_extracts as a quick edit)."""
        for k in MUSHROOMS:
            assert entries[k].get('category_enum') == 'herbs', k


class TestFungalFormScoring:
    def test_unspecified_does_not_outrank_disclosed(self, entries):
        """Unspecified mushroom forms must rank below disclosed fruiting-body /
        standardized forms, and carry no natural bonus."""
        for k in MUSHROOMS:
            forms = entries[k]['forms']
            disclosed = [f['bio_score'] for fn, f in forms.items()
                         if isinstance(f, dict) and 'unspecified' not in fn.lower()]
            for fn, f in forms.items():
                if isinstance(f, dict) and 'unspecified' in fn.lower():
                    if disclosed:
                        assert f['bio_score'] <= min(disclosed), f"{k}/{fn}"
                    assert f.get('natural') is False, f"{k}/{fn} natural bonus"

    def test_local_form_quality_band(self, entries):
        """Non-systemic mushroom forms are not premium-systemic: disclosed forms
        sit in a moderate band (<=13), never the 14-15 systemic-premium tier."""
        for k in MUSHROOMS:
            for fn, f in entries[k]['forms'].items():
                if isinstance(f, dict):
                    assert (f.get('bio_score') or 0) <= 13, f"{k}/{fn}"

    def test_mushroom_extract_label_scorable(self, entries):
        """'<Mushroom> Mushroom Extract' labels must map to a disclosed form."""
        def aliases(k):
            return {a.lower() for f in entries[k]['forms'].values()
                    if isinstance(f, dict) for a in f.get('aliases', [])}
        assert "lion's mane mushroom extract" in aliases('lions_mane')
        assert 'reishi mushroom extract' in aliases('reishi')
        assert 'cordyceps mushroom extract' in aliases('cordyceps')
