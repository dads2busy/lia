#!/usr/bin/env python3
"""Section 6 disruption analysis with UN Comtrade (paper: application.tex, "Disruption
analysis with UN Comtrade"; original: lia src/lia/research/map_exports_to_material.py +
dominant_supplier_analysis.py, re-implemented here).

Usage: python scripts/eval/disruption.py --out-dir "$DATA" \
          --trade /path/aggregate_intercountry_HS_flow_values_2024.arrow \
          --partners /path/partnerAreas.arrow [--threshold 0.6] \
          --folder boron "$STATE_B" [--folder cobalt "$STATE_CO" ...]

For every registered material code: invalid (not 6 digits) / absent (no 2024 Comtrade row)
/ in Comtrade. For codes in Comtrade, global exports = sum of all flow values for the code,
the top exporter = the partner (exporting country; partnerCode, as in
map_exports_to_material.py where "from" = partner) with the largest summed value, and the code
is dominated when that share is >= threshold. Disruption of a dominated code is propagated
as in dominant_supplier_analysis.propagate_disruptions: a process is disabled when any input
is disrupted; a material is disrupted when every process producing it is disabled (materials
no process produces are only disrupted directly). Dependents = disrupted codes other than
the code itself. The hypergraph is the registered-vertex one of criticality.py (the original
also kept unregistered 6-digit codes: --include-unregistered reproduces that). reach_loss is the Section 6 criticality of
the code (|R| lost from {m_base} U Pre), given for comparison.

Writes disruption_<label>.csv (one row per registered code) and disruption_summary.csv.
"""
from __future__ import annotations
import argparse, csv
from pathlib import Path
import pyarrow as pa, pyarrow.compute as pc
import pandas as pd

if __package__ in (None, ""):
    import sys; sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.eval.criticality import SIX_DIGIT, DEFAULT_BASE, build_hypergraph, criticality, load_state

def _read_arrow(path) -> pa.Table:
    return pa.ipc.open_file(pa.memory_map(str(path), "r")).read_all()

def load_trade(path, codes: set) -> pd.DataFrame:
    """Rows of the Comtrade arrow file for the given cmdCodes, summed by (cmdCode, partnerCode)."""
    t = _read_arrow(path)
    t = t.filter(pc.is_in(t["cmdCode"], value_set=pa.array(sorted(codes), pa.string())))
    df = t.select(["cmdCode", "partnerCode", "value"]).to_pandas()
    return df.groupby(["cmdCode", "partnerCode"], as_index=False)["value"].sum()

def load_partners(path) -> dict:
    return {int(r["PartnerCode"]): (r["PartnerCodeIsoAlpha3"], r["PartnerDesc"]) for r in _read_arrow(path).to_pylist()}

def dominance(df: pd.DataFrame, threshold: float) -> dict:
    out = {}
    for code, g in df.groupby("cmdCode"):
        total = float(g["value"].sum())
        if total <= 0: continue
        top = g.sort_values(["value", "partnerCode"], ascending=[False, True]).iloc[0]
        share = float(top["value"]) / total
        out[str(code)] = {"total": total, "top_partner": int(top["partnerCode"]), "top_value": float(top["value"]),
                          "share": share, "dominated": share >= threshold}
    return out

def propagate(edges, removed: set) -> set:
    """Disrupted materials after removing `removed` (dominant_supplier_analysis semantics)."""
    disrupted = set(removed); alive = [True] * len(edges); producers: dict = {}
    for i, (_, t) in enumerate(edges):
        for m in t: producers.setdefault(m, []).append(i)
    changed = True
    while changed:
        changed = False
        for i, (s, _) in enumerate(edges):
            if alive[i] and s & disrupted: alive[i] = False; changed = True
        for m, ps in producers.items():
            if m not in disrupted and not any(alive[i] for i in ps): disrupted.add(m); changed = True
    return disrupted

def analyze_state(state: dict, dom: dict, base: str, partner_names: dict,
                  include_unregistered: bool = False) -> list[dict]:
    mats = state.get("materials", {})
    verts, edges, _ = build_hypergraph(state, include_unregistered)
    crit, _ = criticality(verts, edges, base) if base in verts else ({}, 0)
    rows = []
    for code in sorted(map(str, mats)):
        r = {"hs_code": code, "name": mats[code].get("name", ""), "status": "", "total_exports": "",
             "top_exporter_code": "", "top_exporter_iso3": "", "top_exporter_name": "", "top_share": "",
             "dominated": 0, "n_dependents": "", "dependents": "", "dependents_frac": "", "reach_loss": ""}
        if not SIX_DIGIT.match(code): r["status"] = "invalid"
        elif code not in dom: r["status"] = "absent"
        else:
            d = dom[code]; iso, nm = partner_names.get(d["top_partner"], (f"UNK_{d['top_partner']}", ""))
            r |= {"status": "ok", "total_exports": round(d["total"], 3), "top_exporter_code": d["top_partner"],
                  "top_exporter_iso3": iso, "top_exporter_name": nm, "top_share": round(d["share"], 4),
                  "dominated": int(d["dominated"])}
            if d["dominated"]:
                dep = sorted(propagate(edges, {code}) - {code})
                r |= {"n_dependents": len(dep), "dependents": " ".join(dep),
                      "dependents_frac": round(len(dep) / (len(verts) - 1), 4) if len(verts) > 1 else 0.0,
                      "reach_loss": crit.get(code, "")}
        rows.append(r)
    return rows

def summarize(label: str, rows: list[dict]) -> dict:
    ok = [r for r in rows if r["status"] == "ok"]; dom = [r for r in ok if r["dominated"]]
    casc = [r for r in dom if r["n_dependents"]]
    mx = max(dom, key=lambda r: (r["n_dependents"], -int(r["hs_code"])), default=None)
    return {"label": label, "n_codes": len(rows), "n_invalid": sum(r["status"] == "invalid" for r in rows),
            "n_absent": sum(r["status"] == "absent" for r in rows), "n_in_comtrade": len(ok),
            "n_dominated": len(dom), "frac_dominated": round(len(dom) / len(ok), 4) if ok else 0.0,
            "n_dominated_cascading": len(casc), "n_dominated_local": len(dom) - len(casc),
            "total_dependents": sum(r["n_dependents"] for r in dom),
            "max_code": mx["hs_code"] if mx else "", "max_name": mx["name"] if mx else "",
            "max_supplier_iso3": mx["top_exporter_iso3"] if mx else "", "max_supplier_name": mx["top_exporter_name"] if mx else "",
            "max_share": mx["top_share"] if mx else "", "max_dependents": mx["n_dependents"] if mx else 0,
            "max_dependents_frac": mx["dependents_frac"] if mx else 0.0,
            "dominated_codes": " ".join(f"{r['hs_code']}:{r['top_exporter_iso3']}:{r['n_dependents']}" for r in dom)}

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", nargs=2, action="append", metavar=("LABEL", "PATH"), required=True)
    ap.add_argument("--base", nargs=2, action="append", metavar=("LABEL", "HSCODE"), default=[])
    ap.add_argument("--trade", type=Path, required=True)
    ap.add_argument("--partners", type=Path, required=True)
    ap.add_argument("--threshold", type=float, default=0.6)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--summary-name", default="disruption_summary.csv")
    ap.add_argument("--include-unregistered", action="store_true",
                    help="keep process-only 6-digit codes as vertices, as the original code did (sensitivity)")
    a = ap.parse_args()
    bases = DEFAULT_BASE | dict(a.base)
    states = [(label, load_state(Path(p))) for label, p in a.folder]
    codes = {str(c) for _, s in states for c in s.get("materials", {}) if SIX_DIGIT.match(str(c))}
    dom = dominance(load_trade(a.trade, codes), a.threshold); partners = load_partners(a.partners)
    summ = []
    for label, st in states:
        rows = analyze_state(st, dom, bases.get(label, bases.get(label.rstrip("0123456789"), "")), partners,
                             a.include_unregistered)
        with open(a.out_dir / f"disruption_{label}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        s = summarize(label, rows); s["threshold"] = a.threshold; summ.append(s)
        print({k: v for k, v in s.items()})
    with open(a.out_dir / a.summary_name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0])); w.writeheader(); w.writerows(summ)

if __name__ == "__main__":
    main()
