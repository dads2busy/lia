import json
from pathlib import Path
from scripts.eval.make_latex import macro, pct, build_numbers, mekh_sizes, build_size_numbers

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

def test_primary_judge_n_and_warns_on_mismatch(tmp_path: Path, capsys):
    (tmp_path / "judge_summary.csv").write_text(
        "label,judge,n,overall_correct,precision,ci_lo,ci_hi,plausible_rate,io_rate,hs_rate,inconsistent_count\n"
        "boron,claude,61,50,0.82,0.7,0.9,0.9,0.9,0.85,0\n"
        "boron,llama,55,40,0.73,0.6,0.85,0.8,0.8,0.75,0\n"
        "gallium,claude,40,30,0.75,0.6,0.85,0.85,0.85,0.8,0\n"
        "gallium,llama,38,28,0.74,0.6,0.85,0.85,0.85,0.8,0\n")
    out = build_numbers(tmp_path)
    assert r"\newcommand{\JudgeNBoron}{61}" in out  # primary judge (claude) n, not llama's 55
    assert r"\newcommand{\JudgeNAll}{101}" in out  # 61 + 40, primary judge only
    assert r"\newcommand{\JudgeNAllClaude}{101}" in out
    assert r"\newcommand{\JudgeNAllLlama}{93}" in out  # 55 + 38
    assert r"\newcommand{\JudgeNBoronLlama}{55}" in out  # per-judge per-label count still emitted
    err = capsys.readouterr().err
    assert "boron" in err and "gallium" in err  # warning about n disagreement between judges

def test_mekh_sizes_includes_gate_audit(tmp_path: Path):
    materials = {"111111": {}, "222222": {}}
    processes = {
        "p_string": {"precursors": ["bare material string"], "products": [{"hs_code": "111111"}], "process_score": 0.9},
        "p_unknown": {"precursors": [{"hs_code": "Unknown"}], "products": [{"hs_code": "222222"}], "process_score": 0.8},
        "p_missing_material": {"precursors": [{"hs_code": "333333"}], "products": [{"hs_code": "222222"}], "process_score": 0.95},
        "p_unscored": {"precursors": [{"hs_code": "111111"}], "products": [{"hs_code": "222222"}], "process_score": None},
        "p_below_tau": {"precursors": [{"hs_code": "111111"}], "products": [{"hs_code": "222222"}], "process_score": 0.3},
    }
    (tmp_path / "research_state.json").write_text(json.dumps({"materials": materials, "processes": processes}))
    rows = mekh_sizes([("boron", tmp_path)])
    assert rows == [{"label": "boron", "n_materials": 2, "n_processes": 5,
                      "n_unscored": 1, "n_below_tau": 1, "n_untyped_edges": 3}]
    out = build_size_numbers(rows)
    assert r"\newcommand{\MekhUnscoredBoron}{1}" in out and r"\newcommand{\MekhBelowTauBoron}{1}" in out
    assert r"\newcommand{\MekhUntypedEdgesBoron}{3}" in out
    assert r"\newcommand{\MekhUnscoredFracBoron}{20\%}" in out
    assert r"\newcommand{\MekhUntypedEdgesFracBoron}{60\%}" in out
    assert r"\newcommand{\MekhProcessesAll}{5}" in out
    assert r"\newcommand{\MekhUnscoredAll}{1}" in out and r"\newcommand{\MekhUntypedEdgesAll}{3}" in out
