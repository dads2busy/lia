#!/usr/bin/env python3
"""Recall of author-curated canonical routes in each MEKH.

Usage: python scripts/eval/known_route_recall.py --routes "$DATA/known_routes.csv" --out-dir "$DATA" \
          --folder boron "$STATE_B" [--folder gallium "$STATE_GA" ...]
"""
from __future__ import annotations
import argparse, csv, json, re
from pathlib import Path

SIX = re.compile(r"^\d{6}$")

def load_routes(path: Path) -> tuple[list[dict], list[str]]:
    routes, rejected = [], []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            ins = {c.strip() for c in r["input_hs"].split("|") if c.strip()}
            outs = {c.strip() for c in r["output_hs"].split("|") if c.strip()}
            if not ins or not outs or not all(SIX.match(c) for c in ins | outs):
                rejected.append(r["route_id"]); continue
            routes.append({"base_material": r["base_material"], "route_id": r["route_id"],
                           "description": r["description"], "inputs": ins, "outputs": outs})
    return routes, rejected

def process_hs_sets(folder: Path) -> list[tuple[set[str], set[str]]]:
    state = json.loads((folder / "research_state.json").read_text())
    out = []
    for p in state.get("processes", {}).values():
        hs = lambda ms: {str(m["hs_code"]) for m in ms if isinstance(m, dict) and m.get("hs_code")}
        out.append((hs(p.get("precursors", [])), hs(p.get("products", []))))
    return out

def recall_for(routes: list[dict], procs: list[tuple[set[str], set[str]]]) -> tuple[dict, dict]:
    detail = {}
    for r in routes:
        status = "miss"
        for pin, pout in procs:
            if r["inputs"] <= pin and r["outputs"] <= pout: status = "strict"; break
            if (r["inputs"] & pin) and (r["outputs"] & pout): status = "lenient"
        detail[r["route_id"]] = status
    n = len(routes); s_ = sum(1 for v in detail.values() if v == "strict")
    l_ = sum(1 for v in detail.values() if v in ("strict", "lenient"))
    return ({"n_routes": n, "recovered_lenient": l_, "recall_lenient": l_ / n if n else 0.0,
             "recovered_strict": s_, "recall_strict": s_ / n if n else 0.0}, detail)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", type=Path, required=True)
    ap.add_argument("--folder", nargs=2, action="append", metavar=("LABEL", "PATH"), required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args()
    routes, rejected = load_routes(a.routes)
    if rejected: print("REJECTED (non-6-digit or empty):", rejected)
    with open(a.out_dir / "known_route_recall.csv", "w", newline="") as f, \
         open(a.out_dir / "known_route_recall_detail.csv", "w", newline="") as g:
        w = csv.writer(f); w.writerow(["label", "n_routes", "recovered_lenient", "recall_lenient", "recovered_strict", "recall_strict"])
        wd = csv.writer(g); wd.writerow(["label", "route_id", "description", "status"])
        for label, path in a.folder:
            rs = [r for r in routes if r["base_material"] == label]
            s, detail = recall_for(rs, process_hs_sets(Path(path)))
            w.writerow([label] + [s[k] for k in ["n_routes", "recovered_lenient", "recall_lenient", "recovered_strict", "recall_strict"]])
            for r in rs: wd.writerow([label, r["route_id"], r["description"], detail[r["route_id"]]])
            print(label, s)

if __name__ == "__main__":
    main()
