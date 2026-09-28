#!/usr/bin/env python3
"""Section 6 criticality by reachability, computed per MEKH (paper: application.tex,
Definitions "Precursor Set", "Reachable set", "Criticality").

Usage: python scripts/eval/criticality.py --out-dir "$DATA" \
          --folder boron "$STATE_B" [--folder cobalt "$STATE_CO" ...] [--base LABEL HSCODE ...]

Hypergraph: vertices are the registered materials (keys of state["materials"] that are
6-digit HS codes). Each process is a hyperedge whose source/target sets are its
precursors/products restricted to registered vertices; bare-string entries, missing or
malformed codes ("untyped") and well-formed codes that are not registered materials
("unregistered", process-only codes) are dropped and counted. --include-unregistered
turns process-only 6-digit codes into vertices instead (sensitivity check). Processes
left with no target are dropped (they cannot make anything reachable); processes left
with no source (all inputs untyped/unregistered) fire unconditionally -- the empty source set
vacuously satisfies the Reachable-set definition. --drop-sourceless drops them instead
(sensitivity variant; their products then become precursors if nothing else makes them).

m_start = {m_base} U Pre; c(m) = |R(m_start, H)| - |R(m_start \\ m, H \\ m)|. Deletion
semantics of H \\ m (a ban on m): m leaves the start set, no hyperedge with m in its source set
can fire, and m is never counted as reachable; hyperedges that produce m still fire when their
sources are available, so their co-products survive. Writes "$OUT/criticality_<label>.csv" (ranked,
ties broken by HS code) and "$OUT/criticality_summary.csv".
"""
from __future__ import annotations
import argparse, csv, json, re
from pathlib import Path

SIX_DIGIT = re.compile(r"^\d{6}$")
# m_base per MEKH: the refined/unwrought element itself (see report; override with --base).
DEFAULT_BASE = {"boron": "280450", "cobalt": "810520", "gallium": "811292", "germanium": "811292"}

Edge = tuple[frozenset, frozenset]

def _code(entry) -> str | None:
    if isinstance(entry, dict) and entry.get("hs_code") is not None:
        c = str(entry["hs_code"]).strip()
        return c if SIX_DIGIT.match(c) else None
    return None

def build_hypergraph(state: dict, include_unregistered: bool = False,
                     drop_sourceless: bool = False) -> tuple[set, list[Edge], dict]:
    """Return (vertices, edges, audit) for a research_state dict (see module doc)."""
    mats = state.get("materials", {})
    verts = {str(k) for k in mats if SIX_DIGIT.match(str(k))}
    procs = state.get("processes", {})
    if include_unregistered:
        for p in procs.values():
            for e in list(p.get("precursors", [])) + list(p.get("products", [])):
                if _code(e): verts.add(_code(e))
    audit = {"n_vertices": len(verts), "n_invalid_material_keys": len(mats) - sum(1 for k in mats if SIX_DIGIT.match(str(k))),
             "n_edges": 0, "n_processes": len(procs), "n_processes_no_target": 0, "n_processes_no_source": 0,
             "n_entries_untyped": 0, "n_entries_unregistered": 0}
    edges: list[Edge] = []
    for p in procs.values():
        sides = []
        for key in ("precursors", "products"):
            keep = set()
            for e in p.get(key, []) or []:
                c = _code(e)
                if c is None: audit["n_entries_untyped"] += 1
                elif c not in verts: audit["n_entries_unregistered"] += 1
                else: keep.add(c)
            sides.append(frozenset(keep))
        src, tgt = sides
        if not tgt:
            audit["n_processes_no_target"] += 1
            continue
        if not src:
            audit["n_processes_no_source"] += 1
            if drop_sourceless: continue
        edges.append((src, tgt))
    audit["n_edges"] = len(edges)
    return verts, edges, audit

def precursor_set(edges: list[Edge]) -> set:
    """Pre = (union of sources) - (union of targets)."""
    src = set().union(*[s for s, _ in edges]) if edges else set()
    tgt = set().union(*[t for _, t in edges]) if edges else set()
    return src - tgt

def reachable(edges: list[Edge], start: set, removed: set = frozenset()) -> set:
    """R(start, H \\ removed): materials in the target set of a hyperedge whose sources are all in
    start or reachable (least fixpoint). Removed materials can be neither sources nor targets."""
    avail = set(start) - set(removed); R: set = set(); fired = [False] * len(edges); changed = True
    while changed:
        changed = False
        for i, (s, t) in enumerate(edges):
            if fired[i] or (s & removed) or not s <= avail: continue
            fired[i] = True; changed = True
            new = t - set(removed)
            R |= new; avail |= new
    return R

def criticality(verts: set, edges: list[Edge], base: str) -> tuple[dict, int]:
    """{material: c(m, {base} U Pre, H)} for every vertex except base, and |R({base} U Pre, H)|."""
    start = precursor_set(edges) | {base}
    r0 = len(reachable(edges, start))
    return {m: r0 - len(reachable(edges, start - {m}, removed={m})) for m in verts if m != base}, r0

def ranked(c: dict) -> list[tuple[str, int]]:
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))

def top_k(c: dict, k: int) -> list[tuple[str, int]]:
    return ranked(c)[:k]

def degrees(verts: set, edges: list[Edge]) -> tuple[dict, dict]:
    """(in-degree, out-degree) per vertex: number of hyperedges producing / consuming it."""
    ind = {v: 0 for v in verts}; outd = {v: 0 for v in verts}
    for s, t in edges:
        for v in t: ind[v] += 1
        for v in s: outd[v] += 1
    return ind, outd

def load_state(folder: Path) -> dict:
    return json.loads((Path(folder) / "research_state.json").read_text())

def run_folder(label: str, folder: Path, base: str, out_dir: Path | None = None,
               include_unregistered: bool = False, drop_sourceless: bool = False,
               csv_suffix: str = "") -> tuple[dict, list[dict]]:
    state = load_state(folder); mats = state.get("materials", {})
    verts, edges, audit = build_hypergraph(state, include_unregistered, drop_sourceless)
    if base not in verts:
        raise SystemExit(f"{label}: base {base} is not a registered vertex")
    c, r0 = criticality(verts, edges, base)
    pre = precursor_set(edges); R = reachable(edges, pre | {base}); ind, outd = degrees(verts, edges)
    rows, prev, rank = [], None, 0
    for i, (m, v) in enumerate(ranked(c), 1):
        if v != prev: rank, prev = i, v  # competition ranking ("1224") for ties
        rows.append({"rank": rank, "hs_code": m, "name": mats.get(m, {}).get("name", ""), "criticality": v,
                     "in_reach": int(m in R), "in_pre": int(m in pre), "in_degree": ind[m], "out_degree": outd[m]})
    if out_dir is not None:
        with open(Path(out_dir) / f"criticality_{label}{csv_suffix}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["rank", "hs_code", "name", "criticality"])
            w.writeheader(); w.writerows(rows)
    top = rows[:3]
    third = top[-1]["criticality"] if top else None
    summary = {"label": label, "base_code": base, "base_name": mats.get(base, {}).get("name", ""), "reach": r0,
               "n_pre": len(pre), **audit,
               "n_tied_with_third": sum(1 for r in rows if r["criticality"] == third) if top else 0}
    for i in range(3):
        r = rows[i] if i < len(rows) else {"hs_code": "", "name": "", "criticality": ""}
        summary |= {f"top{i+1}_code": r["hs_code"], f"top{i+1}_name": r["name"], f"top{i+1}_criticality": r["criticality"]}
    return summary, rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", nargs=2, action="append", metavar=("LABEL", "PATH"), required=True)
    ap.add_argument("--base", nargs=2, action="append", metavar=("LABEL", "HSCODE"), default=[])
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--include-unregistered", action="store_true")
    ap.add_argument("--drop-sourceless", action="store_true",
                    help="drop processes with no registered input (sensitivity); per-MEKH CSVs get suffix _nosourceless")
    ap.add_argument("--summary-name", default="criticality_summary.csv")
    a = ap.parse_args()
    bases = DEFAULT_BASE | dict(a.base)
    out = []
    for label, path in a.folder:
        s, _ = run_folder(label, Path(path), bases[label.split(".")[0]] if label not in bases else bases[label],
                          a.out_dir, a.include_unregistered, a.drop_sourceless,
                          "_nosourceless" if a.drop_sourceless else "")
        out.append(s)
        print(label, s["base_code"], "R =", s["reach"], [(s[f"top{i}_code"], s[f"top{i}_criticality"]) for i in (1, 2, 3)])
    with open(a.out_dir / a.summary_name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)

if __name__ == "__main__":
    main()
