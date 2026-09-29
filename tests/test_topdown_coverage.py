import json
from pathlib import Path
from scripts.eval.topdown_coverage import mekh_codes, coverage

def test_mekh_codes_counts_participation(tmp_path):
    state = {"materials": {"252800": {"name": "Borax"}, "281000": {"name": "Boric acid"}, "999999": {"name": "Orphan"}},
             "processes": {"p": {"precursors": [{"hs_code": "252800"}], "products": [{"hs_code": "281000"}]},
                           "q": {"precursors": [{"hs_code": "281000"}], "products": [{"hs_code": "281000"}]}}}
    (tmp_path / "research_state.json").write_text(json.dumps(state))
    codes = mekh_codes(tmp_path)
    assert codes["281000"] == ("Boric acid", 2) and codes["252800"] == ("Borax", 1) and codes["999999"] == ("Orphan", 0)

def test_coverage():
    codes = {"252800": ("Borax", 1), "281000": ("Boric acid", 2), "280450": ("Boron", 1)}
    s, ex = coverage(codes, {"252800", "281000", "284019"})
    assert s == {"mekh_codes": 3, "usgs_codes": 3, "overlap": 2, "mekh_only": 1, "frac_mekh_only": 1/3}
    assert ex == [("280450", "Boron", 1)]

def test_mekh_codes_ignores_non_six_digit_material_keys(tmp_path):
    state = {"materials": {"252800": {"name": "Borax"}, "UNCLASSIFIED": {"name": "misc"}}, "processes": {}}
    (tmp_path / "research_state.json").write_text(json.dumps(state))
    assert set(mekh_codes(tmp_path)) == {"252800"}
