"""
Identifier integrity for ingredient_quality_map.json.

Guards CUI / RxCUI hygiene (A-IQM-5) at the value level:
- cui, when present, is either null or a well-formed UMLS CUI (C + 7 digits).
- rxcui, when present, is either null or a numeric RxNorm identifier string.
- Empty strings and placeholder junk ('', 'none', 'null', 'n/a') are forbidden;
  an absent identifier must be null (so the existing schema requirement that a
  null identifier carries an explanatory note actually applies).
- A null cui/rxcui must carry a cui_note/rxcui_note.

We never invent identifiers: normalization only converts junk to null. Format
checks ensure any *present* identifier is at least structurally valid.

Run with: pytest scripts/tests/test_iqm_identifier_integrity.py -q
"""

import json
import re
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'
JUNK = {'', 'none', 'null', 'n/a', 'na'}
CUI_RE = re.compile(r'C\d{7}')
RXCUI_RE = re.compile(r'\d+')
UNII_RE = re.compile(r'[A-Z0-9]{10}')

# Identifiers verified via official APIs during the audit (RxNorm exact-name /
# FDA GSRS exact-name). Pinned so a regression can't silently drop or corrupt
# a verified value.
VERIFIED_RXCUI = {
    'strontium': '10122', 'gamma_oryzanol': '25608', 'chrysin': '1362888',
    'lactoferrin': '1425933', 'myricetin': '1368374', 'white_tea': '1651698',
    'evening_primrose_oil': '203219', 'corn_silk': '283677',
    'thyme_extract': '1376349', 'celadrin': '2380349',
}
VERIFIED_UNII = {
    'fucoxanthin': '06O0TC0VSM', 'chrysin': '3CN01F5ZJ5', 'myricetin': '76XC01FTOJ',
    'polygodial': '5FAF7T66M7', 'corn_silk': '7D3VB244UX',
    'evening_primrose_oil': '3Q9L08K71N',
}


@pytest.fixture(scope='module')
def entries():
    with open(IQM_PATH, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k != '_metadata'}


class TestNoJunkIdentifiers:
    def test_cui_not_junk(self, entries):
        bad = [(k, repr(e.get('cui'))) for k, e in entries.items()
               if isinstance(e.get('cui'), str) and e['cui'].strip().lower() in JUNK]
        assert not bad, "cui set to placeholder junk (use null instead):\n" + \
            "\n".join(f"  {k}: {v}" for k, v in bad)

    def test_rxcui_not_junk(self, entries):
        bad = [(k, repr(e.get('rxcui'))) for k, e in entries.items()
               if isinstance(e.get('rxcui'), str) and e['rxcui'].strip().lower() in JUNK]
        assert not bad, "rxcui set to placeholder junk (use null instead):\n" + \
            "\n".join(f"  {k}: {v}" for k, v in bad)


class TestIdentifierFormat:
    def test_cui_well_formed(self, entries):
        bad = [(k, repr(e.get('cui'))) for k, e in entries.items()
               if isinstance(e.get('cui'), str) and e['cui'].strip().lower() not in JUNK
               and not CUI_RE.fullmatch(e['cui'].strip())]
        assert not bad, "Malformed CUI (expected C+7 digits):\n" + \
            "\n".join(f"  {k}: {v}" for k, v in bad)

    def test_rxcui_well_formed(self, entries):
        bad = [(k, repr(e.get('rxcui'))) for k, e in entries.items()
               if isinstance(e.get('rxcui'), str) and e['rxcui'].strip().lower() not in JUNK
               and not RXCUI_RE.fullmatch(e['rxcui'].strip())]
        assert not bad, "Malformed RxCUI (expected numeric string):\n" + \
            "\n".join(f"  {k}: {v}" for k, v in bad)


class TestUniiFormat:
    def test_unii_well_formed(self, entries):
        """When present, unii must be a 10-char base-36 FDA UNII; a null/absent
        unii needs no note (unii is optional and unpopulated for most rows)."""
        bad = [(k, repr(e.get('unii'))) for k, e in entries.items()
               if e.get('unii') is not None
               and not (isinstance(e.get('unii'), str) and UNII_RE.fullmatch(e['unii'].strip()))]
        assert not bad, "Malformed UNII (expected 10 [A-Z0-9]):\n" + \
            "\n".join(f"  {k}: {v}" for k, v in bad)


class TestVerifiedIdentifiersPinned:
    def test_verified_rxcui_present(self, entries):
        bad = [(k, entries[k].get('rxcui'), v) for k, v in VERIFIED_RXCUI.items()
               if entries[k].get('rxcui') != v]
        assert not bad, "Verified RxCUI drifted:\n" + \
            "\n".join(f"  {k}: {got} != {exp}" for k, got, exp in bad)

    def test_verified_unii_present(self, entries):
        bad = [(k, entries[k].get('unii'), v) for k, v in VERIFIED_UNII.items()
               if entries[k].get('unii') != v]
        assert not bad, "Verified UNII drifted:\n" + \
            "\n".join(f"  {k}: {got} != {exp}" for k, got, exp in bad)


class TestNoDuplicateCui:
    def test_no_cross_parent_duplicate_cui(self, entries):
        """A CUI must not be shared by two different parents (signals a
        copy-paste / mis-join error like the dandelion+perilla d-limonene bug)."""
        from collections import defaultdict
        m = defaultdict(list)
        for k, e in entries.items():
            if e.get('cui'):
                m[e['cui']].append(k)
        dups = {c: ks for c, ks in m.items() if len(ks) > 1}
        assert not dups, "Duplicate CUI across parents:\n" + \
            "\n".join(f"  {c}: {ks}" for c, ks in dups.items())


# UMLS-verified CUI corrections (sample pins of the systemic re-derivation).
VERIFIED_CUI = {
    'iron': 'C0302583', 'zinc': 'C0043481', 'boron': 'C0006030',
    'vanadium': 'C0042306', 'magnesium': 'C0024467', 'manganese': 'C0024706',
    'curcumin': 'C0010467', 'melatonin': 'C0025219', 'collagen': 'C0009325',
    'glutathione': 'C0017817', 'taurine': 'C0039350', 'l_valine': 'C0042285',
    'gaba': 'C0016904', 'coq10': 'C0041536', 'dandelion': 'C0877851',
    'perilla_oil': 'C0070421',
}


class TestVerifiedCuiPinned:
    def test_verified_cui(self, entries):
        bad = [(k, entries[k].get('cui'), v) for k, v in VERIFIED_CUI.items()
               if entries[k].get('cui') != v]
        assert not bad, "Verified CUI drifted:\n" + \
            "\n".join(f"  {k}: {got} != {exp}" for k, got, exp in bad)


class TestNullIdentifierHasNote:
    def test_null_cui_has_note(self, entries):
        bad = [k for k, e in entries.items()
               if e.get('cui') is None and not e.get('cui_note')]
        assert not bad, "null cui without cui_note:\n" + "\n".join(f"  {k}" for k in bad)

    def test_null_rxcui_has_note(self, entries):
        bad = [k for k, e in entries.items()
               if e.get('rxcui') is None and not e.get('rxcui_note')]
        assert not bad, "null rxcui without rxcui_note:\n" + "\n".join(f"  {k}" for k in bad)
