import pytest
import pyarrow as pa
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "UN_Comtrade"

pytestmark = pytest.mark.skipif(
    not DATA_DIR.exists(), reason="Comtrade data not available"
)


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


def test_full_aggregation_pipeline():
    """Test the aggregation pipeline with a manually constructed bucket."""
    from lia.stdn_export import HSCodeEntry, MaterialBucket, TradeFlowRow
    from lia.stdn_export.comtrade_query import (
        aggregate_trade_data,
        load_partner_map,
        query_us_imports,
    )

    # Create a test bucket for Cobalt (HS 260500 = cobalt ores)
    bucket = MaterialBucket(
        hs_codes=[HSCodeEntry(
            code="260500",
            description="Cobalt ores and concentrates",
            quality="clean",
            relevance="cobalt raw ore",
        )],
        model="test",
    )
    buckets = {"Cobalt": bucket}

    partner_map = load_partner_map(DATA_DIR / "partnerAreas.arrow")
    raw_rows = query_us_imports(DATA_DIR, [2023], {"260500"})

    if not raw_rows:
        pytest.skip("No Comtrade Arrow data files available")

    trade_rows = aggregate_trade_data(raw_rows, buckets, partner_map)

    assert len(trade_rows) > 0
    assert all(isinstance(r, TradeFlowRow) for r in trade_rows)
    assert all(r.material == "Cobalt" for r in trade_rows)
    assert all(r.year == 2023 for r in trade_rows)

    # Shares should sum to ~100%
    total_share = sum(r.import_share_pct for r in trade_rows)
    assert 99.0 <= total_share <= 101.0

    # Ranks should be sequential
    ranks = [r.exporter_rank for r in trade_rows]
    assert ranks == list(range(1, len(ranks) + 1))

    # Quality should be clean (single clean HS code)
    assert all(r.hs_bucket_quality == "clean" for r in trade_rows)
