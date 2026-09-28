#!/usr/bin/env python3
"""Error-mode distribution for judge caches produced by scripts/judge_mekh_processes.py.

Usage:
  python scripts/eval/judge_error_modes.py --out-dir "$DATA" \
      --cache boron:claude "$DATA/judge_boron_claude.jsonl" \
      --cache gallium:claude "$DATA/judge_gallium_claude.jsonl" ...

Writes two files (kept separate so a naive `sum(count)` over one file never
double-counts):
  - judge_error_modes.csv (columns: label,judge,error_mode,count) -- one row
    per (label, judge, error_mode) among that cache's not-correct
    (overall_correct falsy) records.
  - judge_error_modes_pooled.csv (columns: judge,error_mode,count) -- for
    each judge, error_mode counts summed across every label/cache for that
    judge passed in the call.
A missing/null error_mode on a not-correct record is counted as "unspecified".
"""
from __future__ import annotations
import argparse
import collections
import csv
import json
from pathlib import Path


def _rows(path: Path) -> list[dict]:
    out = []
    with open(path) as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def error_mode_counts(path: Path) -> collections.Counter:
    """Counts of error_mode among not-correct (overall_correct falsy) records."""
    counts: collections.Counter = collections.Counter()
    for r in _rows(path):
        if not r.get("overall_correct"):
            counts[r.get("error_mode") or "unspecified"] += 1
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", nargs=2, action="append", metavar=("LABEL:JUDGE", "PATH"), required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args()
    caches = {tuple(lj.split(":", 1)): Path(p) for lj, p in a.cache}

    per_label_rows: list[tuple[str, str, str, int]] = []
    pooled: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for (label, judge), p in sorted(caches.items()):
        counts = error_mode_counts(p)
        pooled[judge].update(counts)
        for mode, n in sorted(counts.items()):
            per_label_rows.append((label, judge, mode, n))

    with open(a.out_dir / "judge_error_modes.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "judge", "error_mode", "count"])
        for label, judge, mode, n in per_label_rows:
            w.writerow([label, judge, mode, n])

    with open(a.out_dir / "judge_error_modes_pooled.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["judge", "error_mode", "count"])
        for judge in sorted(pooled):
            for mode, n in sorted(pooled[judge].items()):
                w.writerow([judge, mode, n])


if __name__ == "__main__":
    main()
