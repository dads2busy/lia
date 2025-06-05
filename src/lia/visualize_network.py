import json
import typer
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

app = typer.Typer(add_completion=False)

@app.command()
def main(input_file: Path, output_file: Path = None):
    if not input_file.exists():
        raise typer.BadParameter(f"Input file does not exist: {input_file}")

    # Load data
    with input_file.open() as f:
        network_data = json.load(f)

    # Default output name
    if output_file is None:
        output_file = input_file.with_suffix(".html")

    # Set up Jinja2 environment to load from the same directory as this script
    script_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(script_dir))
    template = env.get_template("visualization_template.jinja2")

    # Render template
    html = template.render(
        network_data=network_data,
        filename=input_file.name
    )

    # Write output
    with output_file.open("w", encoding="utf-8") as f:
        f.write(html)

    typer.echo(f"✅ HTML written to {output_file}")

if __name__ == "__main__":
    app()
