# src/lia/stdn_export/cli.py
import asyncio
import json
from pathlib import Path
from typing import Annotated, Optional

from dotenv import load_dotenv

load_dotenv()

import typer

from lia.stdn_export import MaterialBucket

app = typer.Typer(help="Export STDN trade flow data from Comtrade for the STDN Explorer")

# Repo root for resolving relative defaults
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Load user config for defaults (same pattern as lia.cli, inlined to avoid circular import)
_LIA_CONFIG_PATH = Path.home() / ".lia" / "config.json"
def _load_user_config() -> dict:
    if _LIA_CONFIG_PATH.exists():
        with _LIA_CONFIG_PATH.open() as f:
            return json.load(f)
    return {}
UserConfig = _load_user_config()


def parse_materials(materials_arg: str) -> list[str]:
    """Parse materials from file path or comma-separated string."""
    path = Path(materials_arg)
    if path.exists() and path.is_file():
        return [line.strip() for line in path.read_text().splitlines() if line.strip()]
    return [m.strip() for m in materials_arg.split(",") if m.strip()]


def parse_years(years_str: str) -> list[int]:
    """Parse year range string like '2017-2025' into list of ints."""
    if "-" in years_str:
        start, end = years_str.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(y.strip()) for y in years_str.split(",")]


@app.command()
def export(
    materials: Annotated[str, typer.Option("--materials", "-m", help="File path (one per line) or comma-separated material names")] = ...,
    comtrade_dir: Annotated[str, typer.Option("--comtrade-dir", help="Directory containing Arrow files")] = UserConfig.get("comtrade_dir", str(REPO_ROOT / "data" / "UN_Comtrade")),
    years: Annotated[str, typer.Option("--years", help="Year range (e.g., 2017-2025)")] = "2017-2025",
    perspective: Annotated[str, typer.Option("--perspective", help="Importer country (only 'US' supported)")] = "US",
    output: Annotated[str, typer.Option("--output", "-o", help="Output CSV path")] = "stdn_trade_data.csv",
    cache_dir: Annotated[str, typer.Option("--cache-dir", help="Bucket mapping cache directory")] = UserConfig.get("cache_dir", "~/.lia/stdn-cache"),
    hs_rollup: Annotated[str, typer.Option("--hs-rollup", help="Path to H6_rollup.md")] = UserConfig.get("hs_rollup_file", str(REPO_ROOT / "H6_rollup.md")),
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Force regeneration of bucket mappings")] = False,
    no_mcp_auto: Annotated[bool, typer.Option("--no-mcp-auto", help="Don't auto-launch MCP servers")] = False,
    model: Annotated[str, typer.Option("--model", help="LLM model name")] = "openai:gpt-5.3",
    llm_api_url: Annotated[Optional[str], typer.Option("--llm-api-url", help="LLM API URL")] = None,
    llm_api_key: Annotated[Optional[str], typer.Option("--llm-api-key", help="LLM API key")] = None,
):
    """Export STDN trade flow data from Comtrade for the STDN Explorer."""
    if perspective.upper() != "US":
        typer.echo(f"Error: Only 'US' perspective is supported. Got: '{perspective}'", err=True)
        raise typer.Exit(1)

    asyncio.run(_run_export(
        materials_arg=materials,
        comtrade_dir=Path(comtrade_dir),
        years=parse_years(years),
        output_path=Path(output),
        cache_dir=Path(cache_dir).expanduser(),
        hs_rollup_path=hs_rollup,
        use_cache=not no_cache,
        auto_mcp=not no_mcp_auto,
        model=model,
        llm_api_url=llm_api_url,
        llm_api_key=llm_api_key or "",
    ))


async def _run_export(
    materials_arg: str,
    comtrade_dir: Path,
    years: list[int],
    output_path: Path,
    cache_dir: Path,
    hs_rollup_path: str,
    use_cache: bool,
    auto_mcp: bool,
    model: str,
    llm_api_url: Optional[str],
    llm_api_key: str,
):
    from lia.research import ResearchPipelineOptions
    from lia.stdn_export.bucket_generator import generate_bucket, load_h6_rollup
    from lia.stdn_export.comtrade_query import (
        aggregate_trade_data,
        load_partner_map,
        query_us_imports,
        write_csv,
    )
    from lia.stdn_export.mcp_launcher import mcp_server_context

    material_list = parse_materials(materials_arg)
    print(f"Materials: {material_list}")
    print(f"Years: {years[0]}-{years[-1]}")
    print(f"Output: {output_path}")

    # Strip provider prefix (e.g. "openai:gpt-5.3" -> "gpt-5.3") since
    # lia's agents use OpenAIModel directly rather than pydantic-ai's routing
    model_name = model.split(":", 1)[-1] if ":" in model else model

    options = ResearchPipelineOptions(
        model_name=model_name,
        llm_api_url=llm_api_url,
        llm_api_key=llm_api_key or "",
    )

    # Load H6 rollup for quality classification
    h6_rollup = load_h6_rollup(hs_rollup_path)
    print(f"Loaded {len(h6_rollup)} HS code descriptions from {hs_rollup_path}")

    # Stage 1-2: Generate buckets (with optional MCP auto-launch)
    buckets: dict[str, MaterialBucket] = {}

    # mcp_server_context is a sync context manager (subprocess management).
    # Use plain `with` — works fine inside async functions.
    if auto_mcp:
        ctx = mcp_server_context(hs_rollup_file=hs_rollup_path)
    else:
        from contextlib import nullcontext
        ctx = nullcontext()

    with ctx:
        for material in material_list:
            print(f"\n[{material}]")
            bucket = await generate_bucket(
                material=material,
                options=options,
                h6_rollup=h6_rollup,
                cache_dir=cache_dir,
                use_cache=use_cache,
            )
            buckets[material] = bucket

    # Collect all HS codes across all buckets
    all_hs_codes = set()
    for bucket in buckets.values():
        for entry in bucket.hs_codes:
            all_hs_codes.add(entry.code)
    print(f"\nTotal unique HS codes across all buckets: {len(all_hs_codes)}")

    # Stage 3-5: Query Comtrade
    print("\nQuerying Comtrade data...")
    partner_map = load_partner_map(comtrade_dir / "partnerAreas.arrow")
    raw_rows = query_us_imports(comtrade_dir, years, all_hs_codes)
    print(f"Total raw trade records: {len(raw_rows)}")

    # Stage 6-7: Aggregate and rank
    print("\nAggregating trade data...")
    trade_rows = aggregate_trade_data(raw_rows, buckets, partner_map)

    # Stage 8: Write outputs
    write_csv(trade_rows, output_path)

    # Also write the consolidated bucket mapping
    bucket_json_path = output_path.with_suffix(".buckets.json")
    bucket_dict = {name: bucket.model_dump() for name, bucket in buckets.items()}
    bucket_json_path.write_text(json.dumps(bucket_dict, indent=2))
    print(f"Bucket mapping written to {bucket_json_path}")

    print(f"\nDone! {len(trade_rows)} trade flow rows for {len(buckets)} materials.")
