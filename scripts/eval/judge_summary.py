#!/usr/bin/env python3
"""Summarize judge caches produced by scripts/judge_mekh_processes.py.

Usage:
  python scripts/eval/judge_summary.py --out-dir "$DATA" \
      --cache boron:gpt "$DATA/judge_boron_gpt.jsonl" \
      --cache boron:claude "$DATA/judge_boron_claude.jsonl" ...
Writes judge_summary.csv, judge_agreement.csv, judge_summary.md.
"""
from __future__ import annotations
import argparse, csv, json, random, re
from pathlib import Path

INCONSISTENT = re.compile(r"(should be true|all criteria are met|overall_correct should be true)", re.I)

def _rows(path: Path) -> dict[str, dict]:
    out = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                r = json.loads(line); out[r["key"]] = r
    return out

def bootstrap_ci(bits: list[int], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed); n = len(bits)
    if n == 0: return (0.0, 0.0)
    means = sorted(sum(rng.choice(bits) for _ in range(n)) / n for _ in range(n_boot))
    return (means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1])

def summarize_cache(path: Path) -> dict:
    rows = list(_rows(path).values())
    bits = [1 if r.get("overall_correct") else 0 for r in rows]
    lo, hi = bootstrap_ci(bits)
    rate = lambda k: (sum(1 for r in rows if r.get(k)) / len(rows)) if rows else 0.0
    return {"n": len(rows), "overall_correct": sum(bits),
            "precision": (sum(bits) / len(bits)) if bits else 0.0, "ci_lo": lo, "ci_hi": hi,
            "plausible_rate": rate("process_plausible"), "io_rate": rate("inputs_outputs_correct"),
            "hs_rate": rate("hs_codes_correct"),
            "inconsistent_count": sum(1 for r in rows if not r.get("overall_correct")
                                      and INCONSISTENT.search(r.get("rationale", "") or ""))}

def cohen_kappa(a: Path, b: Path) -> tuple[float, float]:
    ra, rb = _rows(a), _rows(b); keys = sorted(set(ra) & set(rb))
    if not keys: return (0.0, 0.0)
    xa = [bool(ra[k].get("overall_correct")) for k in keys]
    xb = [bool(rb[k].get("overall_correct")) for k in keys]
    n = len(keys); po = sum(1 for i in range(n) if xa[i] == xb[i]) / n
    pa, pb = sum(xa) / n, sum(xb) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    kappa = 0.0 if pe == 1 else (po - pe) / (1 - pe)
    return (po, kappa)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", nargs=2, action="append", metavar=("LABEL:JUDGE", "PATH"), required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args()
    caches = {tuple(lj.split(":", 1)): Path(p) for lj, p in a.cache}
    with open(a.out_dir / "judge_summary.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["label", "judge", "n", "overall_correct", "precision", "ci_lo", "ci_hi",
                                       "plausible_rate", "io_rate", "hs_rate", "inconsistent_count"])
        for (label, judge), p in sorted(caches.items()):
            s = summarize_cache(p)
            w.writerow([label, judge] + [s[k] for k in ["n", "overall_correct", "precision", "ci_lo", "ci_hi",
                                                          "plausible_rate", "io_rate", "hs_rate", "inconsistent_count"]])
    with open(a.out_dir / "judge_agreement.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["label", "n_both", "agreement", "cohen_kappa"])
        for label in sorted({l for l, _ in caches}):
            js = [caches[(l, j)] for (l, j) in sorted(caches) if l == label]
            if len(js) >= 2:
                po, k = cohen_kappa(js[0], js[1])
                w.writerow([label, len(set(_rows(js[0])) & set(_rows(js[1]))), f"{po:.3f}", f"{k:.3f}"])
    md = ["# Judge summary", "", "| label | judge | n | precision | 95% CI | plausible | I/O | HS | inconsistent |", "|---|---|--:|--:|--|--:|--:|--:|--:|"]
    for (label, judge), p in sorted(caches.items()):
        s = summarize_cache(p)
        md.append(f"| {label} | {judge} | {s['n']} | {s['precision']:.3f} | [{s['ci_lo']:.3f}, {s['ci_hi']:.3f}] | "
                  f"{s['plausible_rate']:.3f} | {s['io_rate']:.3f} | {s['hs_rate']:.3f} | {s['inconsistent_count']} |")
    (a.out_dir / "judge_summary.md").write_text("\n".join(md) + "\n")

if __name__ == "__main__":
    main()
