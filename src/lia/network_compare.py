# dag_compare_cli.py
"""Command‑line utilities for comparing and ranking material‑supply‑chain DAGs.

*Filtering option*
------------------
Both **similarity** and **rank** now accept a `--filter / --no-filter` flag
(default **on**). When filtering is on, *Product*‑stage nodes are ignored:
only nodes whose `stage` is `base chemical`, `mined`, or `refined` (case‑insensitive)
—and the edges between them—are considered.

Sub‑commands
```
similarity        → pair‑wise Jaccard matrices (toggle filtering)
consensus         → build union graph with support counts
rank              → score DAGs by consensus support (toggle filtering)
visualize         → save consensus heat‑map PNG
precision‑recall  → evaluate DAGs vs a gold‑standard reference
```
"""
from __future__ import annotations

import json
import itertools
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from collections import Counter

import matplotlib as mpl  # type: ignore
import matplotlib.pyplot as plt  # type: ignore
import networkx as nx  # type: ignore
import typer

app = typer.Typer(add_completion=False)

ALLOWED_STAGES: Set[str] = {"base chemical", "mined", "refined"}

# ──────────────────────────────────────────────────────────────────────────────
# I/O helpers
# ──────────────────────────────────────────────────────────────────────────────

def _load_graph(path: Path) -> nx.DiGraph:
    data = json.loads(path.read_text())
    if not {"nodes", "links"} <= data.keys():
        typer.echo(f"[error] {path} missing 'nodes' or 'links'", err=True)
        raise typer.Exit(1)
    G = nx.DiGraph()
    for n in data["nodes"]:
        G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in data["links"]:
        G.add_edge(e["source"], e["target"], **{k: v for k, v in e.items() if k not in {"source", "target"}})
    return G

# ──────────────────────────────────────────────────────────────────────────────
# Stage filtering utilities
# ──────────────────────────────────────────────────────────────────────────────

def _stage_nodes(G: nx.DiGraph) -> Set[str]:
    return {n for n, d in G.nodes(data=True) if d.get("stage", "").lower() in ALLOWED_STAGES}


def _filtered_node_edge_sets(G: nx.DiGraph):
    nodes = _stage_nodes(G)
    edges = {(u, v) for u, v in G.edges() if u in nodes and v in nodes}
    return nodes, edges

# ──────────────────────────────────────────────────────────────────────────────
# Similarity matrices
# ──────────────────────────────────────────────────────────────────────────────

def _jaccard(a: set, b: set) -> float:
    return 1.0 if (not a and not b) else len(a & b) / len(a | b)


def _pairwise_jaccard(graphs: List[nx.DiGraph], filtered: bool):
    n = len(graphs)
    node_mat = [[0.0] * n for _ in range(n)]
    edge_mat = [[0.0] * n for _ in range(n)]

    if filtered:
        node_sets, edge_sets = zip(*(_filtered_node_edge_sets(g) for g in graphs))
    else:
        node_sets = [set(g.nodes()) for g in graphs]
        edge_sets = [set(g.edges()) for g in graphs]

    for i, j in itertools.combinations(range(n), 2):
        node_mat[i][j] = node_mat[j][i] = _jaccard(node_sets[i], node_sets[j])
        edge_mat[i][j] = edge_mat[j][i] = _jaccard(edge_sets[i], edge_sets[j])
    for i in range(n):
        node_mat[i][i] = edge_mat[i][i] = 1.0
    return node_mat, edge_mat

# ──────────────────────────────────────────────────────────────────────────────
# Consensus / ranking helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_union_support(graphs: List[nx.DiGraph]):
    e_sup: Dict[Tuple[str, str], int] = {}
    n_sup: Dict[str, int] = {}
    for G in graphs:
        for u, v in G.edges():
            e_sup[(u, v)] = e_sup.get((u, v), 0) + 1
        for n in G.nodes():
            n_sup[n] = n_sup.get(n, 0) + 1
    return n_sup, e_sup


def _score_graph(G: nx.DiGraph, n_sup: Dict[str, int], e_sup: Dict[Tuple[str, str], int], filtered: bool):
    if filtered:
        nodes, edges = _filtered_node_edge_sets(G)
    else:
        nodes, edges = set(G.nodes()), set(G.edges())
    return sum(n_sup.get(n, 0) for n in nodes) + sum(e_sup.get(e, 0) for e in edges)

# ──────────────────────────────────────────────────────────────────────────────
# CLI commands
# ──────────────────────────────────────────────────────────────────────────────

@app.command()
def similarity(
    files: List[Path] = typer.Argument(..., exists=True, dir_okay=False),
    filter: bool = typer.Option(True, "--filter/--no-filter", help="Ignore Product-stage nodes when ON (default)."),
):
    """Pair‑wise Jaccard similarity (optionally ignoring Product nodes)."""
    graphs = [_load_graph(p) for p in files]
    node_mat, edge_mat = _pairwise_jaccard(graphs, filtered=filter)
    _fmt = lambda m: "\n".join("\t".join(f"{v:.3f}" for v in row) for row in m)
    label = "filtered" if filter else "all"
    typer.echo(f"Node Jaccard ({label}):\n" + _fmt(node_mat))
    typer.echo(f"\nEdge Jaccard ({label}):\n" + _fmt(edge_mat))


@app.command()
def consensus(
    files: List[Path] = typer.Argument(..., exists=True, dir_okay=False),
    out: Optional[Path] = typer.Option(None, "--out", help="Write union JSON here"),
):
    graphs = [_load_graph(p) for p in files]
    n_sup, e_sup = _build_union_support(graphs)
    U = nx.DiGraph()
    for n, s in n_sup.items():
        U.add_node(n, support=s)
    for (u, v), s in e_sup.items():
        U.add_edge(u, v, support=s)
    typer.echo(f"Union: {U.number_of_nodes()} nodes / {U.number_of_edges()} links")
    if out:
        out.write_text(json.dumps({
            "nodes": [{"id": n, **U.nodes[n]} for n in U.nodes()],
            "links": [{"source": u, "target": v, **U.edges[u, v]} for u, v in U.edges()],
        }, indent=2))
        typer.echo(f"Wrote {out}")


@app.command()
def rank(
    files: List[Path] = typer.Argument(..., exists=True, dir_okay=False),
    filter: bool = typer.Option(True, "--filter/--no-filter", help="Ignore Product-stage nodes when ON (default)."),
):
    """Rank DAGs by consensus support; optional Product-stage filtering."""
    graphs = [_load_graph(p) for p in files]
    n_sup, e_sup = _build_union_support(graphs)
    scores = [_score_graph(g, n_sup, e_sup, filtered=filter) for g in graphs]
    label = "(filtered)" if filter else "(all nodes)"
    typer.echo(f"Ranking {label}:")
    for i, (p, s) in enumerate(sorted(zip(files, scores), key=lambda kv: kv[1], reverse=True), 1):
        typer.echo(f"{i:2d}. {p.name}\t{s}")


@app.command(name="visualize")
def visualize(
    files: List[Path] = typer.Argument(..., exists=True, dir_okay=False),
    png: Path = typer.Option(Path("consensus.png"), "--png", help="PNG output file"),
):
    """Draw consensus graph with stage-colored nodes and visible arrowheads."""
    graphs = [_load_graph(p) for p in files]
    _, e_sup = _build_union_support(graphs)
    if not e_sup:
        typer.echo("[warning] No edges to visualize.")
        raise typer.Exit()

    # Build union graph (edge attribute “w” = support count)
    G = nx.DiGraph([(u, v, {"w": s}) for (u, v), s in e_sup.items()])
    for g in graphs:
        G.add_nodes_from(g.nodes(data=True))   # keep stage metadata

    # Stage → color mapping
    stages = sorted({G.nodes[n].get("stage", "Other") for n in G.nodes()})
    cmap = mpl.cm.get_cmap("tab10")
    stage_color = {st: mpl.colors.to_hex(cmap(i % 10)) for i, st in enumerate(stages)}
    node_colors = [stage_color[G.nodes[n].get("stage", "Other")] for n in G.nodes()]

    pos = nx.spring_layout(G, seed=42)
    node_size = 1400

    fig, ax = plt.subplots(figsize=(12, 10))

    # 1️⃣ draw nodes & labels (behind)
    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=node_size,
                           node_color=node_colors, edgecolors="black")
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=10)

    # 2️⃣ draw edges on top → arrowheads visible
    weights = [d["w"] for _, _, d in G.edges(data=True)]
    vmax = max(weights)
    nx.draw_networkx_edges(
        G, pos, ax=ax,
        arrows=True, arrowstyle="-|>", arrowsize=28,
        min_source_margin=15, min_target_margin=15,
        width=[2 * w / vmax for w in weights],
        edge_color=weights, edge_cmap=plt.cm.viridis,
    )

    # Stage legend at bottom
    legend_handles = [mpl.patches.Patch(color=col, label=st)
                      for st, col in stage_color.items()]
    ax.legend(handles=legend_handles, title="Stage",
              loc="upper center", bbox_to_anchor=(0.5, -0.08),
              ncol=len(stages))

    # Edge-support color-bar
    sm = mpl.cm.ScalarMappable(cmap=plt.cm.viridis,
                               norm=plt.Normalize(vmin=1, vmax=vmax))
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label="Link support (count)")

    ax.axis("off")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    typer.echo(f"Saved {png}")


@app.command("precision‑recall")
def precision_recall(
    files: List[Path] = typer.Argument(..., exists=True, dir_okay=False),
    reference: Path = typer.Option(..., "--reference", exists=True, dir_okay=False, help="Gold‑standard JSON"),
):
    """Compute precision / recall versus a reference network."""
    ref = _load_graph(reference)
    ref_edges = set(ref.edges())
    if not ref_edges:
        typer.echo("[error] Reference graph has no edges.", err=True)
        raise typer.Exit(1)
    for p in files:
        G = _load_graph(p)
        edges = set(G.edges())
        tp = len(edges & ref_edges)
        prec = tp / len(edges) if edges else float("nan")
        rec = tp / len(ref_edges)
        typer.echo(f"{p.name}\tprecision={prec:.3f}\trecall={rec:.3f}")

@app.command()
def coverage(
    files: List[Path] = typer.Argument(..., exists=True, dir_okay=False),
    filter: bool = typer.Option(False, "--filter/--no-filter", help="When ON, include only nodes in allowed stages"),
):
    """List every node‑ID and in how many supplied networks it appears."""
    graphs = [_load_graph(p) for p in files]
    counts: Counter[str] = Counter()
    for G in graphs:
        nodes = _stage_nodes(G) if filter else set(G.nodes())
        counts.update(nodes)

    typer.echo("Node ID	count")
    for node, cnt in counts.most_common():
        typer.echo(f"{node}	{cnt}")
        
if __name__ == "__main__":
    app()
