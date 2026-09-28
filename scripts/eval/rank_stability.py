#!/usr/bin/env python3
"""RQ3: stability of the criticality list across independent generations of the same MEKH
(paper: experiments.tex RQ3; criticality as in scripts/eval/criticality.py).

Usage: python scripts/eval/rank_stability.py --out-dir "$DATA" --base 280450 \
          --folder boron "$STATE_B" --folder boron2 "$STATE_B2" ... \
          [--p 0.98] [--k 10] [--samples 1000] [--seed 0] [--figure PATH.png]

Per run: criticality list over its registered vertices except m_base (m_base must be a
registered vertex of every run, else ValueError). Headline aggregate: classic Borda count
(a material earns, in each list, one point per material ranked strictly below it, i.e.
strictly less critical; absent materials earn 0; points are summed). Sensitivity aggregate
("critsum"): sum of criticality values. Each run's list is compared with the
aggregate by extrapolated rank-biased overlap, RBO_ext (Webber, Moffat & Zobel 2010,
eq. 32, which handles lists of different lengths) at persistence p, and by the overlap of
their top-k sets. The lists are only partially ordered, so ties are broken uniformly at
random (independently per list) and RBO / top-k overlap are averaged over --samples
tie-breaks (seeded; exact when neither list has ties). Also reported: pairwise RBO / top-k
overlap between every pair of runs (run vs run, independent of the aggregate). SDs are sample
SDs (ddof=1); *_sd_pop columns give the population SD (ddof=0) for reference.

Writes rank_stability.csv (summary), rank_stability_runs.csv (per run),
rank_stability_aggregate.csv (Borda list) and boron_degree_distribution.csv (in/out-degree
= number of hyperedges producing/consuming a material, mean and sample SD of counts across runs).
--figure draws that distribution (needs matplotlib, which lia's venv lacks: run with e.g.
`uv run --no-project --with matplotlib --with numpy python ...`).
"""
from __future__ import annotations
import argparse, csv, random, statistics
from itertools import combinations
from pathlib import Path

if __package__ in (None, ""):
    import sys; sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.eval.criticality import build_hypergraph, criticality, degrees, load_state

def stats(xs: list[float]) -> dict:
    xs = list(xs)
    return {"mean": statistics.fmean(xs), "sd": statistics.stdev(xs) if len(xs) > 1 else 0.0,
            "sd_pop": statistics.pstdev(xs), "min": min(xs), "max": max(xs)}

def criticality_list(state: dict, base: str) -> tuple[dict, set, list]:
    """(criticality dict, vertices, edges) of one run; fails loudly if base is not a vertex."""
    verts, edges, _ = build_hypergraph(state)
    if base not in verts:
        raise ValueError(f"base {base} is not a registered vertex of this MEKH")
    c, _ = criticality(verts, edges, base)
    return c, verts, edges

def borda(lists: list[dict]) -> dict:
    """Sum over lists of the number of items in that list strictly below the material."""
    pts: dict = {}
    for l in lists:
        vals = sorted(l.values())
        for m, v in l.items():
            below = sum(1 for x in vals if x < v)
            pts[m] = pts.get(m, 0) + below
    return pts

def critsum(lists: list[dict]) -> dict:
    """Sensitivity variant: sum of criticality values across lists (absent = 0)."""
    out: dict = {}
    for l in lists:
        for m, v in l.items(): out[m] = out.get(m, 0) + v
    return out

def order(scores: dict, rng: random.Random | None) -> list:
    """Items by descending score; ties by key (rng=None) or shuffled with rng."""
    groups: dict = {}
    for m, v in scores.items(): groups.setdefault(v, []).append(m)
    out = []
    for v in sorted(groups, reverse=True):
        g = sorted(groups[v])
        if rng is not None: rng.shuffle(g)
        out += g
    return out

def rbo_ext(S: list, T: list, p: float) -> float:
    """Extrapolated RBO (Webber et al. 2010, eq. 32; eq. 30 when lengths are equal)."""
    if len(S) > len(T): S, T = T, S
    s, l = len(S), len(T)
    if l == 0: return 1.0
    if s == 0: return 0.0
    X = [0] * (l + 1); inS, inT, x = set(), set(), 0
    for d in range(1, l + 1):
        b = T[d - 1]
        if d <= s:
            a = S[d - 1]
            x += 1 if a == b else (a in inT) + (b in inS)
            inS.add(a)
        else:
            x += b in inS
        inT.add(b); X[d] = x
    sum1 = sum(X[d] / d * p ** d for d in range(1, l + 1))
    sum2 = sum(X[s] * (d - s) / (s * d) * p ** d for d in range(s + 1, l + 1))
    return (1 - p) / p * (sum1 + sum2) + ((X[l] - X[s]) / l + X[s] / s) * p ** l

def _has_ties(d: dict) -> bool: return len(set(d.values())) < len(d)

def compare(a: dict, b: dict, p: float, k: int, n_samples: int, seed: int) -> dict:
    """Expected RBO_ext and top-k overlap (count, Jaccard) over random tie-breaks."""
    rng = random.Random(seed)
    n = n_samples if (_has_ties(a) or _has_ties(b)) else 1
    r = ov = jac = 0.0
    for _ in range(n):
        oa, ob = (order(a, rng), order(b, rng)) if n > 1 else (order(a, None), order(b, None))
        ta, tb = set(oa[:k]), set(ob[:k])
        r += rbo_ext(oa, ob, p); ov += len(ta & tb); jac += len(ta & tb) / len(ta | tb) if ta | tb else 1.0
    return {"rbo": r / n, "topk_overlap": ov / n, "topk_jaccard": jac / n}

def degree_table(runs: list[dict]) -> list[dict]:
    """runs: [{"in": [deg per vertex], "out": [...]}]. Per degree value, mean/SD (ddof=0)
    across runs of the number of vertices with that degree (0 when a run has none); SD ddof=1."""
    mx = max(max(r["in"] + r["out"] + [0]) for r in runs)
    rows = []
    for k in range(mx + 1):
        ins = [r["in"].count(k) for r in runs]; outs = [r["out"].count(k) for r in runs]
        rows.append({"degree": k, "in_mean": statistics.fmean(ins), "in_sd": stats(ins)["sd"],
                     "out_mean": statistics.fmean(outs), "out_sd": stats(outs)["sd"]})
    return rows

def plot_degrees(rows: list[dict], n_runs: int, path: Path) -> None:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.size": 22})
    x = np.array([r["degree"] for r in rows]); w = 0.4
    def err(side):  # 1 SD, clipped at 0 below; no bar/whisker where no run has that degree
        m = np.array([r[f"{side}_mean"] for r in rows]); sd = np.array([r[f"{side}_sd"] for r in rows])
        lo = np.where(m > 0, np.minimum(sd, m), np.nan); hi = np.where(m > 0, sd, np.nan)
        return m, np.vstack([lo, hi])
    fig, ax = plt.subplots(figsize=(8.8, 6.8))
    m, e = err("in")
    ax.bar(x - w / 2, m, w, yerr=e, capsize=4, color="#1f77b4", ecolor="black", label="Indegree distribution")
    m, e = err("out")
    ax.bar(x + w / 2, m, w, yerr=e, capsize=4, color="#ff7f0e", ecolor="black", label="Outdegree distribution")
    ax.set_xlabel("Indegree and Outdegree"); ax.set_ylabel("Average Count")
    ax.grid(True, linestyle="--", alpha=0.7); ax.set_axisbelow(True); ax.legend()
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)

def _write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", nargs=2, action="append", metavar=("LABEL", "PATH"), required=True)
    ap.add_argument("--base", default="280450")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--p", type=float, default=0.98)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--samples", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--figure", type=Path)
    a = ap.parse_args()
    lists, degs, names = [], [], {}
    for label, path in a.folder:
        st = load_state(Path(path))
        try: c, verts, edges = criticality_list(st, a.base)
        except ValueError as e: raise SystemExit(f"{label}: {e}")
        lists.append((label, c))
        ind, outd = degrees(verts, edges); degs.append({"in": list(ind.values()), "out": list(outd.values())})
        for m in c: names.setdefault(m, st["materials"].get(m, {}).get("name", ""))
    summary = {"n_runs": len(lists), "base": a.base, "p": a.p, "k": a.k, "samples": a.samples, "seed": a.seed}
    per_run = []
    for agg_name, agg_fn in (("borda", borda), ("critsum", critsum)):
        agg = agg_fn([c for _, c in lists])
        res = [compare(c, agg, a.p, a.k, a.samples, a.seed + i) for i, (_, c) in enumerate(lists)]
        rb = [r["rbo"] for r in res]; ov = [r["topk_overlap"] for r in res]; jc = [r["topk_jaccard"] for r in res]
        sr, so = stats(rb), stats(ov)
        summary |= {f"{agg_name}_rbo_mean": sr["mean"], f"{agg_name}_rbo_sd": sr["sd"], f"{agg_name}_rbo_sd_pop": sr["sd_pop"],
                    f"{agg_name}_rbo_min": sr["min"], f"{agg_name}_rbo_max": sr["max"],
                    f"{agg_name}_topk_overlap_mean": so["mean"], f"{agg_name}_topk_overlap_sd": so["sd"],
                    f"{agg_name}_topk_jaccard_mean": statistics.fmean(jc)}
        for (label, c), r in zip(lists, res):
            per_run.append({"aggregate": agg_name, "label": label, "n_items": len(c), **r})
        if agg_name == "borda":
            _write(a.out_dir / "rank_stability_aggregate.csv",
                   [{"rank": i, "hs_code": m, "name": names.get(m, ""), "borda": agg[m],
                     "n_runs_present": sum(m in c for _, c in lists)} for i, m in enumerate(order(agg, None), 1)])
            top = order(agg, None)[: a.k]
            summary["borda_topk_codes"] = " ".join(top)
    pw = [compare(c1, c2, a.p, a.k, a.samples, a.seed + 100 + i)
          for i, ((_, c1), (_, c2)) in enumerate(combinations(lists, 2))]
    sp, spo = stats([r["rbo"] for r in pw]), stats([r["topk_overlap"] for r in pw])
    summary |= {"n_pairs": len(pw), "pairwise_rbo_mean": sp["mean"], "pairwise_rbo_sd": sp["sd"],
                "pairwise_rbo_sd_pop": sp["sd_pop"], "pairwise_rbo_min": sp["min"], "pairwise_rbo_max": sp["max"],
                "pairwise_topk_overlap_mean": spo["mean"], "pairwise_topk_overlap_sd": spo["sd"]}
    _write(a.out_dir / "rank_stability.csv", [summary]); _write(a.out_dir / "rank_stability_runs.csv", per_run)
    rows = degree_table(degs); _write(a.out_dir / "boron_degree_distribution.csv", rows)
    if a.figure: plot_degrees(rows, len(degs), a.figure)
    for k, v in summary.items(): print(k, round(v, 4) if isinstance(v, float) else v)

if __name__ == "__main__":
    main()
