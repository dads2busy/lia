#!/usr/bin/env python3
import typer
import networkx as nx
import json
from typing import Optional
from enum import Enum

app = typer.Typer(help="Random Graph Generator CLI using NetworkX and Typer")

class OutputFormat(str, Enum):
    edgelist = "edgelist"
    adjlist = "adjlist"
    gml = "gml"
    graphml = "graphml"
    json = "json"

    @classmethod
    def _missing_(cls, value):
        # Allow case-insensitive matching for enum members
        for member in cls:
            if member.value.lower() == value.lower():
                return member
        return None

def write_graph(G: nx.Graph, output: str, fmt: str):
    """
    Write the graph G to the file `output` in the chosen format.
    Supported formats: edgelist, adjlist, gml, graphml, json.
    """
    if fmt == "edgelist":
        nx.write_edgelist(G, output)
    elif fmt == "adjlist":
        nx.write_adjlist(G, output)
    elif fmt == "gml":
        nx.write_gml(G, output)
    elif fmt == "graphml":
        nx.write_graphml(G, output)
    elif fmt == "json":
        with open(output, "w") as f:
            json.dump(nx.node_link_data(G), f)
    else:
        typer.echo(f"Unsupported format: {fmt}")

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    Random Graph Generator CLI using NetworkX and Typer.

    Use one of the subcommands below to generate a random graph.
    """
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

@app.command()
def erdos_renyi(
    n: int = typer.Option(..., help="Number of nodes"),
    p: float = typer.Option(..., help="Probability for edge creation (0 <= p <= 1)"),
    seed: Optional[int] = typer.Option(None, help="Random seed"),
    directed: bool = typer.Option(False, help="Generate a directed graph"),
    output: Optional[str] = typer.Option(None, help="Output file path"),
    output_format: OutputFormat = typer.Option(
        OutputFormat.edgelist,
        help="Output format",
        show_default=True,
    )
):
    """
    Generate an Erdős–Rényi random graph.
    """
    G = nx.erdos_renyi_graph(n, p, seed=seed, directed=directed)
    if output:
        write_graph(G, output, output_format.value)
        typer.echo(f"Graph saved to '{output}' in {output_format.value} format.")
    else:
        typer.echo("Nodes:")
        typer.echo(list(G.nodes()))
        typer.echo("Edges:")
        typer.echo(list(G.edges()))

@app.command()
def watts_strogatz(
    n: int = typer.Option(..., help="Number of nodes"),
    k: int = typer.Option(..., help="Each node is joined with its k nearest neighbors (k must be even)"),
    p: float = typer.Option(..., help="Probability of rewiring each edge"),
    seed: Optional[int] = typer.Option(None, help="Random seed"),
    output: Optional[str] = typer.Option(None, help="Output file path"),
    output_format: OutputFormat = typer.Option(
        OutputFormat.edgelist,
        help="Output format",
        show_default=True,
    )
):
    """
    Generate a Watts–Strogatz small‑world graph.
    """
    if k % 2 != 0:
        typer.echo("Error: k must be even for Watts–Strogatz graphs.", err=True)
        raise typer.Exit(code=1)
    G = nx.watts_strogatz_graph(n, k, p, seed=seed)
    if output:
        write_graph(G, output, output_format.value)
        typer.echo(f"Graph saved to '{output}' in {output_format.value} format.")
    else:
        typer.echo("Nodes:")
        typer.echo(list(G.nodes()))
        typer.echo("Edges:")
        typer.echo(list(G.edges()))

@app.command()
def barabasi_albert(
    n: int = typer.Option(..., help="Number of nodes"),
    m: int = typer.Option(..., help="Number of edges to attach from a new node to existing nodes"),
    seed: Optional[int] = typer.Option(None, help="Random seed"),
    output: Optional[str] = typer.Option(None, help="Output file path"),
    output_format: OutputFormat = typer.Option(
        OutputFormat.edgelist,
        help="Output format",
        show_default=True,
    )
):
    """
    Generate a Barabási–Albert preferential attachment graph.
    """
    G = nx.barabasi_albert_graph(n, m, seed=seed)
    if output:
        write_graph(G, output, output_format.value)
        typer.echo(f"Graph saved to '{output}' in {output_format.value} format.")
    else:
        typer.echo("Nodes:")
        typer.echo(list(G.nodes()))
        typer.echo("Edges:")
        typer.echo(list(G.edges()))

@app.command()
def random_regular(
    n: int = typer.Option(..., help="Number of nodes"),
    d: int = typer.Option(..., help="Degree for each node (must be feasible)"),
    seed: Optional[int] = typer.Option(None, help="Random seed"),
    output: Optional[str] = typer.Option(None, help="Output file path"),
    output_format: OutputFormat = typer.Option(
        OutputFormat.edgelist,
        help="Output format",
        show_default=True,
    )
):
    """
    Generate a random d-regular graph.
    """
    try:
        G = nx.random_regular_graph(d, n, seed=seed)
    except nx.NetworkXError as e:
        typer.echo(f"Error generating random regular graph: {e}", err=True)
        raise typer.Exit(code=1)
    if output:
        write_graph(G, output, output_format.value)
        typer.echo(f"Graph saved to '{output}' in {output_format.value} format.")
    else:
        typer.echo("Nodes:")
        typer.echo(list(G.nodes()))
        typer.echo("Edges:")
        typer.echo(list(G.edges()))

@app.command()
def powerlaw_cluster(
    n: int = typer.Option(..., help="Number of nodes"),
    m: int = typer.Option(..., help="Number of edges to attach from a new node to existing nodes"),
    p: float = typer.Option(..., help="Probability of adding a triangle after adding a random edge"),
    seed: Optional[int] = typer.Option(None, help="Random seed"),
    output: Optional[str] = typer.Option(None, help="Output file path"),
    output_format: OutputFormat = typer.Option(
        OutputFormat.edgelist,
        help="Output format",
        show_default=True,
    )
):
    """
    Generate a powerlaw cluster graph (Holme–Kim model).
    """
    G = nx.powerlaw_cluster_graph(n, m, p, seed=seed)
    if output:
        write_graph(G, output, output_format.value)
        typer.echo(f"Graph saved to '{output}' in {output_format.value} format.")
    else:
        typer.echo("Nodes:")
        typer.echo(list(G.nodes()))
        typer.echo("Edges:")
        typer.echo(list(G.edges()))

@app.command()
def newman_watts_strogatz(
    n: int = typer.Option(..., help="Number of nodes"),
    k: int = typer.Option(..., help="Each node is joined with its k nearest neighbors (k must be even)"),
    p: float = typer.Option(..., help="Probability of adding a new edge for each edge"),
    seed: Optional[int] = typer.Option(None, help="Random seed"),
    output: Optional[str] = typer.Option(None, help="Output file path"),
    output_format: OutputFormat = typer.Option(
        OutputFormat.edgelist,
        help="Output format",
        show_default=True,
    )
):
    """
    Generate a Newman–Watts–Strogatz small‑world graph.
    """
    if k % 2 != 0:
        typer.echo("Error: k must be even for Newman–Watts–Strogatz graphs.", err=True)
        raise typer.Exit(code=1)
    G = nx.newman_watts_strogatz_graph(n, k, p, seed=seed)
    if output:
        write_graph(G, output, output_format.value)
        typer.echo(f"Graph saved to '{output}' in {output_format.value} format.")
    else:
        typer.echo("Nodes:")
        typer.echo(list(G.nodes()))
        typer.echo("Edges:")
        typer.echo(list(G.edges()))

if __name__ == "__main__":
    app()



# Create a python CLI script using typer and networkx.
# The purpose of the script is to generate random networks/graphs.
# the script should allow generation of all of the various forms of networks networkx and generate.
# The script should have options to control the various parameters such as number of nodes and edges.
# Other parameters that are available for the various networks should be allowed as well.