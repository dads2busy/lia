import json
from pathlib import Path
from typing import List, Optional
import typer

app = typer.Typer()

@app.command()
def filter_networks(
    files: List[Path] = typer.Argument(..., exists=True, help="List of JSON files to process."),
    stages: str = typer.Option("product", help="Comma-separated list of node stages to filter out (case-insensitive)."),
    suffix: str = typer.Option("filtered", help="Suffix to append to output file names."),
):
    # Normalize filter stages to lowercase for comparison
    stage_filter = {s.strip().lower() for s in stages.split(",")}

    for file_path in files:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        original_node_count = len(data["nodes"])
        original_link_count = len(data["links"])

        # Filter nodes
        filtered_nodes = [
            node for node in data["nodes"]
            if node.get("stage", "").strip().lower() not in stage_filter
        ]
        retained_node_ids = {node["id"] for node in filtered_nodes}

        # Filter links where both source and target nodes still exist
        filtered_links = [
            link for link in data["links"]
            if link["source"] in retained_node_ids and link["target"] in retained_node_ids
        ]

        output_data = {
            "nodes": filtered_nodes,
            "links": filtered_links
        }

        output_file = file_path.with_name(f"{file_path.stem}-{suffix}.json")
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)

        typer.echo(
            f"Processed {file_path.name}: {original_node_count} nodes -> {len(filtered_nodes)}, "
            f"{original_link_count} links -> {len(filtered_links)} -> Saved to {output_file.name}"
        )

if __name__ == "__main__":
    app()

