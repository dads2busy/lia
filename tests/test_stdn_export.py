import pytest
import pyarrow as pa
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "UN_Comtrade"


def test_load_partner_areas():
    """partnerAreas.arrow loads and contains US (code 840)."""
    from lia.stdn_export.comtrade_query import load_partner_map
    partner_map = load_partner_map(DATA_DIR / "partnerAreas.arrow")
    assert 840 in partner_map
    assert partner_map[840]["name"] == "United States of America"
    assert partner_map[840]["iso3"] == "USA"
    assert len(partner_map) > 200


def test_query_us_imports_with_known_hs_code():
    """Querying a common HS code returns non-empty results for US imports."""
    from lia.stdn_export.comtrade_query import query_us_imports
    # HS 260500 = Cobalt ores, should have US import records
    # In this dataset the US reporter code is 842 (not 840)
    rows = query_us_imports(DATA_DIR, [2023], {"260500"}, reporter_code=842)
    assert len(rows) > 0
    assert all(r["reporterCode"] == 842 for r in rows)
    assert all(r["cmdCode"] == "260500" for r in rows)
