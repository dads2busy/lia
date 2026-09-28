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


def test_main_writes_per_label_and_pooled_rows(tmp_path, monkeypatch):
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
        rows = list(csv.DictReader(f))

    by_label = {(r["label"], r["error_mode"]): int(r["count"]) for r in rows}
    assert by_label[("boron", "hs_code_mismatch")] == 1
    assert by_label[("gallium", "hs_code_mismatch")] == 1
    assert by_label[("gallium", "hallucinated_process")] == 1
    assert by_label[("ALL", "hs_code_mismatch")] == 2
    assert by_label[("ALL", "hallucinated_process")] == 1
