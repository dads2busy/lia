#!/usr/bin/env python3
"""
Analyze and visualize a bottom-up supply-chain directed hypergraph using XGI + NetworkX.

Features:
- Full analytics: degree, reachability, flow, edge betweenness, connectivity, JSON metrics
- Nodes labeled by HS code (inside node)
- Node color determined by HS section (official ranges and colors provided)
- Bold border for mined materials; process nodes get dashed borders and label 'P'
- Legend lists each HS category ONCE (e.g., 'MINERAL PRODUCTS (25–27)')
- Kamada–Kawai layout (fallback to spring) to reduce label overlap
"""

import argparse, json, requests, xgi, networkx as nx, matplotlib.pyplot as plt
from urllib.parse import urlparse
from pathlib import Path
from statistics import mean
from datetime import datetime
import numpy as np
from collections import OrderedDict
import matplotlib.patches as mpatches

# --------------------------- HS SECTION MAP ---------------------------------
# Using the exact ranges and colors you provided
HS_SECTIONS = [
    { "section": 1,  "hs_codes": [1,5],   "name": "LIVE ANIMALS; ANIMAL PRODUCTS", "color": "#1F77B4" },
    { "section": 2,  "hs_codes": [6,14],  "name": "VEGETABLE PRODUCTS", "color": "#FF7F0E" },
    { "section": 3,  "hs_codes": [15,15], "name": "ANIMAL OR VEGETABLE FATS AND OILS", "color": "#2CA02C" },
    { "section": 4,  "hs_codes": [16,24], "name": "PREPARED FOODSTUFFS; BEVERAGES; TOBACCO", "color": "#D62728" },
    { "section": 5,  "hs_codes": [25,27], "name": "MINERAL PRODUCTS", "color": "#A9A9A9" },
    { "section": 6,  "hs_codes": [28,38], "name": "PRODUCTS OF THE CHEMICAL OR ALLIED INDUSTRIES", "color": "#008000" },
    { "section": 7,  "hs_codes": [39,40], "name": "PLASTICS AND ARTICLES THEREOF; RUBBER", "color": "#FFA500" },
    { "section": 8,  "hs_codes": [41,43], "name": "RAW HIDES AND SKINS, LEATHER, FURSKINS", "color": "#7F7F7F" },
    { "section": 9,  "hs_codes": [44,46], "name": "WOOD AND ARTICLES OF WOOD; BASKETWARE", "color": "#BCBD22" },
    { "section": 10, "hs_codes": [47,49], "name": "PULP, PAPER, PAPERBOARD; ARTICLES THEREOF", "color": "#17BECF" },
    { "section": 11, "hs_codes": [50,63], "name": "TEXTILES AND TEXTILE ARTICLES", "color": "#AEC7E8" },
    { "section": 12, "hs_codes": [64,67], "name": "FOOTWEAR, HEADGEAR, UMBRELLAS, ETC.", "color": "#FFBB78" },
    { "section": 13, "hs_codes": [68,70], "name": "ARTICLES OF STONE, CERAMIC PRODUCTS, GLASSWARE", "color": "#D3D3D3" },
    { "section": 14, "hs_codes": [71,71], "name": "PRECIOUS METALS, STONES, JEWELLERY", "color": "#FF9896" },
    { "section": 15, "hs_codes": [72,83], "name": "BASE METALS AND ARTICLES OF BASE METAL", "color": "#87CEEB" },
    { "section": 16, "hs_codes": [84,85], "name": "MACHINERY & ELECTRICAL EQUIPMENT", "color": "#C49C94" },
    { "section": 17, "hs_codes": [86,89], "name": "TRANSPORTATION EQUIPMENT", "color": "#F7B6D2" },
    { "section": 18, "hs_codes": [90,92], "name": "PRECISION / MEDICAL / OPTICAL INSTRUMENTS", "color": "#C7C7C7" },
    { "section": 19, "hs_codes": [93,93], "name": "ARMS AND AMMUNITION", "color": "#DBDB8D" },
    { "section": 20, "hs_codes": [94,96], "name": "MISCELLANEOUS MANUFACTURED ARTICLES", "color": "#9EDAE5" },
    { "section": 21, "hs_codes": [97,97], "name": "WORKS OF ART, COLLECTORS’ PIECES AND ANTIQUES", "color": "#FF7F50" },
]

def section_for_prefix(prefix):
    """Return the HS section dict matching a 2-digit prefix."""
    for sec in HS_SECTIONS:
        lo, hi = sec["hs_codes"]
        if lo <= prefix <= hi:
            return sec
    return None

def color_for_hscode(hscode):
    """Return (color, legend_label) for a given HS code string/number."""
    try:
        prefix = int(str(hscode)[:2])
    except Exception:
        return ("#CCCCCC", None)  # Unknown/no HS code
    sec = section_for_prefix(prefix)
    if not sec:
        return ("#CCCCCC", None)
    label = f"{sec['name']} ({sec['hs_codes'][0]:02d}–{sec['hs_codes'][1]:02d})"
    return (sec["color"], label)

# ------------------------------ I/O -----------------------------------------

def load_json(src):
    if urlparse(src).scheme in ("http", "https"):
        print(f"Fetching {src} ...")
        r = requests.get(src); r.raise_for_status()
        return r.json()
    return json.loads(Path(src).read_text())

def extract_material_name(m):
    if isinstance(m, dict):
        return m.get("id") or m.get("name") or m.get("label") or str(m)
    return str(m)

# -------------------------- Build DiHypergraph ------------------------------

def build_dihypergraph(data):
    processes = data.get("processes", data)
    H = xgi.DiHypergraph()
    tails, heads = {}, {}
    skipped = 0
    for pid, proc in processes.items():
        prec = [extract_material_name(x) for x in proc.get("precursors", []) if x]
        prod = [extract_material_name(x) for x in proc.get("products", []) if x]
        if not prec and not prod:
            skipped += 1
            continue
        H.add_edge((prec, prod))
        tails[pid], heads[pid] = prec, prod
    if skipped:
        print(f"⚠️  Skipped {skipped} empty processes.")
    return H, tails, heads

# ------------------------- Directed Projection ------------------------------

def directed_projection(H, tails, heads):
    """
    Build a bipartite-like directed projection including:
    - material -> process edges for all precursors
    - process -> material edges for all products
    This preserves both input and output directionality.
    """
    G = nx.DiGraph()

    for pid in set(tails.keys()) | set(heads.keys()):
        precursors = tails.get(pid, [])
        products = heads.get(pid, [])

        # Connect precursor materials to the process node
        for u in precursors:
            if u:
                G.add_edge(u, pid, relation="precursor_to_process")

        # Connect process node to product materials
        for v in products:
            if v:
                G.add_edge(pid, v, relation="process_to_product")

    return G

# -------------------------- Plot Helper -------------------------------------

def plot_hist(data, bins, xlabel, ylabel, title, out_path, color="steelblue"):
    vals = list(data)
    plt.figure(figsize=(8,5))
    plt.hist(vals, bins=bins, color=color, alpha=0.7)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved: {out_path}")

def summarize_distribution(values, num_bins=20):
    values = list(values)
    if not values:
        return {"bins": [], "counts": [], "min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0}
    hist, bin_edges = np.histogram(values, bins=num_bins)
    return {
        "bins": [float(x) for x in bin_edges.tolist()],
        "counts": [int(x) for x in hist.tolist()],
        "min": float(min(values)),
        "max": float(max(values)),
        "mean": float(mean(values)),
        "median": float(np.median(values)),
    }

# ----------------------------- Analyses -------------------------------------

def degree_analysis(G, out_prefix, metrics):
    print("\n=== Degree Distribution ===")
    in_deg = [d for _, d in G.in_degree()]
    out_deg = [d for _, d in G.out_degree()]
    total_deg = [a + b for a, b in zip(in_deg, out_deg)]

    metrics["avg_in_degree"] = mean(in_deg) if in_deg else 0
    metrics["avg_out_degree"] = mean(out_deg) if out_deg else 0
    metrics["avg_total_degree"] = mean(total_deg) if total_deg else 0
    metrics["in_degree_distribution"] = summarize_distribution(in_deg)
    metrics["out_degree_distribution"] = summarize_distribution(out_deg)
    metrics["total_degree_distribution"] = summarize_distribution(total_deg)

    max_deg = max(max(in_deg or [0]), max(out_deg or [0]))
    deg_values = list(range(0, max_deg + 1))
    in_counts = [in_deg.count(k) for k in deg_values]
    out_counts = [out_deg.count(k) for k in deg_values]

    x = np.arange(len(deg_values))
    width = 0.4
    plt.figure(figsize=(9,6))
    plt.bar(x - width/2, in_counts, width=width, color='orange', alpha=0.7, label='In-degree')
    plt.bar(x + width/2, out_counts, width=width, color='teal', alpha=0.7, label='Out-degree')
    plt.xlabel("Degree value"); plt.ylabel("Node count")
    plt.title("In-Degree vs Out-Degree Distribution (Raw Counts)")
    plt.legend(); plt.xticks(x, deg_values)
    plt.tight_layout(); plt.savefig(f"{out_prefix}_degree_comparison.png", dpi=150); plt.close()

    plot_hist(total_deg, 30, "Total degree", "Frequency",
              "Total Degree Distribution", f"{out_prefix}_total_degree_hist.png", color="purple")

def reachability_analysis(G, out_prefix, metrics):
    print("\n=== Reachability Analysis ===")
    if G.number_of_edges() == 0:
        print("⚠️  No edges to analyze reachability."); return

    out_reach = {n: len(nx.descendants(G, n)) for n in G.nodes()}
    in_reach  = {n: len(nx.ancestors(G,  n)) for n in G.nodes()}

    metrics["avg_downstream_reach"]     = float(mean(out_reach.values())) if out_reach else 0.0
    metrics["avg_upstream_reach"]       = float(mean(in_reach.values()))  if in_reach  else 0.0
    metrics["out_reach_distribution"]   = summarize_distribution(out_reach.values(), 30)
    metrics["in_reach_distribution"]    = summarize_distribution(in_reach.values(), 30)

    plot_hist(out_reach.values(), 30, "Downstream reach", "Frequency",
              "Distribution of Out-Reachability", f"{out_prefix}_reach_out_hist.png")
    plot_hist(in_reach.values(), 30, "Upstream reach", "Frequency",
              "Distribution of In-Reachability", f"{out_prefix}_reach_in_hist.png")

def flow_and_betweenness_analysis(G, out_prefix, metrics):
    print("\n=== Flow & Edge Betweenness Centrality ===")
    if G.number_of_edges() == 0:
        print("⚠️  No edges to analyze."); return

    edge_bw = nx.edge_betweenness_centrality(G, normalized=True)
    bw_values = list(edge_bw.values())
    metrics["avg_edge_betweenness"]          = float(mean(bw_values)) if bw_values else 0.0
    metrics["edge_betweenness_distribution"] = summarize_distribution(bw_values, 30)
    plot_hist(bw_values, 30, "Edge Betweenness Centrality", "Frequency",
              "Edge Betweenness Distribution", f"{out_prefix}_edge_bw_hist.png", color="green")

    flow_centrality = {n: float(G.in_degree(n) * G.out_degree(n)) for n in G.nodes()}
    flow_vals = list(flow_centrality.values())
    metrics["avg_flow_centrality"]           = float(mean(flow_vals)) if flow_vals else 0.0
    metrics["flow_centrality_distribution"]  = summarize_distribution(flow_vals, 30)
    plot_hist(flow_vals, 30, "Flow Centrality", "Frequency",
              "Node Flow Centrality Distribution", f"{out_prefix}_flow_centrality_hist.png", color="red")

def advanced_network_measures(G, metrics):
    print("\n=== Advanced Network Measures ===")
    if G.number_of_nodes() == 0:
        print("⚠️  Empty projection, skipping advanced measures.")
        return
    try:
        metrics["density"]     = float(nx.density(G))
        metrics["reciprocity"] = float(nx.reciprocity(G)) if G.number_of_edges() > 0 else 0.0
    except Exception:
        pass

    if nx.is_empty(G):
        return
    largest_wcc = max(nx.weakly_connected_components(G), key=len)
    subG = G.subgraph(largest_wcc).copy()

    try:
        if nx.is_strongly_connected(subG):
            metrics["avg_path_length"] = float(nx.average_shortest_path_length(subG))
            metrics["diameter"]        = int(nx.diameter(subG))
        else:
            und = subG.to_undirected()
            if nx.is_connected(und):
                metrics["avg_path_length"] = float(nx.average_shortest_path_length(und))
                metrics["diameter"]        = int(nx.diameter(und))
    except Exception:
        pass

    try:
        metrics["clustering_coefficient"] = float(nx.average_clustering(subG.to_undirected()))
    except Exception:
        pass

# ----------------------- Directed Connectivity ------------------------------

def directed_connectivity_section(G, metrics):
    print("\n=== Directed Connectivity ===")
    dc = {}
    if G.number_of_edges() == 0:
        print("⚠️  No directed edges found; skipping connectivity.")
        metrics["directed_connectivity"] = {"has_edges": False}
        return

    dc["has_edges"]          = True
    dc["num_nodes"]          = G.number_of_nodes()
    dc["num_edges"]          = G.number_of_edges()

    weak_components = list(nx.weakly_connected_components(G))
    strong_components = list(nx.strongly_connected_components(G))
    dc["num_weak_components"]   = len(weak_components)
    dc["num_strong_components"] = len(strong_components)
    dc["largest_weak_size"]     = int(len(max(weak_components, key=len))) if weak_components else 0
    dc["largest_strong_size"]   = int(len(max(strong_components, key=len))) if strong_components else 0

    print(f"Directed projection: {dc['num_nodes']} nodes, {dc['num_edges']} edges")
    print(f"Weakly connected components: {dc['num_weak_components']} | Largest: {dc['largest_weak_size']}")
    print(f"Strongly connected components: {dc['num_strong_components']} | Largest: {dc['largest_strong_size']}")
    metrics["directed_connectivity"] = dc

# ----------------------- Visualization (HS-based) ---------------------------

def build_material_lookup(data):
    """Map any of id/name/label -> material record for robust matching."""
    lookup = {}
    if data and "materials" in data:
        for m in data["materials"].values():
            for key in (m.get("id"), m.get("name"), m.get("label")):
                if key:
                    lookup[key] = m
    return lookup

def _point_radius_to_data(ax, size_pts2):
    """
    Convert a node size given in points^2 (as used by nx.draw) to a radius in data units,
    for drawing dashed-border process nodes via patches.
    """
    r_pts = np.sqrt(size_pts2 / np.pi)  # radius in points
    fig = ax.figure
    r_px = r_pts * (fig.dpi / 72.0)     # points -> pixels

    # use plot center as reference for an approximately correct conversion
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    base = np.array([(x0 + x1) / 2.0, (y0 + y1) / 2.0])
    base_disp = ax.transData.transform(base)
    dx_disp = base_disp + np.array([r_px, 0.0])
    dy_disp = base_disp + np.array([0.0, r_px])
    dx_data = ax.transData.inverted().transform(dx_disp)[0] - base[0]
    dy_data = ax.transData.inverted().transform(dy_disp)[1] - base[1]
    return float(min(abs(dx_data), abs(dy_data)))

def visualize(H, tails, heads, outpath, data=None):
    """
    Visualize the directed projection:
    - Materials: colored by HS section, label = HS code, mined => bold border
    - Processes (no HS code): dashed border, label 'P'
    - Materials are drawn on top of processes
    - Process nodes are semi-transparent (50% opacity)
    - Layout: hybrid spring + Kamada–Kawai with adjustable SPREAD_FACTOR
    """

    # ---------------------- Layout tuning ----------------------
    SPREAD_FACTOR = 5.0   # Increase to spread nodes further apart (default ~1.8)
    KK_SCALE = 2.0        # Additional scale for Kamada–Kawai refinement
    KK_ITER = 300         # Iterations for refinement
    # ------------------------------------------------------------

    G = directed_projection(H, tails, heads)
    if G.number_of_edges() == 0:
        print("⚠️  No edges to visualize.")
        return

    material_lookup = build_material_lookup(data)

    material_nodes, process_nodes = [], []
    material_colors, material_edgecolors, material_lws, material_labels = [], [], [], {}
    mined_nodes = set()

    MATERIAL_NODE_SIZE = 1000
    PROCESS_NODE_SIZE = 500

    present_categories = OrderedDict()

    # ---------------------- Build styling info ----------------------
    for n in G.nodes():
        m = material_lookup.get(n)
        if m:
            # Material node
            hs_code = m.get("hs_code", None)
            mined = bool(m.get("mined", False))
            color, legend_label = color_for_hscode(hs_code)
            material_nodes.append(n)
            material_colors.append(color)
            material_edgecolors.append("black" if mined else "gray")
            material_lws.append(2.6 if mined else 1.0)
            label_text = str(hs_code) if hs_code else ""
            material_labels[n] = label_text
            if mined: mined_nodes.add(n)
            if legend_label and legend_label not in present_categories:
                present_categories[legend_label] = color
        else:
            # Process node
            process_nodes.append(n)

    # ---------------------- Layout computation ----------------------
    try:
        init_pos = nx.spring_layout(
            G,
            k=SPREAD_FACTOR / np.sqrt(max(1, len(G.nodes()))),
            iterations=250,
            seed=42,
        )
        pos = nx.kamada_kawai_layout(G, pos=init_pos, scale=KK_SCALE)
    except Exception:
        pos = nx.spring_layout(
            G,
            k=(SPREAD_FACTOR * 1.5) / np.sqrt(max(1, len(G.nodes()))),
            iterations=300,
            seed=42,
        )
    # ------------------------------------------------------------

    fig, ax = plt.subplots(figsize=(14, 12))
    ax.set_aspect('equal', adjustable='datalim')
    # Edges first

        # ---------------------- Draw directed edges (with arrows) ----------------------
    nx.draw_networkx_edges(
        G,
        pos,
        ax=ax,
        arrows=True,
        arrowstyle='-|>',      # clean arrowhead
        arrowsize=12,          # moderate arrow size
        connectionstyle="arc3,rad=0.08",  # slight curvature to reduce overlap
        edge_color='gray',
        width=0.8,
        alpha=0.4,
        min_source_margin=8,   # leave small gaps from node centers
        min_target_margin=8,
    )


    # ---------------------- Draw process nodes (bottom layer, dotted border) ----------------------
    if process_nodes:
        r_data = _point_radius_to_data(ax, PROCESS_NODE_SIZE)

        for n in process_nodes:
            x, y = pos[n]
            circ = mpatches.Circle(
                (x, y),
                r_data,
                facecolor="#FFFFFF",
                edgecolor="gray",
                linewidth=1.5,
                alpha=0.5,             # 50% opacity
                linestyle=(0, (4, 2)),
                zorder=1               # draw behind material nodes
            )
            ax.add_patch(circ)

            # Add "P" label manually with low zorder (below material nodes)
            ax.text(
                x, y, "P",
                fontsize=9,
                ha='center', va='center',
                color='black',
                alpha=0.7,
                zorder=2               # still above the circle, but below material nodes
            )

    # ---------------------- Draw material nodes (on top layer) ----------------------
    if material_nodes:
        nx.draw_networkx_nodes(
            G, pos, nodelist=material_nodes, node_size=MATERIAL_NODE_SIZE,
            node_color=material_colors, edgecolors=material_edgecolors,
            linewidths=material_lws, alpha=0.95, ax=ax
        )
        nx.draw_networkx_labels(G, pos, labels=material_labels,
                                font_size=8, font_color="black", ax=ax)

    # ---------------------- Legend ----------------------
    legend_handles = [
        mpatches.Patch(facecolor=color, edgecolor='black', label=label)
        for label, color in present_categories.items()
    ]
    if process_nodes:
        legend_handles.append(
            mpatches.Patch(facecolor="#FFFFFF", edgecolor="gray",
                           label="Process (no HS code)", linestyle=(0, (4, 2)), alpha=0.5)
        )

    if legend_handles:
        ax.legend(handles=legend_handles, loc="upper right", fontsize=7,
                  title="Categories", frameon=True)

    ax.set_title("Bottom-Up Supply-Chain Network\n(HS-code Nodes, Category Colors, Bold=MINED, Dashed=P, Semi-transparent=Process)")
    ax.axis("off")
    plt.tight_layout()
    fig.savefig(outpath, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"Saved visualization to {outpath}")

# ---------------------------- Orchestration ---------------------------------

def analyze(H, tails, heads, out_prefix):
    print("\n=== Network Summary ===")
    metrics = {
        "timestamp": datetime.now().isoformat(),
        "num_materials": H.num_nodes,
        "num_processes": H.num_edges,
    }
    print(f"Nodes (materials): {H.num_nodes}")
    print(f"Hyperedges (processes): {H.num_edges}")

    # Build directed projection once
    G = directed_projection(H, tails, heads)

    # Connectivity & metrics
    directed_connectivity_section(G, metrics)
    degree_analysis(G, out_prefix, metrics)
    reachability_analysis(G, out_prefix, metrics)
    flow_and_betweenness_analysis(G, out_prefix, metrics)
    advanced_network_measures(G, metrics)

    # Save metrics JSON
    json_path = f"{out_prefix}_metrics.json"
    with open(json_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nSaved metrics JSON: {json_path}")

    return metrics

# --------------------------------- CLI --------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="Path or URL to research_state.json")
    ap.add_argument("--out-prefix", required=True, help="Output prefix for plots/json (no extension)")
    args = ap.parse_args()

    data = load_json(args.source)
    H, tails, heads = build_dihypergraph(data)
    analyze(H, tails, heads, args.out_prefix)
    visualize(H, tails, heads, f"{args.out_prefix}_network.png", data)

if __name__ == "__main__":
    main()

