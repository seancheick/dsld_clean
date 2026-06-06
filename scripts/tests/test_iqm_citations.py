"""
Citation integrity for ingredient_quality_map.json.

Any PMID cited in form notes must be in the verified allowlist (each was
confirmed to resolve to a real, topically-correct PubMed article via NCBI
E-utilities during the audit). This guards against fabricated/unverified PMIDs
slipping into the data - identifiers must never be invented.

Run with: pytest scripts/tests/test_iqm_citations.py -q
"""

import json
import re
from pathlib import Path

import pytest

IQM_PATH = Path(__file__).parent.parent / 'data' / 'ingredient_quality_map.json'

# PMIDs verified via NCBI E-utilities (resolve to the cited topic):
#  30328058 quercetin phytosome oral absorption (Riva, Eur J Drug Metab Pharmacokinet 2019)
#  39756599 polyphenol supramolecular delivery (Int J Pharm 2025)
#  39756973 anthocyanin cyanidin-3-glucoside bioavailability (J Nutr Sci Vitaminol 2024)
#  41106481 EGCG gut-health axis (Adv Nutr 2025)
#  41265600 apigenin oral delivery (Int J Biol Macromol 2025)
#  42120042 berberine mucoadhesive delivery (J Drug Target 2026)
VERIFIED_PMIDS = {
    '30328058', '39756599', '39756973', '41106481', '41265600', '42120042',
    '34115818', '37057922',
}


@pytest.fixture(scope='module')
def raw():
    return IQM_PATH.read_text()


def test_all_cited_pmids_are_verified(raw):
    cited = set(re.findall(r'PMID (\d+)', raw))
    unverified = cited - VERIFIED_PMIDS
    assert not unverified, (
        f"Unverified PMIDs cited in IQM notes: {sorted(unverified)}. "
        "Every PMID must be confirmed via PubMed and added to VERIFIED_PMIDS."
    )
