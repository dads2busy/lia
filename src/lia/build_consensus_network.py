"""consensus_generator.py  — hyper-edge consensus builder (JSON + TSV only)

Creates a consensus hyper-DAG from two or more run JSON files.

Output
------
• <out>.json      consensus graph (nodes + edges)
• <out>.disagree  TSV of low-support / inconsistent items
• console summary

Edge format in all files:
    {"source": [...], "target": "<HS-code>", ...}
"""

from __future__ import annotations
import itertools, io, json, math, textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import typer

app = typer.Typer(add_completion=False, invoke_without_command=True)

# ──────────────────────────── JSON I/O ────────────────────────────
def _load_run(path: Path):
    """Return (nodes, edges) where edges use (tuple(source_list), target_str)."""
    data = json.loads(path.read_text())
    if not {"nodes", "links"} <= data.keys():
        raise typer.Exit(code=1, message=f"[error] {path} missing 'nodes' or 'links'")

    nodes = {n["id"]: {k: v for k, v in n.items() if k != "id"} for n in data["nodes"]}
    edges = []
    for e in data["links"]:
        src = tuple(sorted(e.get("sources") or e.get("source") or []))
        tgt = e.get("target") or (e.get("targets")[0] if e.get("targets") else "")
        if not src or not tgt:
            continue
        refs = e.get("references") or e.get("reference") or []
        if isinstance(refs, str):
            refs = [refs]
        edges.append(
            {"source": src, "target": tgt, "process": e.get("process", ""), "references": refs}
        )
    return nodes, edges

# ─────────────────── Support aggregation / majority ──────────────────
def _collect_support(runs):
    n_sup, e_sup = Counter(), Counter()
    n_stage, n_mat, n_desc = defaultdict(list), defaultdict(list), defaultdict(list)
    e_proc, e_refs = defaultdict(list), defaultdict(list)

    for nodes, edges in runs:
        for nid, attrs in nodes.items():
            n_sup[nid] += 1
            n_stage[nid].append(attrs.get("stage", ""))
            n_mat[nid].append(attrs.get("material", ""))
            n_desc[nid].append(attrs.get("description", ""))
        for ed in edges:
            key = (ed["source"], ed["target"])
            e_sup[key] += 1
            if ed["process"]:
                e_proc[key].append(ed["process"])
            e_refs[key].extend(ed["references"])
    return n_sup, n_stage, n_mat, n_desc, e_sup, e_proc, e_refs

_majority = lambda vals: Counter([v for v in vals if v]).most_common(1)[0][0] if vals else ""

# ───────────────────────── Consensus build ─────────────────────────
def _build_consensus(runs, min_node: int, min_edge: int):
    n_sup, n_stage, n_mat, n_desc, e_sup, e_proc, e_refs = _collect_support(runs)

    # identify leaves (no incoming OR no outgoing in aggregated edges)
    incoming, outgoing = defaultdict(int), defaultdict(int)
    for srcs, tgt in e_sup.keys():
        for s in srcs:
            outgoing[s] += 1
        incoming[tgt] += 1
    leaves = {n for n in set(incoming) | set(outgoing) if incoming[n] == 0 or outgoing[n] == 0}

    kept_nodes = {nid for nid, cnt in n_sup.items() if cnt >= min_node or nid in leaves}

    nodes_out = [
        {
            "id": nid,
            "support": n_sup[nid],
            "stage": _majority(n_stage[nid]),
            "material": _majority(n_mat[nid]),
            "description": _majority(n_desc[nid]),
            "stage_consistent": len({s.lower() for s in n_stage[nid] if s}) == 1,
        }
        for nid in kept_nodes
    ]
    maj_material = {n["id"]: n["material"] for n in nodes_out}

    edges_out = []
    for (src, tgt), cnt in e_sup.items():
        if cnt < min_edge:
            continue
        if not (all(n in kept_nodes for n in src) and tgt in kept_nodes):
            continue
        mats = {maj_material[n] for n in src + (tgt,) if maj_material[n]}
        if len(mats) < 2:
            continue
        edges_out.append(
            {
                "source": list(src),
                "target": tgt,
                "support": cnt,
                "process": sorted(set(e_proc[(src, tgt)])),
                "references": sorted(set(e_refs[(src, tgt)])),
            }
        )

    # drop orphan nodes
    incident = set(itertools.chain(*[e["source"] + [e["target"]] for e in edges_out]))
    nodes_out = [n for n in nodes_out if n["id"] in incident]

    return nodes_out, edges_out, n_sup, e_sup, n_stage, n_mat, e_proc

# ───────────────────── Disagreement row generator ───────────────────
def _disagreement_rows(n_sup, e_sup, n_stage, n_mat, e_proc, thresh):
    for nid, cnt in n_sup.items():
        if cnt < thresh:
            yield (
                "node", nid, cnt,
                _majority(n_stage[nid]),
                ";".join(f"{s}:{c}" for s, c in Counter(n_stage[nid]).items()),
                _majority(n_mat[nid]),
                ";".join(f"{m}:{c}" for m, c in Counter(n_mat[nid]).items()),
            )
    for (src, tgt), cnt in e_sup.items():
        if cnt < thresh:
            procs = e_proc[(src, tgt)]
            yield (
                "edge", "+".join(src)+"->"+tgt, cnt,
                _majority(procs),
                ";".join(f"{p}:{c}" for p, c in Counter(procs).items()),
                "", "",
            )

# ───────────────────────────── CLI build ────────────────────────────
@app.callback()
def build(
    ctx: typer.Context,
    files: List[Path] = typer.Argument(..., exists=True),
    out: Path = typer.Option(Path("consensus.json"), "--out"),
    disagreements: Optional[Path] = typer.Option(None, "--disagreements"),
    min_node_support: int = typer.Option(3, "--min-node-support"),
    min_edge_support: int = typer.Option(3, "--min-edge-support"),
    review_threshold: int = typer.Option(2, "--review-threshold"),
):
    runs = [_load_run(p) for p in files]
    if len(runs) < 2:
        raise typer.Exit(code=1, message="[error] Need at least two run files.")

    nodes_out, edges_out, n_sup, e_sup, n_stage, n_mat, e_proc = _build_consensus(
        runs, min_node_support, min_edge_support
    )

    # consensus JSON
    out.write_text(json.dumps({"nodes": nodes_out, "links": edges_out}, indent=2))
    typer.echo(f"Consensus JSON → {out}")

    # disagreements TSV
    dis_file = disagreements or out.with_suffix(".disagree")
    with dis_file.open("w") as fh:
        fh.write("type\tid\tsupport\tmajority_stage_or_process\tvariants\tmajority_material\tmaterial_variants\n")
        for row in _disagreement_rows(n_sup, e_sup, n_stage, n_mat, e_proc, review_threshold):
            fh.write("\t".join(map(str, row)) + "\n")
    typer.echo(f"Disagreements  → {dis_file}")

    # summary
    typer.echo("\nSummary\n-------")
    typer.echo(f"Runs provided: {len(runs)}")
    typer.echo(f"Unique nodes  : {len(n_sup)}")
    typer.echo(f"Unique edges  : {len(e_sup)}")
    typer.echo(f"Nodes kept    : {len(nodes_out)}   (leaf nodes exempt from threshold)")
    typer.echo(f"Edges kept    : {len(edges_out)}")
    typer.echo(
        f"Flagged for review (<{review_threshold} support): "
        f"{sum(1 for c in n_sup.values() if c < review_threshold)} nodes, "
        f"{sum(1 for c in e_sup.values() if c < review_threshold)} edges"
    )

# ────────────────────────── main entry point ───────────────────────
if __name__ == "__main__":
    app()
