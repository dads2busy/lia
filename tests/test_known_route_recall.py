import json, csv
from pathlib import Path
from scripts.eval.known_route_recall import load_routes, process_hs_sets, recall_for

def test_load_routes_rejects_non_six_digit(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("base_material,route_id,description,input_hs,output_hs,source\nboron,B1,x,2528,284019,\nboron,B2,y,252800,284019,\n")
    routes, rejected = load_routes(p)
    assert [r["route_id"] for r in routes] == ["B2"] and rejected == ["B1"]

def test_recall_lenient_and_strict():
    procs = [({"252800", "280700"}, {"284019"})]
    routes = [{"route_id": "R1", "inputs": {"252800"}, "outputs": {"284019"}},          # strict hit
              {"route_id": "R2", "inputs": {"252800", "999999"}, "outputs": {"284019"}},# lenient only
              {"route_id": "R3", "inputs": {"111111"}, "outputs": {"284019"}}]         # miss
    s, detail = recall_for(routes, procs)
    assert s["recovered_lenient"] == 2 and s["recovered_strict"] == 1
    assert detail["R2"] == "lenient" and detail["R3"] == "miss"

def test_process_hs_sets(tmp_path):
    state = {"materials": {}, "processes": {"p": {"precursors": [{"hs_code": "252800"}, "bare"], "products": [{"hs_code": "284019"}]}}}
    (tmp_path / "research_state.json").write_text(json.dumps(state))
    assert process_hs_sets(tmp_path) == [({"252800"}, {"284019"})]
