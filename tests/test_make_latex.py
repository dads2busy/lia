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
    # 2 registered materials; classes: (i) truly untyped -- bare string / missing
    # or malformed hs_code; (ii) unregistered -- valid 6-digit code, not a
    # known material. p_both exercises a process landing in BOTH classes.
    materials = {"111111": {}, "222222": {}}
    processes = {
        "p_string": {"precursors": ["bare material string"], "products": [{"hs_code": "111111"}], "process_score": 0.9},  # untyped only
        "p_unknown": {"precursors": [{"hs_code": "Unknown"}], "products": [{"hs_code": "222222"}], "process_score": 0.8},  # untyped only
        "p_missing_material": {"precursors": [{"hs_code": "333333"}], "products": [{"hs_code": "222222"}], "process_score": 0.95},  # unregistered only
        "p_both": {"precursors": [{"hs_code": "444444"}], "products": ["byproduct string", {"hs_code": "111111"}], "process_score": 0.85},  # untyped AND unregistered
        "p_unscored": {"precursors": [{"hs_code": "111111"}], "products": [{"hs_code": "222222"}], "process_score": None},  # neither
        "p_below_tau": {"precursors": [{"hs_code": "111111"}], "products": [{"hs_code": "222222"}], "process_score": 0.3},  # neither
    }
    (tmp_path / "research_state.json").write_text(json.dumps({"materials": materials, "processes": processes}))
    rows = mekh_sizes([("boron", tmp_path)])
    assert rows == [{"label": "boron", "n_materials": 2, "n_processes": 6,
                      "n_unscored": 1, "n_below_tau": 1, "n_untyped_edges": 3, "n_unregistered_edges": 2}]
    out = build_size_numbers(rows)
    assert r"\newcommand{\MekhUnscoredBoron}{1}" in out and r"\newcommand{\MekhBelowTauBoron}{1}" in out
    assert r"\newcommand{\MekhUntypedEdgesBoron}{3}" in out  # p_string, p_unknown, p_both
    assert r"\newcommand{\MekhUnregisteredEdgesBoron}{2}" in out  # p_missing_material, p_both
    assert r"\newcommand{\MekhUnscoredFracBoron}{17\%}" in out
    assert r"\newcommand{\MekhUntypedEdgesFracBoron}{50\%}" in out
    assert r"\newcommand{\MekhUnregisteredEdgesFracBoron}{33\%}" in out
    assert r"\newcommand{\MekhProcessesAll}{6}" in out
    assert r"\newcommand{\MekhUnscoredAll}{1}" in out and r"\newcommand{\MekhUntypedEdgesAll}{3}" in out
    assert r"\newcommand{\MekhUnregisteredEdgesAll}{2}" in out

def _write_new_inputs(d: Path):
    (d / "criticality_summary.csv").write_text(
        "label,base_code,base_name,reach,n_pre,n_vertices,n_invalid_material_keys,n_edges,n_processes,n_processes_no_target,"
        "n_processes_no_source,n_entries_untyped,n_entries_unregistered,n_tied_with_third,"
        "top1_code,top1_name,top1_criticality,top2_code,top2_name,top2_criticality,top3_code,top3_name,top3_criticality\n"
        "boron,280450,Elemental boron,73,1,74,0,127,129,2,31,61,65,2,"
        "280700,Sulfuric acid,14,220190,Raw water & ice,10,252800,Natural borates,10\n")
    (d / "rank_stability.csv").write_text(
        "n_runs,base,p,k,samples,seed,borda_rbo_mean,borda_rbo_sd,borda_rbo_sd_pop,borda_rbo_min,borda_rbo_max,"
        "borda_topk_overlap_mean,borda_topk_overlap_sd,borda_topk_jaccard_mean,borda_topk_codes,critsum_rbo_mean,"
        "critsum_rbo_sd,critsum_rbo_sd_pop,critsum_rbo_min,critsum_rbo_max,critsum_topk_overlap_mean,critsum_topk_overlap_sd,"
        "critsum_topk_jaccard_mean,n_pairs,pairwise_rbo_mean,pairwise_rbo_sd,pairwise_rbo_sd_pop,pairwise_rbo_min,"
        "pairwise_rbo_max,pairwise_topk_overlap_mean,pairwise_topk_overlap_sd\n"
        "7,280450,0.98,10,1000,0,0.5721,0.0311,0.0288,0.5179,0.624,5.0167,1.03,0.3412,281000 284019,0.6044,0.0376,"
        "0.0348,0.5389,0.6613,4.99,1.49,0.34,21,0.4218,0.0628,0.0613,0.30,0.55,3.2921,1.1\n")
    (d / "criticality_summary_nosourceless.csv").write_text(
        "label,base_code,base_name,reach,n_pre,top1_code,top1_name,top1_criticality\n"
        "boron,280450,Elemental boron,40,20,252800,Natural borates,12\n")
    (d / "disruption_summary.csv").write_text(
        "label,n_codes,n_invalid,n_absent,n_in_comtrade,n_dominated,frac_dominated,n_dominated_cascading,n_dominated_local,"
        "total_dependents,max_code,max_name,max_supplier_iso3,max_supplier_name,max_share,max_dependents,max_dependents_frac,"
        "dominated_codes,threshold\n"
        "boron,74,0,2,72,4,0.0556,1,3,8,284019,Disodium tetraborate,TUR,Türkiye,0.7243,8,0.1096,x,0.6\n")
    (d / "disruption_boron.csv").write_text(
        "hs_code,name,status,total_exports,top_exporter_code,top_exporter_iso3,top_exporter_name,top_share,dominated,"
        "n_dependents,dependents,dependents_frac,reach_loss\n"
        "284019,Disodium tetraborate,ok,1.0,792,TUR,Türkiye,0.7243,1,8,281000 284011,0.1096,9\n"
        "280450,Elemental boron,ok,1.0,392,JPN,Japan,0.3,0,,,,\n")

def test_new_result_macros(tmp_path: Path):
    _write_new_inputs(tmp_path)
    out = build_numbers(tmp_path)
    for m in [r"\newcommand{\CritBaseCodeBoron}{280450}", r"\newcommand{\CritReachBoron}{73}",
              r"\newcommand{\CritTopNameBoron}{Sulfuric acid}", r"\newcommand{\CritTopCodeBoron}{280700}",
              r"\newcommand{\CritTopBoron}{14}", r"\newcommand{\CritSecondNameBoron}{Raw water \& ice}",
              r"\newcommand{\CritThirdBoron}{10}",
              r"\newcommand{\RboMean}{0.572}", r"\newcommand{\RboSd}{0.031}", r"\newcommand{\RboSdPop}{0.029}",
              r"\newcommand{\RboRuns}{7}", r"\newcommand{\RboPairwiseSd}{0.063}", r"\newcommand{\RboPairs}{21}",
              r"\newcommand{\RboSensitivityCritsumMean}{0.604}", r"\newcommand{\RboSensitivityCritsumSd}{0.038}",
              r"\newcommand{\CritReachNoSourcelessBoron}{40}", r"\newcommand{\CritPreNoSourcelessBoron}{20}",
              r"\newcommand{\CritTopNameNoSourcelessBoron}{Natural borates}",
              r"\newcommand{\CritTopCodeNoSourcelessBoron}{252800}", r"\newcommand{\CritTopNoSourcelessBoron}{12}",
              r"\newcommand{\RboPersistence}{0.98}", r"\newcommand{\RboTopTenOverlap}{5.0}",
              r"\newcommand{\RboTopTenJaccard}{34\%}", r"\newcommand{\RboPairwiseMean}{0.422}",
              r"\newcommand{\DisruptThreshold}{60\%}", r"\newcommand{\DisruptDominatedBoron}{4}",
              r"\newcommand{\DisruptInComtradeBoron}{72}", r"\newcommand{\DisruptAbsentBoron}{2}",
              r"\newcommand{\DisruptCascadingBoron}{1}", r"\newcommand{\DisruptMaxCodeBoron}{284019}",
              r"\newcommand{\DisruptMaxSupplierBoron}{Türkiye}", r"\newcommand{\DisruptMaxShareBoron}{72\%}",
              r"\newcommand{\DisruptMaxDependentsBoron}{8}", r"\newcommand{\DisruptMaxDependentsFracBoron}{11\%}"]:
        assert m in out, m
    names = [l.split("}{")[0][len("\\newcommand{\\"):] for l in out.splitlines() if l.startswith("\\newcommand")]
    assert all(n.isalpha() for n in names)
    assert "RboCritsumMean" not in names   # critsum only under an explicit sensitivity name
    assert "ddof=1" in out and "strictly below" in out   # comments make the headline definitions explicit

def test_new_tables_are_wrapped_in_macros(tmp_path: Path):
    from scripts.eval.make_latex import build_tables
    _write_new_inputs(tmp_path)
    t = build_tables(tmp_path)
    assert r"\newcommand{\CriticalityTable}{" in t and r"\label{table:criticality}" in t
    assert r"\textbf{Elemental boron [280450]} & \textbf{73} \\" in t and r"Raw water \& ice [220190] & 10 \\" in t
    assert r"\newcommand{\DisruptionTable}{" in t and r"\label{table:disruption}" in t
    assert "Disodium tetraborate [284019] & Türkiye & 72\\% &  & 8 \\\\"  # reporters column empty in this fixture in t and "280450" not in t.split("DisruptionTable")[1]

def test_followup_macros_coverage_inclunreg_halfweight_sourceless(tmp_path: Path):
    from scripts.eval.make_latex import build_tables
    _write_new_inputs(tmp_path)
    cs = tmp_path / "criticality_summary.csv"; lines = cs.read_text().splitlines()
    cs.write_text(lines[0] + ",n_sourceless_untyped,n_sourceless_unregistered,n_sourceless_empty\n" + lines[1] + ",20,9,2\n")
    rs = tmp_path / "rank_stability.csv"; lines = rs.read_text().splitlines()
    rs.write_text(lines[0] + ",half_weight_depth\n" + lines[1] + ",14\n")
    ds = tmp_path / "disruption_summary.csv"; lines = ds.read_text().splitlines()
    ds.write_text(lines[0] + ",n_reporters_total\n" + lines[1] + ",151\n")
    db = tmp_path / "disruption_boron.csv"; lines = db.read_text().splitlines()
    db.write_text("\n".join([lines[0] + ",n_reporters"] + [l + ",37" for l in lines[1:]]) + "\n")
    (tmp_path / "disruption_summary_inclunreg.csv").write_text(
        ds.read_text().replace("boron,74,0,2,72,4,0.0556,1,3,", "boron,74,0,2,72,3,0.0417,2,1,"))
    (tmp_path / "disruption_boron_inclunreg.csv").write_text(
        "hs_code,name,status,total_exports,top_exporter_code,top_exporter_iso3,top_exporter_name,top_share,dominated,"
        "n_reporters,n_dependents,dependents,dependents_frac,reach_loss\n"
        "284019,Disodium tetraborate,ok,1,792,TUR,Türkiye,0.70,1,37,9,a,0.1,9\n"
        "284520,Refined boron,ok,1,392,JPN,Japan,0.69,1,12,3,b,0.03,1\n"
        "280511,Sodium metal,ok,1,251,FRA,France,0.65,1,20,0,,0,1\n")
    out = build_numbers(tmp_path)
    for m in [r"\newcommand{\DisruptReporters}{151}", r"\newcommand{\RboHalfWeightDepth}{14}",
              r"\newcommand{\CritSourcelessUntypedBoron}{20}", r"\newcommand{\CritSourcelessUnregisteredBoron}{9}",
              r"\newcommand{\CritSourcelessEmptyBoron}{2}",
              r"\newcommand{\DisruptCascadingInclUnregBoron}{2}", r"\newcommand{\DisruptDominatedInclUnregBoron}{3}",
              r"\newcommand{\DisruptCascadeFirstCodeInclUnregBoron}{284019}",
              r"\newcommand{\DisruptCascadeFirstNameInclUnregBoron}{Disodium tetraborate}",
              r"\newcommand{\DisruptCascadeFirstDependentsInclUnregBoron}{9}",
              r"\newcommand{\DisruptCascadeSecondCodeInclUnregBoron}{284520}",
              r"\newcommand{\DisruptCascadeListInclUnregBoron}{Disodium tetraborate [284019] (9), Refined boron [284520] (3)}",
              r"\newcommand{\DisruptCascadeListBoron}{Disodium tetraborate [284019] (8)}"]:
        assert m in out, m
    names = [l.split("}{")[0][len("\\newcommand{\\"):] for l in out.splitlines() if l.startswith("\\newcommand")]
    assert all(n.isalpha() for n in names) and len(names) == len(set(names))
    t = build_tables(tmp_path)
    assert "Share & Reporters & Dependents" in t and "& 72\\% & 37 & 8 \\\\" in t
