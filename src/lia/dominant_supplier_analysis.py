#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Dict, Set, List
import typer
from rich.progress import track


app = typer.Typer(help="Analyze dominant suppliers and perform disruption propagation on a hypergraph network.")


def find_dominant_suppliers(materials: dict, year: int, threshold: float) -> Dict[str, Dict]:
    """
    Determine dominant suppliers based on export 'from' values for a given year.
    """
    dominant = {}
    for hs_code, mat in materials.items():
        exports = mat.get("exports", {})
        year_exports = exports.get(str(year)) or exports.get(int(year)) or []
        if not year_exports:
            continue

        supplier_totals: Dict[str, float] = {}
        for record in year_exports:
            supplier = record.get("from")
            value = record.get("value", 0)
            if supplier:
                supplier_totals[supplier] = supplier_totals.get(supplier, 0.0) + float(value)

        total_value = sum(supplier_totals.values())
        if total_value == 0:
            continue

        for supplier, val in supplier_totals.items():
            frac = val / total_value
            if frac >= threshold:
                dominant[hs_code] = {
                    "supplier": supplier,
                    "fraction": frac,
                    "total_exports": total_value,
                    "supplier_value": val,
                }
                break

    return dominant


def build_hypergraph(processes: dict):
    """
    Convert process definitions into a true hypergraph structure:
    process_id -> {inputs: set of hs_codes, outputs: set of hs_codes}
    """
    hyperedges = {}
    for pid, proc in processes.items():
        inputs, outputs = set(), set()
        for p in proc.get("precursors", []):
            if isinstance(p, dict) and "hs_code" in p:
                inputs.add(p["hs_code"])
        for p in proc.get("products", []):
            if isinstance(p, dict) and "hs_code" in p:
                outputs.add(p["hs_code"])
        if inputs or outputs:
            hyperedges[pid] = {"inputs": inputs, "outputs": outputs}
    return hyperedges


def propagate_disruptions(materials: dict, hyperedges: dict, removed: Set[str]) -> Set[str]:
    """
    Propagate disruptions through the hypergraph:
    - A process is disabled if any input is disrupted.
    - A material is disrupted if all processes producing it are disabled.
    """
    disrupted = set(removed)
    active_processes = set(hyperedges.keys())
    material_to_processes: Dict[str, Set[str]] = {}

    # Build reverse index: which processes produce each material
    for pid, edge in hyperedges.items():
        for m in edge["outputs"]:
            material_to_processes.setdefault(m, set()).add(pid)

    changed = True
    while changed:
        changed = False

        # Disable processes missing inputs
        for pid, edge in list(hyperedges.items()):
            if pid not in active_processes:
                continue
            if any(inp in disrupted for inp in edge["inputs"]):
                active_processes.remove(pid)
                changed = True

        # Disrupt materials that lost all producing processes
        for mat, producers in material_to_processes.items():
            if mat in disrupted:
                continue
            if all(p not in active_processes for p in producers):
                disrupted.add(mat)
                changed = True

    return disrupted


@app.command()
def analyze(
    network_file: Path = typer.Argument(..., help="Path to mapped_research_state.json"),
    threshold: float = typer.Option(0.75, help="Fraction threshold for dominant supplier"),
    year: int = typer.Option(2024, help="Year to analyze"),
    output: Path = typer.Option(None, help="Output JSON file (default: auto name)")
):
    """
    Identify dominant suppliers and propagate disruptions across a true hypergraph.
    """
    typer.echo(f"Loading network file: {network_file}")
    data = json.loads(network_file.read_text())

    materials = data.get("materials", {})
    processes = data.get("processes", {})
    hyperedges = build_hypergraph(processes)

    typer.echo(f"Constructed hypergraph with {len(materials)} materials and {len(hyperedges)} processes.")

    dominant = find_dominant_suppliers(materials, year, threshold)
    typer.echo(f"Found {len(dominant)} dominant-supplier materials (threshold={threshold:.2f}).")

    disrupted_results = {}
    for hs_code, info in track(dominant.items(), description="Propagating disruptions..."):
        disrupted = propagate_disruptions(materials, hyperedges, {hs_code})
        disrupted_results[hs_code] = {
            **info,
            "disrupted_materials": sorted(list(disrupted)),
        }

    if output is None:
        output = network_file.parent / f"dominant_supplier_hypergraph_analysis_{year}.json"

    with open(output, "w") as f:
        json.dump(disrupted_results, f, indent=2)

    typer.echo(f"✅ Analysis complete. Results written to {output}")


if __name__ == "__main__":
    app()

