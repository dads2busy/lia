#!/usr/bin/env python3
"""RQ2: HS codes present in a MEKH but absent from the USGS Mineral Commodity Summaries listing.

Usage: python scripts/eval/topdown_coverage.py --usgs "$DATA/usgs_mcs_hs_codes.csv" --out-dir "$DATA" \
          --folder boron "$STATE_B" [--folder gallium "$STATE_GA" ...]
"""
from __future__ import annotations
import argparse, csv, json
from collections import Counter
from pathlib import Path

def mekh_codes(folder: Path) -> dict[str, tuple[str, int]]:
    state = json.loads((folder / "research_state.json").read_text())
    part = Counter()  # number of distinct processes each code participates in
    for p in state.get("processes", {}).values():
        codes = {str(m["hs_code"]) for m in p.get("precursors", []) + p.get("products", [])
                 if isinstance(m, dict) and m.get("hs_code")}
        for c in codes: part[c] += 1
    return {code: (rec.get("name", ""), part.get(code, 0)) for code, rec in state.get("materials", {}).items()}

def coverage(codes: dict[str, tuple[str, int]], usgs: set[str]) -> tuple[dict, list[tuple[str, str, int]]]:
    only = sorted(((c, n, k) for c, (n, k) in codes.items() if c not in usgs), key=lambda t: -t[2])
    s = {"mekh_codes": len(codes), "usgs_codes": len(usgs), "overlap": len(set(codes) & usgs),
         "mekh_only": len(only), "frac_mekh_only": (len(only) / len(codes)) if codes else 0.0}
    return s, only

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usgs", type=Path, required=True)
    ap.add_argument("--folder", nargs=2, action="append", metavar=("LABEL", "PATH"), required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args()
    usgs: dict[str, set[str]] = {}
    with open(a.usgs, newline="") as f:
        for r in csv.DictReader(f): usgs.setdefault(r["commodity"], set()).add(r["hs_code"].strip())
    with open(a.out_dir / "topdown_coverage.csv", "w", newline="") as f, \
         open(a.out_dir / "topdown_coverage_examples.csv", "w", newline="") as g:
        w = csv.writer(f); w.writerow(["label", "mekh_codes", "usgs_codes", "overlap", "mekh_only", "frac_mekh_only"])
        we = csv.writer(g); we.writerow(["label", "hs_code", "name", "n_processes"])
        for label, path in a.folder:
            s, only = coverage(mekh_codes(Path(path)), usgs.get(label, set()))
            w.writerow([label] + [s[k] for k in ["mekh_codes", "usgs_codes", "overlap", "mekh_only", "frac_mekh_only"]])
            for c, n, k in only[:10]: we.writerow([label, c, n, k])
            print(label, s)

if __name__ == "__main__":
    main()
