import json
from pathlib import Path
from scripts.eval.make_latex import macro, pct, build_numbers, mekh_sizes

def test_macro_and_pct():
    assert pct(0.8712) == r"87\%" and macro("JudgeN", "boron", 61) == r"\newcommand{\JudgeNBoron}{61}"

def test_build_numbers_pools_all(tmp_path: Path):
    (tmp_path / "judge_summary.csv").write_text(
        "label,judge,n,overall_correct,precision,ci_lo,ci_hi,plausible_rate,io_rate,hs_rate,inconsistent_count\n"
        "boron,gpt,10,8,0.8,0.5,0.95,0.9,0.9,0.8,0\ngallium,gpt,10,6,0.6,0.3,0.8,0.7,0.7,0.6,1\n")
    (tmp_path / "judge_agreement.csv").write_text("label,n_both,agreement,cohen_kappa\nboron,10,0.9,0.75\n")
    for name, hdr in [("evidence_support.csv", "label,n_processes,n_refs,refs_with_content,frac_refs_with_content,proc_any_mention,proc_fully_grounded,frac_any,frac_full,unresolved_materials\nboron,10,20,15,0.75,9,7,0.9,0.7,0\n"),
                      ("known_route_recall.csv", "label,n_routes,recovered_lenient,recall_lenient,recovered_strict,recall_strict\nboron,8,6,0.75,4,0.5\n"),
                      ("topdown_coverage.csv", "label,mekh_codes,usgs_codes,overlap,mekh_only,frac_mekh_only\nboron,84,5,5,79,0.94\n")]:
        (tmp_path / name).write_text(hdr)
    out = build_numbers(tmp_path)
    assert r"\newcommand{\JudgePrecisionAllGpt}{70\%}" in out and r"\newcommand{\JudgeNAll}{20}" in out
    assert r"\newcommand{\JudgeKappaBoron}{0.75}" in out and r"\newcommand{\RecallStrictBoron}{50\%}" in out
    assert r"\newcommand{\CoverageMekhOnlyBoron}{79}" in out

def test_mekh_sizes(tmp_path: Path):
    state = {"materials": {"m1": {}, "m2": {}, "m3": {}}, "processes": {"p1": {}, "p2": {}}}
    (tmp_path / "research_state.json").write_text(json.dumps(state))
    rows = mekh_sizes([("boron", tmp_path)])
    assert rows == [{"label": "boron", "n_materials": 3, "n_processes": 2}]
