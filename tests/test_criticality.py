import json
from pathlib import Path
from scripts.eval.criticality import (build_hypergraph, precursor_set, reachable, criticality,
                                      ranked, top_k, run_folder)

# Tiny hand-made MEKH (all codes registered):
#   e1: {100000 ore, 200000 reagent} -> {300000 intermediate}
#   e2: {300000}                     -> {400000 metal, 500000 byproduct}
#   e3: {400000, 600000 reagent2}    -> {700000 alloy}
#   e4: {800000 other ore}           -> {400000}          (alternative route to the metal)
# Pre = {100000, 200000, 600000, 800000}; with base = 400000 the start set is Pre + {400000}.
# R(start) = {300000, 400000, 500000, 700000} -> |R| = 4.
EDGES = [(frozenset({"100000", "200000"}), frozenset({"300000"})),
         (frozenset({"300000"}), frozenset({"400000", "500000"})),
         (frozenset({"400000", "600000"}), frozenset({"700000"})),
         (frozenset({"800000"}), frozenset({"400000"}))]
VERTS = {"100000", "200000", "300000", "400000", "500000", "600000", "700000", "800000", "900000"}

def test_precursor_set():
    assert precursor_set(EDGES) == {"100000", "200000", "600000", "800000"}

def test_reachable_fixpoint_and_removal():
    start = {"100000", "200000", "600000", "800000", "400000"}
    assert reachable(EDGES, start) == {"300000", "400000", "500000", "700000"}
    # removing 300000 blocks e2 but 400000 is still made by e4 (and is in start), so 700000 survives
    assert reachable(EDGES, start - {"300000"}, removed={"300000"}) == {"400000", "700000"}
    # a hyperedge fires only when ALL its sources are available
    assert reachable(EDGES, {"100000"}) == set()

def test_criticality_definition():
    c, reach = criticality(VERTS, EDGES, base="400000")
    assert reach == 4 and "400000" not in c
    # removing ore 100000 kills e1 -> 300000, 500000 lost (400000 in start; 700000 via start 400000)
    assert c["100000"] == 2 and c["200000"] == 2
    assert c["300000"] == 2          # itself + 500000
    assert c["600000"] == 1          # 700000
    assert c["700000"] == 1 and c["500000"] == 1   # only themselves
    assert c["800000"] == 0          # alternative route; 400000 is in the start set anyway
    assert c["900000"] == 0          # isolated registered vertex
    r = ranked(c)
    assert [x[0] for x in r][:4] == ["100000", "200000", "300000", "500000"]  # ties broken by code
    assert top_k(c, 3) == [("100000", 2), ("200000", 2), ("300000", 2)]

def test_build_hypergraph_drops_untyped_and_unregistered():
    state = {"materials": {"100000": {"name": "Ore"}, "300000": {"name": "Int"}, "12AB": {"name": "bad key"}},
             "processes": {
                 "p1": {"precursors": [{"hs_code": "100000"}, "water", {"hs_code": "999999"}, {"hs_code": "Unknown"}],
                        "products": [{"hs_code": "300000"}, "slag"]},
                 "p2": {"precursors": ["air"], "products": ["heat"]}}}
    verts, edges, audit = build_hypergraph(state)
    assert verts == {"100000", "300000"}
    assert edges == [(frozenset({"100000"}), frozenset({"300000"}))]
    assert audit == {"n_vertices": 2, "n_invalid_material_keys": 1, "n_edges": 1, "n_processes": 2,
                     "n_processes_no_target": 1, "n_processes_no_source": 0,
                     "n_entries_untyped": 5, "n_entries_unregistered": 1,
                     "n_sourceless_untyped": 0, "n_sourceless_unregistered": 0, "n_sourceless_empty": 0}
    verts2, edges2, _ = build_hypergraph(state, include_unregistered=True)
    assert "999999" in verts2 and edges2[0][0] == frozenset({"100000", "999999"})

def test_run_folder_writes_ranked_csv(tmp_path: Path):
    state = {"materials": {"100000": {"name": "Ore"}, "300000": {"name": "Int"}, "400000": {"name": "Metal"}},
             "processes": {"p1": {"precursors": [{"hs_code": "100000"}], "products": [{"hs_code": "300000"}]},
                           "p2": {"precursors": [{"hs_code": "300000"}], "products": [{"hs_code": "400000"}]}}}
    (tmp_path / "research_state.json").write_text(json.dumps(state))
    summary, rows = run_folder("toy", tmp_path, base="400000", out_dir=tmp_path)
    assert summary["reach"] == 2 and summary["top1_code"] in {"100000", "300000"} and summary["top1_criticality"] == 2
    text = (tmp_path / "criticality_toy.csv").read_text().splitlines()
    assert text[0].startswith("rank,hs_code,name,criticality")
    assert text[1].split(",")[3] == "2"

def test_drop_sourceless_variant():
    # p_mine has only untyped inputs: under the literal rule its empty source set is vacuously
    # satisfied and it fires; with drop_sourceless it is removed, so its ore becomes a precursor.
    state = {"materials": {"100000": {"name": "Ore"}, "300000": {"name": "Int"}, "400000": {"name": "Metal"}},
             "processes": {"p_mine": {"precursors": ["rock"], "products": [{"hs_code": "100000"}]},
                           "p1": {"precursors": [{"hs_code": "100000"}], "products": [{"hs_code": "300000"}]},
                           "p2": {"precursors": [{"hs_code": "300000"}], "products": [{"hs_code": "400000"}]}}}
    v, e, a = build_hypergraph(state)
    assert len(e) == 3 and a["n_processes_no_source"] == 1
    c, r = criticality(v, e, "400000")
    assert r == 3 and c["100000"] == 3 and precursor_set(e) == set()
    v2, e2, a2 = build_hypergraph(state, drop_sourceless=True)
    assert len(e2) == 2 and a2["n_processes_no_source"] == 1 and a2["n_edges"] == 2
    c2, r2 = criticality(v2, e2, "400000")
    assert precursor_set(e2) == {"100000"} and r2 == 2 and c2["100000"] == 2

def test_sourceless_breakdown():
    state = {"materials": {"100000": {"name": "Ore"}, "300000": {"name": "Int"}},
             "processes": {
                 "p_untyped": {"precursors": ["rock", {"hs_code": "Unknown"}], "products": [{"hs_code": "100000"}]},
                 "p_unreg": {"precursors": ["air", {"hs_code": "999999"}], "products": [{"hs_code": "100000"}]},
                 "p_empty": {"precursors": [], "products": [{"hs_code": "300000"}]},
                 "p_none": {"products": [{"hs_code": "300000"}]},
                 "p_ok": {"precursors": [{"hs_code": "100000"}], "products": [{"hs_code": "300000"}]},
                 "p_notarget": {"precursors": ["x"], "products": ["y"]}}}
    _, _, a = build_hypergraph(state)
    assert a["n_processes_no_source"] == 4
    assert (a["n_sourceless_untyped"], a["n_sourceless_unregistered"], a["n_sourceless_empty"]) == (1, 1, 2)
