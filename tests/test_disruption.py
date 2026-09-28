import json
from pathlib import Path
import pyarrow as pa
import pytest
from scripts.eval.disruption import load_trade, dominance, propagate, analyze_state, summarize

EDGES = [(frozenset({"100000", "200000"}), frozenset({"300000"})),
         (frozenset({"300000"}), frozenset({"400000", "500000"})),
         (frozenset({"400000", "600000"}), frozenset({"700000"})),
         (frozenset({"800000"}), frozenset({"400000"}))]

def _arrow(path: Path, rows: list[tuple]) -> Path:
    t = pa.table({"partnerCode": pa.array([r[0] for r in rows], pa.int64()),
                  "reporterCode": pa.array([r[1] for r in rows], pa.int64()),
                  "cmdCode": pa.array([r[2] for r in rows], pa.string()),
                  "refYear": pa.array([2024] * len(rows), pa.int64()),
                  "value": pa.array([float(r[3]) for r in rows], pa.float64())})
    with pa.OSFile(str(path), "wb") as f, pa.ipc.new_file(f, t.schema) as w: w.write_table(t)
    return path

TRADE = [(1, 9, "100000", 40), (1, 8, "100000", 40), (2, 9, "100000", 50),   # 80/130 = 0.615 -> dominated
         (1, 9, "300000", 50), (2, 9, "300000", 50),                          # 50/50 -> not
         (3, 9, "400000", 60), (4, 9, "400000", 40),                          # exactly 60% -> dominated (>=)
         (5, 9, "999999", 10)]                                                # not in the MEKH

def test_load_trade_and_dominance(tmp_path):
    df = load_trade(_arrow(tmp_path / "t.arrow", TRADE), {"100000", "300000", "400000", "700000"})
    assert set(df["cmdCode"]) == {"100000", "300000", "400000"}
    d = dominance(df, 0.6)
    assert d["100000"]["top_partner"] == 1 and d["100000"]["share"] == pytest.approx(80 / 130) and d["100000"]["dominated"]
    assert not d["300000"]["dominated"] and d["400000"]["dominated"] and d["400000"]["top_partner"] == 3
    assert "700000" not in d

def test_propagate_original_semantics():
    # a process dies if ANY input is disrupted; a material dies when ALL its producers are dead;
    # materials nobody produces survive unless removed directly
    assert propagate(EDGES, {"300000"}) == {"300000", "500000"}          # 400000 still made by e4
    assert propagate(EDGES, {"100000"}) == {"100000", "300000", "500000"}
    assert propagate(EDGES, {"600000"}) == {"600000", "700000"}
    assert propagate(EDGES, {"800000"}) == {"800000"}

def test_analyze_state_counts_invalid_and_absent(tmp_path):
    mats = {c: {"name": f"m{c}"} for c in ["100000", "200000", "300000", "400000", "500000", "600000", "700000", "800000"]}
    mats["28XX"] = {"name": "bad code"}
    procs = {f"e{i}": {"precursors": [{"hs_code": c} for c in sorted(s)], "products": [{"hs_code": c} for c in sorted(t)]}
             for i, (s, t) in enumerate(EDGES)}
    df = load_trade(_arrow(tmp_path / "t.arrow", TRADE), set(mats))
    rows = analyze_state({"materials": mats, "processes": procs}, dominance(df, 0.6), base="400000",
                         partner_names={1: ("AAA", "Aland"), 3: ("CCC", "Ceeland")})
    by = {r["hs_code"]: r for r in rows}
    assert by["28XX"]["status"] == "invalid" and by["200000"]["status"] == "absent"
    assert by["100000"]["dominated"] == 1 and by["100000"]["top_exporter_iso3"] == "AAA"
    assert by["100000"]["n_dependents"] == 2 and by["100000"]["dependents"] == "300000 500000"
    assert by["100000"]["reach_loss"] == 2            # criticality-style loss from {base} U Pre
    assert by["400000"]["dominated"] == 1 and by["400000"]["dependents"] == "700000"   # e3 needs 400000
    s = summarize("toy", rows)
    assert s["n_codes"] == 9 and s["n_invalid"] == 1 and s["n_absent"] == 5 and s["n_in_comtrade"] == 3
    assert s["n_dominated"] == 2 and s["n_dominated_cascading"] == 2
    assert s["max_code"] == "100000" and s["max_dependents"] == 2 and s["max_supplier_iso3"] == "AAA"
