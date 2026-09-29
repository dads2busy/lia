import csv
import json
from pathlib import Path
from scripts.eval.judge_summary import (
    summarize_cache, cohen_kappa, bootstrap_ci, pooled_cohen_kappa,
    criterion_kappa, CRITERIA, main as judge_summary_main,
)

def _write(p: Path, rows):
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

def test_summarize_and_kappa(tmp_path):
    a = tmp_path / "a.jsonl"; b = tmp_path / "b.jsonl"
    base = {"process_plausible": True, "inputs_outputs_correct": True, "hs_codes_correct": True, "rationale": ""}
    _write(a, [{"key": "k1", "overall_correct": True, **base},
               {"key": "k2", "overall_correct": False, **base, "rationale": "All criteria are met."},
               {"key": "k3", "overall_correct": True, **base}])
    _write(b, [{"key": "k1", "overall_correct": True, **base},
               {"key": "k2", "overall_correct": True, **base},
               {"key": "k3", "overall_correct": False, **base}])
    s = summarize_cache(a)
    assert s["n"] == 3 and abs(s["precision"] - 2/3) < 1e-9
    assert s["inconsistent_count"] == 1          # k2: rationale says met, verdict false
    lo, hi = bootstrap_ci([1, 0, 1], seed=0)
    assert 0.0 <= lo <= 2/3 <= hi <= 1.0
    agree, kappa = cohen_kappa(a, b)
    assert abs(agree - 1/3) < 1e-9


def test_structural_inconsistency_all_true_but_overall_false(tmp_path):
    # All three sub-criteria true but overall_correct false, with a
    # rationale that does NOT match the regex -- the regex alone would miss
    # this, but it's structurally inconsistent (all-true implies overall
    # should be true) and must be flagged.
    p = tmp_path / "a.jsonl"
    _write(p, [
        {"key": "k1", "process_plausible": True, "inputs_outputs_correct": True,
         "hs_codes_correct": True, "overall_correct": False,
         "rationale": "Some unrelated wording that does not match the regex."},
    ])
    s = summarize_cache(p)
    assert s["inconsistent_count"] == 1


def test_structural_inconsistency_overall_true_but_a_criterion_false(tmp_path):
    # Reverse case: overall_correct true despite a false sub-criterion.
    p = tmp_path / "a.jsonl"
    _write(p, [
        {"key": "k1", "process_plausible": True, "inputs_outputs_correct": True,
         "hs_codes_correct": False, "overall_correct": True, "rationale": "Fine."},
    ])
    s = summarize_cache(p)
    assert s["inconsistent_count"] == 1


def test_consistent_records_not_flagged(tmp_path):
    p = tmp_path / "a.jsonl"
    _write(p, [
        # Normal correct record: all true, overall true.
        {"key": "k1", "process_plausible": True, "inputs_outputs_correct": True,
         "hs_codes_correct": True, "overall_correct": True, "rationale": "Fine."},
        # Normal incorrect record: one criterion false, overall false, no
        # rationale-regex match.
        {"key": "k2", "process_plausible": True, "inputs_outputs_correct": True,
         "hs_codes_correct": False, "overall_correct": False, "rationale": "HS code is wrong."},
    ])
    s = summarize_cache(p)
    assert s["inconsistent_count"] == 0


def test_pooled_cohen_kappa_matches_manual_concatenation(tmp_path):
    # Two "labels" (e.g. MEKHs), each with a judge-A and judge-B cache.
    # pooled_cohen_kappa concatenates all matched-key records across both
    # labels before computing kappa/agreement, rather than averaging the
    # per-label kappas.
    base = {"process_plausible": True, "inputs_outputs_correct": True, "hs_codes_correct": True, "rationale": ""}
    a1, b1 = tmp_path / "a1.jsonl", tmp_path / "b1.jsonl"
    a2, b2 = tmp_path / "a2.jsonl", tmp_path / "b2.jsonl"
    _write(a1, [{"key": "k1", "overall_correct": True, **base}, {"key": "k2", "overall_correct": False, **base}])
    _write(b1, [{"key": "k1", "overall_correct": True, **base}, {"key": "k2", "overall_correct": True, **base}])
    _write(a2, [{"key": "k3", "overall_correct": True, **base}, {"key": "k4", "overall_correct": True, **base}])
    _write(b2, [{"key": "k3", "overall_correct": True, **base}, {"key": "k4", "overall_correct": False, **base}])

    n, po, kappa = pooled_cohen_kappa([(a1, b1), (a2, b2)])
    assert n == 4
    # Manual: matches on k1, k3 (2/4 agree) -> po = 0.5
    assert abs(po - 0.5) < 1e-9
    # pa = fraction of True in [T,F,T,T] = 3/4; pb = fraction True in [T,T,T,F] = 3/4
    pa = pb = 3 / 4
    pe = pa * pb + (1 - pa) * (1 - pb)
    expected_kappa = (po - pe) / (1 - pe)
    assert abs(kappa - expected_kappa) < 1e-9


def test_pooled_cohen_kappa_empty_pairs_returns_zero():
    assert pooled_cohen_kappa([]) == (0, 0.0, 0.0)


def test_criterion_kappa_matches_pooled_cohen_kappa_for_overall_correct(tmp_path):
    # criterion_kappa(pairs, "overall_correct") must be identical to
    # pooled_cohen_kappa(pairs) -- the latter is now a thin wrapper.
    base = {"process_plausible": True, "inputs_outputs_correct": True, "hs_codes_correct": True, "rationale": ""}
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _write(a, [{"key": "k1", "overall_correct": True, **base}, {"key": "k2", "overall_correct": False, **base}])
    _write(b, [{"key": "k1", "overall_correct": True, **base}, {"key": "k2", "overall_correct": True, **base}])
    assert criterion_kappa([(a, b)], "overall_correct") == pooled_cohen_kappa([(a, b)])


def test_criterion_kappa_on_hs_codes_correct(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    base = {"process_plausible": True, "inputs_outputs_correct": True, "overall_correct": True, "rationale": ""}
    _write(a, [{"key": "k1", "hs_codes_correct": True, **base},
               {"key": "k2", "hs_codes_correct": False, **base}])
    _write(b, [{"key": "k1", "hs_codes_correct": False, **base},
               {"key": "k2", "hs_codes_correct": False, **base}])
    n, po, kappa = criterion_kappa([(a, b)], "hs_codes_correct")
    assert n == 2
    assert abs(po - 0.5) < 1e-9  # agree on k2 only


def test_main_writes_judge_agreement_criteria_csvs(tmp_path, monkeypatch):
    base = {"process_plausible": True, "inputs_outputs_correct": True, "hs_codes_correct": True, "rationale": ""}
    a1, b1 = tmp_path / "a1.jsonl", tmp_path / "b1.jsonl"
    a2, b2 = tmp_path / "a2.jsonl", tmp_path / "b2.jsonl"
    _write(a1, [{"key": "k1", "overall_correct": True, **base}])
    _write(b1, [{"key": "k1", "overall_correct": True, **base}])
    _write(a2, [{"key": "k2", "overall_correct": False, **{**base, "hs_codes_correct": False}}])
    _write(b2, [{"key": "k2", "overall_correct": True, **base}])

    monkeypatch.setattr("sys.argv", [
        "judge_summary.py",
        "--cache", "boron:claude", str(a1), "--cache", "boron:llama", str(b1),
        "--cache", "gallium:claude", str(a2), "--cache", "gallium:llama", str(b2),
        "--out-dir", str(tmp_path),
    ])
    judge_summary_main()

    with open(tmp_path / "judge_agreement_criteria.csv") as f:
        per_label = list(csv.DictReader(f))
    with open(tmp_path / "judge_agreement_criteria_pooled.csv") as f:
        pooled = list(csv.DictReader(f))

    assert {r["label"] for r in per_label} == {"boron", "gallium"}
    assert {r["criterion"] for r in per_label} == set(CRITERIA)
    assert len(per_label) == 2 * len(CRITERIA)

    # Pooled file has no "label" column, one row per criterion.
    assert "label" not in pooled[0]
    assert {r["criterion"] for r in pooled} == set(CRITERIA)
    pooled_overall = [r for r in pooled if r["criterion"] == "overall_correct"][0]
    assert int(pooled_overall["n_both"]) == 2
