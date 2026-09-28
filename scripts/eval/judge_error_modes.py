#!/usr/bin/env python3
"""Error-mode distribution for judge caches produced by scripts/judge_mekh_processes.py.

Usage:
  python scripts/eval/judge_error_modes.py --out-dir "$DATA" \
      --cache boron:claude "$DATA/judge_boron_claude.jsonl" \
      --cache gallium:claude "$DATA/judge_gallium_claude.jsonl" ...

Writes judge_error_modes.csv with columns label,error_mode,count: one row
per (label, error_mode) among that label's not-correct (overall_correct
falsy) records, plus pooled rows under label "ALL" summing error_mode
counts across every cache passed in the call. A missing/null error_mode on
a not-correct record is counted under "unspecified".
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

    pooled: collections.Counter = collections.Counter()
    rows: list[tuple[str, str, int]] = []
    for (label, _judge), p in sorted(caches.items()):
        counts = error_mode_counts(p)
        pooled.update(counts)
        for mode, n in sorted(counts.items()):
            rows.append((label, mode, n))
    for mode, n in sorted(pooled.items()):
        rows.append(("ALL", mode, n))

    with open(a.out_dir / "judge_error_modes.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "error_mode", "count"])
        for label, mode, n in rows:
            w.writerow([label, mode, n])


if __name__ == "__main__":
    main()
