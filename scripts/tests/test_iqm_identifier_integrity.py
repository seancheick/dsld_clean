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


class TestNullIdentifierHasNote:
    def test_null_cui_has_note(self, entries):
        bad = [k for k, e in entries.items()
               if e.get('cui') is None and not e.get('cui_note')]
        assert not bad, "null cui without cui_note:\n" + "\n".join(f"  {k}" for k in bad)

    def test_null_rxcui_has_note(self, entries):
        bad = [k for k, e in entries.items()
               if e.get('rxcui') is None and not e.get('rxcui_note')]
        assert not bad, "null rxcui without rxcui_note:\n" + "\n".join(f"  {k}" for k in bad)
