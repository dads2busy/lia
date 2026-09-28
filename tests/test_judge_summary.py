import json
from pathlib import Path
from scripts.eval.judge_summary import summarize_cache, cohen_kappa, bootstrap_ci

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
