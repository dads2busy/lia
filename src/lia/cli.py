# src/lia/cli.py
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Optional

import typer
from typing_extensions import Annotated

from lia.identify_raw_materials import IdentifyRawMaterialsOptions
from lia.identify_raw_materials import (
    identify_raw_materials as call_identify_raw_materials,
)
from lia.research.research_cli import app as research_app
from lia.search import SearchOptions, llmsearch

app = typer.Typer()
app.add_typer(
    research_app,
    name="bottomup",
)

DEFAULT_LIA_CONFIG = Path.home() / ".lia" / "config.json"


def load_user_config() -> dict:
    if DEFAULT_LIA_CONFIG.exists():
        with DEFAULT_LIA_CONFIG.open() as f:
            return json.load(f)
    return {}


UserConfig = load_user_config()


@app.command()
def search(
    query: str,
    model: Annotated[
        str, typer.Option("--model", "-m", help="Default Base Model Name")
    ] = UserConfig.get("model", "llama3.3"),
    llm_api_url: Annotated[
        Optional[str], typer.Option("--llm-api-url", "-u", help="URL to LLM API")
    ] = UserConfig.get("llm_api_url", None),
    llm_api_key: Annotated[
        str, typer.Option("--llm-api-key", "-k", help="API Key if needed for LLM")
    ] = None,
    google_api_key: Annotated[
        Optional[str],
        typer.Option("--google-api-key", "-g", help="Google API Key for custom search"),
    ] = None,
    google_custom_search_engine_id: Annotated[
        Optional[str],
        typer.Option("--google-cse-id", "-c", help="Google Custom Search Engine ID"),
    ] = UserConfig.get("google_custom_search_engine_id", None),
):
    """
    Perform LLM assisted web search
    """
    options = SearchOptions(
        model_name=model,
        llm_api_url=llm_api_url,
        llm_api_key=llm_api_key,
        google_api_key=google_api_key,
        google_custom_search_engine_id=google_custom_search_engine_id,
    )
    print(f"from options: {options.google_api_key}")
    print(f"Options: {options}")
    return asyncio.run(llmsearch(query, options=options))


@app.command()
def identify_raw_materials(
    material: str,
    debug: Annotated[
        bool, typer.Option("--debug", "-d", help="Enable debugging output.")
    ] = False,
    model: Annotated[
        str, typer.Option("--model", "-m", help="Default Base Model Name")
    ] = "llama3.3",
    llm_api_url: Annotated[
        str, None, typer.Option("--llm-api-url", "-u", help="URL to LLM API")
    ] = None,
    llm_api_key: Annotated[
        str, typer.Option("--llm-api-key", "-k", help="API Key if needed for LLM")
    ] = "None",
    max_reviews: Annotated[
        int, None, typer.Option("--max-reviews", "-R", help="Maximum number of reviews")
    ] = 6,
    min_reviews: Annotated[
        int, None, typer.Option("--min-reviews", "-r", help="Minimum number of reviews")
    ] = 3,
    output: Annotated[
        str,
        None,
        typer.Option(
            "--output", "-o", help="Output file.  If not provided, output stdout"
        ),
    ] = None,
):
    """
    Identify raw materials for a specific technology/product
    """
    # material = ' '.join(material)
    print("Here")
    options = IdentifyRawMaterialsOptions(
        debug=debug,
        model_name=model,
        llm_api_url=llm_api_url,
        llm_api_key=llm_api_key,
        max_reviews=max_reviews,
        min_reviews=min_reviews,
    )

    print(f"Identifying raw materials required for the production of '{material}'")
    try:
        results = asyncio.run(call_identify_raw_materials(material, options))
        # results=None
        if results is not None:
            print(f"results: {results}")
            if output is not None:
                with open(output, "w") as f:
                    f.write(json.dumps([asdict(mat) for mat in results], indent=2))
                    f.close()
                print(f"Wrote Raw Material list to {output}")
            else:
                print(f"{json.dumps([asdict(mat) for mat in results], indent=4)}")
        else:
            print("No Results")

    except Exception as err:
        print(f"Error generator supply chain network:\n{err}")


if __name__ == "__main__":
    app()
