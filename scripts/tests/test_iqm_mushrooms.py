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
MUSHROOMS = [
    'lions_mane', 'reishi', 'cordyceps', 'cordycepsprime', 'ahcc',
    'turkey_tail', 'chaga', 'maitake', 'shiitake', 'button_mushroom', 'auricularia',
]
# label -> parent whose '<X> mushroom extract' alias must route to a disclosed extract form
EXTRACT_LABEL_ROUTES = {
    "lion's mane mushroom extract": 'lions_mane',
    'reishi mushroom extract': 'reishi',
    'cordyceps mushroom extract': 'cordyceps',
    'turkey tail mushroom extract': 'turkey_tail',
    'chaga mushroom extract': 'chaga',
    'maitake mushroom extract': 'maitake',
    'shiitake mushroom extract': 'shiitake',
}


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

    def test_category_is_decided_bucket(self, entries):
        """Mushrooms use category_enum='mushroom_extracts' (decision: chosen over
        'herbs' to match current main's vocabulary; ahcc already used it there)."""
        for k in MUSHROOMS:
            assert entries[k].get('category_enum') == 'mushroom_extracts', k

    def test_no_mushroom_routes_to_stale_category(self, entries):
        """No mushroom parent may regress to the pre-decision/piecemeal categories
        (herbs catch-all, adaptogens use-case, botanical, or null)."""
        BANNED = {'botanical', 'fungal', 'mushrooms', 'adaptogens', 'herbs', None}
        for k in MUSHROOMS:
            e = entries[k]
            assert e.get('category') not in BANNED, f"{k} category={e.get('category')}"
            assert e.get('category_enum') not in BANNED, f"{k} enum={e.get('category_enum')}"


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

    def test_mushroom_extract_label_routes_to_disclosed_extract(self, entries):
        """'<Mushroom> Mushroom Extract' labels must route to a *disclosed extract*
        form (not unspecified) so the label stays scorable at the extract tier."""
        for label, parent in EXTRACT_LABEL_ROUTES.items():
            hit = None
            for fn, f in entries[parent]['forms'].items():
                if isinstance(f, dict) and label in {a.lower() for a in f.get('aliases', [])}:
                    hit = fn
                    break
            assert hit is not None, f"{label} not found on {parent}"
            assert 'unspecified' not in hit.lower(), f"{label} -> unspecified ({parent}/{hit})"
            assert 'extract' in hit.lower() or 'militaris' in hit.lower(), \
                f"{label} -> non-extract form {parent}/{hit}"
