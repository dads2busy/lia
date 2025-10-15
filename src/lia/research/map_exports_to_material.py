#!/usr/bin/env python

import os
import json
import typer
import pyarrow as pa
import pyarrow.compute as pc
from pathlib import Path
from rich import print
from rich.progress import track

app = typer.Typer(help="Map trade flow data from Arrow files to materials in a research_state.json file.")


def load_arrow_table(path: str) -> pa.Table:
    """Load an Arrow file into memory."""
    with pa.memory_map(path, "r") as source:
        reader = pa.ipc.RecordBatchFileReader(source)
        return reader.read_all()


@app.command()
def main(
    arrow_files: list[Path] = typer.Argument(..., help="Paths to yearly trade Arrow files."),
    research_state: Path = typer.Option(None, help="Path to research_state.json (default from $LIA_RESEARCH_FOLDER)."),
    partner_file: Path = typer.Option("/project/bi_dpi/data/UN_Comtrade/partnerAreas.arrow", help="Path to partner areas Arrow file."),
    output_file: Path = typer.Option(None, help="Output file name (defaults to mapped_research_state.json in same folder)."),
):
    # Resolve research_state path
    if research_state is None:
        research_folder = Path(Path.home() / "lia_data")
        if "LIA_RESEARCH_FOLDER" in os.environ:
            research_folder = Path(os.environ["LIA_RESEARCH_FOLDER"])
        research_state = research_folder / "research_state.json"

    # Load research state
    print(f"[bold green]Reading research state from:[/bold green] {research_state}")
    with open(research_state) as f:
        state = json.load(f)

    output_path = output_file or (research_state.parent / "mapped_research_state.json")
    print(f"[bold green]Will write output to:[/bold green] {output_path}")

    # Load partner area mappings
    print(f"[bold green]Loading partner code map from:[/bold green] {partner_file}")
    partner_table = load_arrow_table(str(partner_file))
    partner_map = {
        row["PartnerCode"]: row["PartnerCodeIsoAlpha3"]
        for row in partner_table.to_pylist()
        if not row.get("isGroup", False)
    }

    # Load all arrow data, indexed by refYear
    year_tables = {}
    for arrow_file in arrow_files:
        table = load_arrow_table(str(arrow_file))
        if "refYear" not in table.column_names:
            print(f"[red]Warning: No 'refYear' column found in {arrow_file}[/red]")
            continue

        years_in_file = pc.unique(table["refYear"]).to_pylist()
        for year in years_in_file:
            filtered = table.filter(pc.equal(table["refYear"], year))
            print(f"[blue]Loaded {arrow_file} for year {year} with {filtered.num_rows} rows.[/blue]")
            year_tables[year] = filtered

    # Handle dict vs list materials
    materials_data = state.get("materials", {})
    if isinstance(materials_data, dict):
        materials_iter = materials_data.items()
    else:
        materials_iter = enumerate(materials_data)

    total_mapped = 0

    # Map exports to materials
    for key, mat in track(materials_iter, description="Mapping exports to materials..."):
        hs_code = mat.get("hs_code") or key  # dict keys are HS codes themselves
        if not hs_code:
            print(f"[yellow]Skipping material without HS code:[/yellow] {mat.get('name', '<unnamed>')}")
            continue

        exports = {}
        total_exports = {}

        for year, table in year_tables.items():
            try:
                mask = pc.equal(table["cmdCode"], str(hs_code))
                filtered = table.filter(mask)
            except Exception as e:
                print(f"[red]Error filtering data for year {year}, HS {hs_code}:[/red] {e}")
                continue

            if filtered.num_rows == 0:
                continue

            year_data = []
            for row in filtered.to_pylist():
                partner = row["partnerCode"]
                reporter = row["reporterCode"]
                val = row["value"]
                from_code = partner_map.get(partner, f"UNK_{partner}")
                to_code = partner_map.get(reporter, f"UNK_{reporter}")

                year_data.append({
                    "from": from_code,
                    "to": to_code,
                    "value": val
                })

            # Sort descending by trade value
            year_data.sort(key=lambda x: x["value"], reverse=True)

            if year_data:
                exports[str(year)] = year_data
                total_exports[str(year)] = sum(x["value"] for x in year_data)

        if exports:
            mat["exports"] = exports
            mat["total_exports"] = total_exports
            total_mapped += 1
            print(f"[green]Mapped exports for material:[/green] {hs_code}")
        else:
            print(f"[yellow]No export data found for material:[/yellow] {hs_code}")

    # Save updated research state
    with open(output_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"[bold green]Done! {total_mapped} materials updated with export data.[/bold green]")
    print(f"[bold green]Output written to:[/bold green] {output_path}")


if __name__ == "__main__":
    app()

