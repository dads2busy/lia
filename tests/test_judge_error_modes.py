import collections
import csv
import json
from pathlib import Path

from scripts.eval.judge_error_modes import error_mode_counts, main as judge_error_modes_main


def _write(p: Path, rows):
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_error_mode_counts_only_counts_not_correct(tmp_path):
    p = tmp_path / "a.jsonl"
    _write(p, [
        {"key": "k1", "overall_correct": True, "error_mode": None},
        {"key": "k2", "overall_correct": False, "error_mode": "hs_code_mismatch"},
        {"key": "k3", "overall_correct": False, "error_mode": "hs_code_mismatch"},
        {"key": "k4", "overall_correct": False, "error_mode": None},  # missing -> "unspecified"
    ])
    counts = error_mode_counts(p)
    assert counts == {"hs_code_mismatch": 2, "unspecified": 1}


def test_main_writes_per_label_file_and_separate_pooled_file(tmp_path, monkeypatch):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    _write(a, [
        {"key": "k1", "overall_correct": False, "error_mode": "hs_code_mismatch"},
        {"key": "k2", "overall_correct": True, "error_mode": None},
    ])
    _write(b, [
        {"key": "k1", "overall_correct": False, "error_mode": "hs_code_mismatch"},
        {"key": "k2", "overall_correct": False, "error_mode": "hallucinated_process"},
    ])
    monkeypatch.setattr(
        "sys.argv",
        [
            "judge_error_modes.py",
            "--cache", "boron:claude", str(a),
            "--cache", "gallium:claude", str(b),
            "--out-dir", str(tmp_path),
        ],
    )
    judge_error_modes_main()

    with open(tmp_path / "judge_error_modes.csv") as f:
        per_label = list(csv.DictReader(f))
    with open(tmp_path / "judge_error_modes_pooled.csv") as f:
        pooled = list(csv.DictReader(f))

    # Per-label file has a `judge` column and no "ALL" pseudo-label mixed in
    # with real labels (that was the bug: double-counting when a naive
    # consumer summed this file's `count` column).
    assert {r["label"] for r in per_label} == {"boron", "gallium"}
    assert all(r["judge"] == "claude" for r in per_label)

    by_label = {(r["label"], r["error_mode"]): int(r["count"]) for r in per_label}
    assert by_label[("boron", "hs_code_mismatch")] == 1
    assert by_label[("gallium", "hs_code_mismatch")] == 1
    assert by_label[("gallium", "hallucinated_process")] == 1

    # Pooled file is separate, keyed by judge (not label).
    assert {r["judge"] for r in pooled} == {"claude"}
    by_pooled = {r["error_mode"]: int(r["count"]) for r in pooled}
    assert by_pooled["hs_code_mismatch"] == 2
    assert by_pooled["hallucinated_process"] == 1

    # Per-label counts (for a given judge) must sum to that judge's pooled
    # counts -- this is exactly the invariant a double-counting bug breaks.
    per_label_sum: collections.Counter = collections.Counter()
    for r in per_label:
        per_label_sum[(r["judge"], r["error_mode"])] += int(r["count"])
    for r in pooled:
        assert per_label_sum[(r["judge"], r["error_mode"])] == int(r["count"])
    assert sum(int(r["count"]) for r in per_label) == sum(int(r["count"]) for r in pooled)
