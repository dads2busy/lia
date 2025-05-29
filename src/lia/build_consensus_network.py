"""consensus_generator.py
Build a robust consensus DAG from 7-10 independently generated JSON networks.

Run
---
python consensus_generator.py run1.json run2.json ... runN.json \
    --out consensus.json \
    --disagreements flagged.tsv

Key features
------------
* Drops orphaned nodes.
* Keeps dominant (`majority`) `stage`, `material`, `description` per node and
  flags `stage_consistent = False` when runs disagree on stage.
* Edge attribute `process` becomes a list of unique transformation strings.
* Adjustable support thresholds (node/edge) via CLI switches.
* **Disagreements TSV** now provides context: majority value and minority
  variants so experts can quickly see what differed.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import typer
import networkx as nx

app = typer.Typer(add_completion=False, invoke_without_command=True)

# ───────────────────────── I/O helper ──────────────────────────

def _load_graph(path: Path) -> nx.DiGraph:
    data = json.loads(path.read_text())
    if not {"nodes", "links"} <= data.keys():
        typer.echo(f"[error] {path} missing 'nodes' or 'links'", err=True)
        raise typer.Exit(1)

    G = nx.DiGraph()
    for n in data["nodes"]:
        G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in data["links"]:
        G.add_edge(
            e["source"],
            e["target"],
            **{k: v for k, v in e.items() if k not in {"source", "target"}},
        )
    return G

# ───────────────────── Consensus helpers ──────────────────────

def _collect_support_and_attrs(graphs: List[nx.DiGraph]):
    """Gather support counts and raw attribute lists."""
    n_sup: Dict[str, int] = Counter()
    e_sup: Dict[Tuple[str, str], int] = Counter()

    n_stages: Dict[str, List[str]] = defaultdict(list)
    n_mats: Dict[str, List[str]] = defaultdict(list)
    n_desc: Dict[str, List[str]] = defaultdict(list)
    e_proc: Dict[Tuple[str, str], List[str]] = defaultdict(list)

    for G in graphs:
        for nid, d in G.nodes(data=True):
            n_sup[nid] += 1
            n_stages[nid].append(d.get("stage", ""))
            n_mats[nid].append(d.get("material", ""))
            n_desc[nid].append(d.get("description", ""))
        for u, v, d in G.edges(data=True):
            e_sup[(u, v)] += 1
            if d.get("process"):
                e_proc[(u, v)].append(d["process"])
    return n_sup, e_sup, n_stages, n_mats, n_desc, e_proc


def _majority(values: List[str]) -> str:
    values = [v for v in values if v]
    return Counter(values).most_common(1)[0][0] if values else ""


def _consensus_graph(graphs: List[nx.DiGraph], min_node: int, min_edge: int):
    (
        n_sup,
        e_sup,
        n_stages,
        n_mats,
        n_desc,
        e_proc,
    ) = _collect_support_and_attrs(graphs)

    C = nx.DiGraph()

    # nodes
    for n, cnt in n_sup.items():
        if cnt >= min_node:
            stages = n_stages[n]
            stage_consistent = len(set(s.lower() for s in stages if s)) == 1
            C.add_node(
                n,
                support=cnt,
                stage=_majority(stages),
                material=_majority(n_mats[n]),
                description=_majority(n_desc[n]),
                stage_consistent=stage_consistent,
            )

    # edges
    for (u, v), cnt in e_sup.items():
        if cnt >= min_edge and u in C and v in C:
            C.add_edge(u, v, support=cnt, process=sorted(set(e_proc[(u, v)])))

    # drop orphaned nodes
    C.remove_nodes_from([n for n in C if C.degree(n) == 0])

    return C, n_sup, e_sup, n_stages, n_mats, n_desc, e_proc

# disagreement rows -----------------------------------------------------------

def _disagreement_rows(
    n_sup, e_sup, n_stages, n_mats, e_proc, threshold: int
):
    """Yield detailed rows for TSV."""
    # nodes first
    for nid, cnt in n_sup.items():
        if cnt >= threshold:
            continue
        stages = n_stages[nid]
        mats = n_mats[nid]
        maj_stage = _majority(stages)
        maj_mat = _majority(mats)
        stage_counts = Counter(s for s in stages if s)
        mat_counts = Counter(m for m in mats if m)
        stage_variants = ";".join(f"{s}:{c}" for s, c in stage_counts.items())
        mat_variants = ";".join(f"{m}:{c}" for m, c in mat_counts.items())
        yield (
            "node",
            nid,
            cnt,
            maj_stage,
            stage_variants,
            maj_mat,
            mat_variants,
        )
    # edges
    for (u, v), cnt in e_sup.items():
        if cnt >= threshold:
            continue
        procs = e_proc[(u, v)]
        maj_proc = _majority(procs)
        proc_counts = Counter(p for p in procs if p)
        proc_variants = ";".join(f"{p}:{c}" for p, c in proc_counts.items())
        yield (
            "edge",
            f"{u}->{v}",
            cnt,
            maj_proc,
            proc_variants,
            "",
            "",
        )

# ─────────────────────────┐ CLI build (default) ─────────────────────────────
@app.callback()
def build(
    ctx: typer.Context,
    files: List[Path] = typer.Argument(..., exists=True, dir_okay=False, help="Run JSONs to combine"),
    out: Path = typer.Option(Path("consensus.json"), "--out", help="Output consensus JSON"),
    disagreements: Optional[Path] = typer.Option(None, "--disagreements", help="Write TSV of low-support/variant elements"),
    min_node_support: int = typer.Option(3, "--min-node-support"),
    min_edge_support: int = typer.Option(3, "--min-edge-support"),
    review_threshold: int = typer.Option(2, "--review-threshold"),
):
    """Build consensus DAG from multiple run JSONs (default command)."""
    graphs = [_load_graph(p) for p in files]
    if len(graphs) < 2:
        typer.echo("[error] Need at least two run files.", err=True)
        raise typer.Exit(1)

    (
        C,
        n_sup,
        e_sup,
        n_stages,
        n_mats,
        n_desc,
        e_proc,
    ) = _consensus_graph(graphs, min_node_support, min_edge_support)

    out.write_text(json.dumps({
        "nodes": [{"id": n, **C.nodes[n]} for n in C.nodes()],
        "links": [{"source": u, "target": v, **C.edges[u, v]} for u, v in C.edges()],
    }, indent=2))
    typer.echo(f"Consensus written to {out}")

    # disagreements TSV with context
    if disagreements:
        with disagreements.open("w") as fh:
            fh.write("type\tid\tsupport\tmajority_stage_or_process\tvariants\tmajority_material\tmaterial_variants\n")
            for row in _disagreement_rows(
                n_sup, e_sup, n_stages, n_mats, e_proc, review_threshold
            ):
                fh.write("\t".join(map(str, row)) + "\n")
        typer.echo(f"Disagreements logged to {disagreements}")

    # summary
    total_nodes = len(set().union(*(g.nodes() for g in graphs)))
    total_edges = len(set().union(*(g.edges() for g in graphs)))
    typer.echo("\nSummary")
    typer.echo("-------")
    typer.echo(f"Runs provided: {len(graphs)}")
    typer.echo(f"Total unique nodes across runs: {total_nodes}")
    typer.echo(f"Total unique edges across runs: {total_edges}")
    typer.echo(f"Nodes kept in consensus: {C.number_of_nodes()}")
    typer.echo(f"Edges kept in consensus: {C.number_of_edges()}")
    low_n = sum(1 for c in n_sup.values() if c < review_threshold)
    low_e = sum(1 for c in e_sup.values() if c < review_threshold)
    typer.echo(f"Elements flagged for review: {low_n} nodes, {low_e} edges")

if __name__ == "__main__":
    app()