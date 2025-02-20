#!/usr/bin/env python3
import json
import os
from statistics import mean
from typing import Optional
import networkx as nx
import typer

app = typer.Typer(
    help="Network analysis tool using NetworkX with support for multiple file formats."
)

def detect_file_type(file_path: str) -> str:
    """
    Auto-detect the network file type by inspecting the file's content.
    Returns one of: "graphml", "gexf", "gml", "pajek", "adjlist", "json", or "edgelist".
    """
    try:
        with open(file_path, "r", errors="ignore") as f:
            head = f.read(2048)
    except Exception as e:
        typer.echo(f"Error reading file for type detection: {e}")
        return "edgelist"
    lower_head = head.lower()
    if "<graphml" in lower_head:
        return "graphml"
    elif "<gexf" in lower_head:
        return "gexf"
    elif lower_head.lstrip().startswith("graph ["):
        return "gml"
    elif "*vertices" in lower_head:
        return "pajek"
    elif lower_head.lstrip().startswith("{"):
        # Assume JSON in node-link format
        if '"nodes"' in lower_head and '"links"' in lower_head:
            return "json"
    # Fallback to checking the file extension:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".gml":
        return "gml"
    elif ext in [".graphml"]:
        return "graphml"
    elif ext in [".gexf"]:
        return "gexf"
    elif ext in [".pajek", ".net"]:
        return "pajek"
    elif ext in [".adjlist"]:
        return "adjlist"
    return "edgelist"

def load_graph(file_path: str, directed: Optional[bool], specified_file_type: Optional[str]) -> nx.Graph:
    """
    Load a graph from file_path.
    If specified_file_type is provided, it will be used directly; otherwise, auto-detection is used.
    The `directed` parameter forces the graph to be directed or undirected when applicable.
    """
    # Use user-specified file type if provided; otherwise, auto-detect.
    file_type = specified_file_type.lower() if specified_file_type else detect_file_type(file_path)
    try:
        if file_type == "graphml":
            G = nx.read_graphml(file_path)
        elif file_type == "gexf":
            G = nx.read_gexf(file_path)
        elif file_type == "gml":
            G = nx.read_gml(file_path)
        elif file_type == "pajek":
            G = nx.read_pajek(file_path)
        elif file_type == "adjlist":
            if directed is None:
                G = nx.read_adjlist(file_path)
            else:
                if directed:
                    G = nx.read_adjlist(file_path, create_using=nx.DiGraph())
                else:
                    G = nx.read_adjlist(file_path)
        elif file_type == "json":
            from networkx.readwrite import json_graph
            with open(file_path, "r") as f:
                data = json.load(f)
            G = json_graph.node_link_graph(data)
        else:  # edgelist (default)
            if directed is None:
                G = nx.read_edgelist(file_path, create_using=nx.DiGraph(), nodetype=str)
            else:
                if directed:
                    G = nx.read_edgelist(file_path, create_using=nx.DiGraph(), nodetype=str)
                else:
                    G = nx.read_edgelist(file_path, create_using=nx.Graph(), nodetype=str)
    except Exception as e:
        typer.echo(f"Error loading graph from file: {e}")
        raise typer.Exit(code=1)

    return [G, file_type]

@app.command()
def main(
    network_file: str = typer.Argument(..., help="Path to the network file."),
    directed: Optional[str] = typer.Option(
        None,
        "--directed",
        help=(
            "The network to be 'directed' or 'undirected'. "
            "E.g., use --directed=directed or --directed=undirected. "
            "If not provided, auto-detection is used (or the file's own properties if available)."
        ),
    ),
    file_type: Optional[str] = typer.Option(
        None,
        "--file-type",
        help=(
            "Specify the network file type explicitly. Supported types: "
            "graphml, gexf, gml, pajek, adjlist, json, edgelist. "
            "If provided, auto-detection is skipped."
        ),
    ),
    basic: bool = typer.Option(True, "--basic/--no-basic", help="Perform basic analysis."),
    scc: bool = typer.Option(True, "--scc/--no-scc", help="Analyze strongly connected components."),
    wcc: bool = typer.Option(True, "--wcc/--no-wcc", help="Analyze weakly connected components."),
    kcore: bool = typer.Option(True, "--kcore/--no-kcore", help="Analyze k-core decomposition."),
    indegree_stats: bool = typer.Option(
        True, "--indegree/--no-indegree", help="Analyze node in-degree statistics."
    ),
    outdegree_stats: bool = typer.Option(
        True, "--outdegree/--no-outdegree", help="Analyze node out-degree statistics."
    ),
    node_betweenness: bool = typer.Option(
        True, "--node-betweenness/--no-node-betweenness", help="Analyze node betweenness centrality."
    ),
    edge_betweenness: bool = typer.Option(
        True, "--edge-betweenness/--no-edge-betweenness", help="Analyze edge betweenness centrality."
    ),
    hub: bool = typer.Option(False, "--hub/--no-hub", help="Analyze HITS hub scores."),
    pagerank: bool = typer.Option(False, "--pagerank/--no-pagerank", help="Analyze PageRank scores."),
    eigenvector: bool = typer.Option(
        False, "--eigenvector/--no-eigenvector", help="Analyze eigenvector centrality."
    ),
):
    """
    Analyze a network file using NetworkX and output the results as JSON.

    The script auto-detects the file type (supported formats include GraphML, GEXF, GML,
    Pajek, Adjlist, JSON (node-link), and Edgelist) unless --file-type is specified.
    Optionally, use --force-directed to force the network to be treated as 'directed'
    or 'undirected'.
    """
    # Interpret the --directed option.
    if directed is not None:
        if directed.lower() in ["directed", "true", "yes", "1"]:
            directed = True
        elif directed.lower() in ["undirected", "false", "no", "0"]:
            directed = False
        else:
            typer.echo("Invalid value for --directed. Use 'directed' or 'undirected'.")
            raise typer.Exit(code=1)
    else:
        directed = None

    # Load the graph using the provided file type (if any) and force-directed option.
    [G, file_type] = load_graph(network_file, directed, file_type)

    results = {"file_type": file_type, "directed": G.is_directed()}

    # ---------------- Basic Analysis ----------------
    if basic:
        num_nodes = G.number_of_nodes()
        num_edges = G.number_of_edges()

        # Diameter is computed on the undirected version.
        
        ## check on this DJM
        UG = G.to_undirected()
        # UG=G
        if nx.is_connected(UG):
            diameter = nx.diameter(UG)
        else:
            largest_cc = max(nx.connected_components(UG), key=len)
            diameter = nx.diameter(UG.subgraph(largest_cc))

        # For connectivity, use weakly connected for directed graphs.
        is_weakly_connected = (
            nx.is_weakly_connected(G) if G.is_directed() else nx.is_connected(UG)
        )
        total_degrees = [d for _, d in G.degree()]
        avg_degree = mean(total_degrees) if total_degrees else 0
        min_degree = min(total_degrees) if total_degrees else 0
        max_degree = max(total_degrees) if total_degrees else 0

        results["basic"] = {
            "num_nodes": num_nodes,
            "num_edges": num_edges,
            "estimated_diameter": diameter,
            "is_weakly_connected": is_weakly_connected,
            "node_degree": {"average": avg_degree, "min": min_degree, "max": max_degree},
        }

    # ---------------- Strongly Connected Components ----------------
    if scc:
        DG = G.to_directed()
        scc_components = list(nx.strongly_connected_components(DG))
        total_scc = len(scc_components)
        scc_sizes = [len(comp) for comp in scc_components]
        if scc_sizes:
            smallest_size = min(scc_sizes)
            largest_size = max(scc_sizes)
            count_smallest = scc_sizes.count(smallest_size)
            count_largest = scc_sizes.count(largest_size)
            fraction_smallest = count_smallest / total_scc
            fraction_largest = count_largest / total_scc
        else:
            smallest_size = largest_size = count_smallest = count_largest = total_scc = 0
            fraction_smallest = fraction_largest = 0.0
        results["strongly_connected_components"] = {
            "total_components": total_scc,
            "smallest_component_size": smallest_size,
            "number_smallest_components": count_smallest,
            "largest_component_size": largest_size,
            "number_largest_components": count_largest,
            "fraction_smallest_components": fraction_smallest,
            "fraction_largest_components": fraction_largest,
        }

    # ---------------- Weakly Connected Components ----------------
    if wcc:
        if G.is_directed():
            wcc_components = list(nx.weakly_connected_components(G))
        else:
            wcc_components = list(nx.connected_components(G))
        total_wcc = len(wcc_components)
        wcc_sizes = [len(comp) for comp in wcc_components]
        if wcc_sizes:
            smallest_size = min(wcc_sizes)
            largest_size = max(wcc_sizes)
            count_smallest = wcc_sizes.count(smallest_size)
            count_largest = wcc_sizes.count(largest_size)
            fraction_smallest = count_smallest / total_wcc
            fraction_largest = count_largest / total_wcc
        else:
            smallest_size = largest_size = count_smallest = count_largest = total_wcc = 0
            fraction_smallest = fraction_largest = 0.0
        results["weakly_connected_components"] = {
            "total_components": total_wcc,
            "smallest_component_size": smallest_size,
            "number_smallest_components": count_smallest,
            "largest_component_size": largest_size,
            "number_largest_components": count_largest,
            "fraction_smallest_components": fraction_smallest,
            "fraction_largest_components": fraction_largest,
        }

    # ---------------- k-core Analysis ----------------
    if kcore:
        UG = G.to_undirected()
        try:
            core_numbers = nx.core_number(UG)
        except Exception as e:
            core_numbers = {}
        if core_numbers:
            core_vals = list(core_numbers.values())
            smallest_core = min(core_vals)
            largest_core = max(core_vals)
            count_smallest = core_vals.count(smallest_core)
            count_largest = core_vals.count(largest_core)
            total_nodes_core = len(core_vals)
            fraction_smallest = count_smallest / total_nodes_core
            fraction_largest = count_largest / total_nodes_core
        else:
            smallest_core = largest_core = count_smallest = count_largest = total_nodes_core = 0
            fraction_smallest = fraction_largest = 0.0
        results["kcore"] = {
            "smallest_kcore": smallest_core,
            "number_of_nodes_in_smallest_kcore": count_smallest,
            "fraction_of_nodes_in_smallest_kcore": fraction_smallest,
            "largest_kcore": largest_core,
            "number_of_nodes_in_largest_kcore": count_largest,
            "fraction_of_nodes_in_largest_kcore": fraction_largest,
        }

    # ---------------- Node In-Degree Analysis ----------------
    if indegree_stats:
        if G.is_directed():
            in_degrees = list(dict(G.in_degree()).values())
        else:
            in_degrees = list(dict(G.degree()).values())
        avg_in = mean(in_degrees) if in_degrees else 0
        min_in = min(in_degrees) if in_degrees else 0
        max_in = max(in_degrees) if in_degrees else 0
        results["node_in_degree"] = {"average": avg_in, "min": min_in, "max": max_in}

    # ---------------- Node Out-Degree Analysis ----------------
    if outdegree_stats:
        if G.is_directed():
            out_degrees = list(dict(G.out_degree()).values())
        else:
            out_degrees = list(dict(G.degree()).values())
        avg_out = mean(out_degrees) if out_degrees else 0
        min_out = min(out_degrees) if out_degrees else 0
        max_out = max(out_degrees) if out_degrees else 0
        results["node_out_degree"] = {"average": avg_out, "min": min_out, "max": max_out}

    # ---------------- Node Betweenness Centrality ----------------
    if node_betweenness:
        node_btw = nx.betweenness_centrality(G, normalized=False)
        node_btw_values = list(node_btw.values())
        avg_node_btw = mean(node_btw_values) if node_btw_values else 0
        min_node_btw = min(node_btw_values) if node_btw_values else 0
        max_node_btw = max(node_btw_values) if node_btw_values else 0
        results["node_betweenness_centrality"] = {
            "average": avg_node_btw,
            "min": min_node_btw,
            "max": max_node_btw,
        }

    # ---------------- Edge Betweenness Centrality ----------------
    if edge_betweenness:
        edge_btw = nx.edge_betweenness_centrality(G, normalized=False)
        edge_btw_values = list(edge_btw.values())
        avg_edge_btw = mean(edge_btw_values) if edge_btw_values else 0
        min_edge_btw = min(edge_btw_values) if edge_btw_values else 0
        max_edge_btw = max(edge_btw_values) if edge_btw_values else 0
        results["edge_betweenness_centrality"] = {
            "average": avg_edge_btw,
            "min": min_edge_btw,
            "max": max_edge_btw,
        }

    # ---------------- HITS Hub Score Analysis ----------------
    if hub:
        try:
            hubs, _ = nx.hits(G, max_iter=1000, normalized=True)
        except nx.PowerIterationFailedConvergence:
            largest_scc = max(nx.strongly_connected_components(G), key=len)
            hubs, _ = nx.hits(G.subgraph(largest_scc), max_iter=1000, normalized=True)
        hub_values = list(hubs.values())
        avg_hub = mean(hub_values) if hub_values else 0
        min_hub = min(hub_values) if hub_values else 0
        max_hub = max(hub_values) if hub_values else 0
        results["node_hub_score_hits"] = {"average": avg_hub, "min": min_hub, "max": max_hub}

    # ---------------- PageRank Analysis ----------------
    if pagerank:
        pr = nx.pagerank(G)
        pr_values = list(pr.values())
        avg_pr = mean(pr_values) if pr_values else 0
        min_pr = min(pr_values) if pr_values else 0
        max_pr = max(pr_values) if pr_values else 0
        results["node_page_rank"] = {"average": avg_pr, "min": min_pr, "max": max_pr}

    # ---------------- Eigenvector Centrality Analysis ----------------
    if eigenvector:
        try:
            ev = nx.eigenvector_centrality(G, max_iter=1000)
        except Exception:
            largest_scc = max(nx.strongly_connected_components(G), key=len)
            ev = nx.eigenvector_centrality(G.subgraph(largest_scc), max_iter=1000)
        ev_values = list(ev.values())
        avg_ev = mean(ev_values) if ev_values else 0
        min_ev = min(ev_values) if ev_values else 0
        max_ev = max(ev_values) if ev_values else 0
        results["node_eigenvector_centrality"] = {"average": avg_ev, "min": min_ev, "max": max_ev}

    # ---------------- Output the JSON results ----------------
    typer.echo(json.dumps(results, indent=4))

if __name__ == "__main__":
    app()
