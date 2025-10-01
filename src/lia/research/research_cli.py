import json
import os
from pathlib import Path
from typing import List, Optional, Annotated,Union
import typer
import asyncio

from lia.research import ResearchPipelineOptions,ResearchMaterial

from lia.research.config import ResearchConfig,load_config,save_config
from lia.research.research_pipeline import run_research_pipeline,start_map
from lia.util.fetch_reference_content import fetch_references,fetch_content,ReferenceContentOptions
from lia.util.mcp_supervisord import build_supervisord_config,start_supervisor,status_supervisor,stop_supervisor,restart_supervisor,check_all_running
from lia.research.pipeline_state import ResearchPipelineState,load_state,save_state as save_pipeline_state,backup_state

app = typer.Typer(help="Research Configuration CLI Tool")
mcp_app = typer.Typer(help="Manage external MCP Server processes for Research")
app.add_typer(mcp_app,name="mcp")

reference_app = typer.Typer(help="Manage and Display Refereence Content")
app.add_typer(reference_app,name="reference")


CONFIG_FILENAME = "research_config.json"
ENV_RESEARCH_FOLDER = "LIA_RESEARCH_FOLDER"
DEFAULT_LIA_CONFIG = Path.home() / ".lia" / "config.json"

def resolve_output(default: Optional[Path] = None) -> Path:
    env_path = os.getenv(ENV_RESEARCH_FOLDER)
    if default is None and env_path:
        return Path(env_path)
    if default is not None:
        return default
    typer.echo("Error: --output is required or set the LIA_RESEARCH_FOLDER environment variable.", err=True)
    raise typer.Exit(1)

def load_user_config() -> dict:
    if DEFAULT_LIA_CONFIG.exists():
        with DEFAULT_LIA_CONFIG.open() as f:
            return json.load(f)
    return {}

UserConfig = load_user_config()

### MCP Subcommands
### These are used to launch external http based MCP servers
@mcp_app.command()    
def start(
        research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder")
):
    """
    Start external MCP servers
    """
    config_file = research_folder / "mcp_supervisord.conf"
    pid_file = research_folder / "mcp_supervisord.pid"
    log_dir = research_folder / "logs"
    reference_content_folder = research_folder / "reference_content"
    db_cache_folder = research_folder / "db_cache"
    os.makedirs(log_dir,exist_ok=True)

    external_mcp_servers = [
        ["hscode",["python",str(Path(__file__).parent.parent.resolve() / Path("tools/mcp-server-hscode-faiss-rollupmd.py")),"--cache-dir", str(db_cache_folder)]],
        ["research_data", ["python",str(Path(__file__).parent.parent.resolve() / Path("tools/mcp-preliminary-research-vector.py")),"--cache-dir", str(db_cache_folder),str(reference_content_folder)]]
    ]
    
    start_supervisor(external_mcp_servers, config_file, pid_file, overwrite=True,log_dir=log_dir)

@mcp_app.command()    
def stop(
        research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder")
):
    """
    Stop external MCP servers
    """
    config_file = research_folder / "mcp_supervisord.conf"
    pid_file = research_folder / "mcp_supervisord.pid"

    stop_supervisor(config_file, pid_file)


@mcp_app.command()    
def status(
        research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder")
):
    """
    Show the status of the external MCP servers
    """
    config_file = research_folder / "mcp_supervisord.conf"
    pid_file = research_folder / "mcp_supervisord.pid"

    status_supervisor(config_file)
    
@reference_app.command()
def list(
    research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"),
    failed: Annotated[bool, typer.Option("--failed", "-f", help="Show URLs that were not retrievable")] = False,
):
    """
    List all references in the research folder
    """
    research_folder = resolve_output(research_folder)
    reference_content_folder = research_folder / "reference_content"
    for file in reference_content_folder.glob("*.json"):
        with file.open("r") as ref_file:
            try:
                ref_data = json.load(ref_file)
                err = ref_data.get('error',None)
                if err is None:
                    typer.echo(f"- {ref_data['url']}")
                elif failed:
                    typer.echo(f"- [FAILED] {ref_data['url']}")
                
            except json.JSONDecodeError:
                typer.echo(f"Error decoding JSON from {file.name}")

@reference_app.command()
def refresh(
    research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"),
    urls: Optional[List[str]] = typer.Argument(None, help="List of URLs to refresh. If not provided, all URLs will be refreshed.")
):
    """
    Refresh the content of specified references or all references if no URLs are provided.
    """
    research_folder = resolve_output(research_folder)
    reference_content_folder = research_folder / "reference_content"
    config = load_config(research_folder)

    urls_to_refresh = urls if urls else config.references

    for file in reference_content_folder.glob("*.json"):
        with file.open("r") as ref_file:
            try:
                ref_data = json.load(ref_file)
                if ref_data['url'] not in urls_to_refresh:
                    urls_to_refresh.append(ref_data['url'])
            except json.JSONDecodeError:
                typer.echo(f"Error decoding JSON from {file.name}")
                
                
    async def _refresh_content(refs: List[str]):
        for ref in refs:
            try:
                print(f"Refreshing content for {ref}...")
                rc = await fetch_content(ref, options=ReferenceContentOptions(reference_cache_folder=str(reference_content_folder), save=True, refresh=True))
                if rc.error:
                    typer.echo(f"Error refreshing content for {ref}: {rc.error}")
                else:
                    typer.echo(f"Refreshed content for {ref}")
            except Exception as e:
                typer.echo(f"Error refreshing content for {ref}: {e}")

    typer.echo(f"Refreshing content for {len(urls_to_refresh)} references...")
    asyncio.run(_refresh_content(urls_to_refresh))
       
@reference_app.command()
def show(
    url: str = typer.Argument(str, help="URL of the reference to show"),
    research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"),
    refresh: Annotated[bool, typer.Option("--refresh", "-r", help="Reload the content from the source and overwrite the cached version")] = False,
): 
    research_folder = resolve_output(research_folder)
    reference_content_folder = str(research_folder / "reference_content")
    async def _fetch_content(ref: str):
        try:
            rc = await fetch_content(ref, options=ReferenceContentOptions(reference_cache_folder=reference_content_folder, save=refresh, refresh=refresh))
            if rc.error:
                typer.echo(f"Error fetching content for {ref}: {rc.error}")
            else:
                typer.echo(f"Content for {ref}:\n{rc.content}")
        except Exception as e:
            typer.echo(f"Error fetching content for {ref}: {e}")
            
    print(f"Fetching content for {url}...")
    asyncio.run(_fetch_content(url))
    
### Main Research Commands
@app.command()
def init(
    output: Path = typer.Argument(..., help="Folder to store research information"),
    material: str = typer.Argument(..., help="The main material name"),
    materials: Optional[str] = typer.Option(None, help="Comma-separated list of material forms/compounds"),
    references: Optional[str] = typer.Option(None, help="Comma-separated list of reference URLs"),
    products: Optional[str] = typer.Option(None, help="Comma-separated list of important product families"),
    force: bool = typer.Option(False, help="Overwrite existing research_config.json")
):
    """
    Initialize a folder for preliminary research and optionally add materials, references, and products to the set
    """
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / CONFIG_FILENAME
    if config_path.exists() and not force:
        typer.echo(f"Config already exists at {config_path}. Use --force to overwrite.")
        with open(config_path, "r") as f:
            config = ResearchConfig(**json.load(f))
    else:
        config = ResearchConfig(
            material=material,
            materials=[s.strip() for s in materials.split(",")] if materials else [],
            references=[s.strip() for s in references.split(",")] if references else [],
            products=[s.strip() for s in products.split(",")] if products else []
        )
    
    save_config(output, config)
    typer.echo(f"Initialized research config at {config_path}")
    os.makedirs(output / "reference_content", exist_ok=True)
    if len(config.references) > 0:
        typer.echo(f"Retrieving initial references...")
        opts = ReferenceContentOptions(
            reference_cache_folder=str(output / "reference_content"),
            save=True
        )
        refs = asyncio.run(fetch_references(config.references,opts))

@app.command()
def addMaterial(research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"), form: str = typer.Argument(...)):
    """
    Add a material for preliminary research
    """
    research_folder = resolve_output(research_folder)
    config = load_config(research_folder)
    if form not in config.materials:
        config.materials.append(form)
        save_config(research_folder, config)
        typer.echo(f"Added form: {form}")
    else:
        typer.echo(f"Form already exists: {form}")

@app.command()
def addReference(research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"), url: str = typer.Argument(...)):
    """
    Add a reference for preliminary research
    """
    research_folder = resolve_output(research_folder)
    config = load_config(research_folder)
    if url not in config.references:
        config.references.append(url)
        save_config(research_folder, config)
        typer.echo(f"Added reference: {url}")
        if len(config.references) > 0:
            typer.echo(f"Retrieving initial references...")
            opts = ReferenceContentOptions(
                reference_cache_folder=str(research_folder / "reference_content"),
                save=True
            )
            refs = asyncio.run(fetch_references(config.references,opts))
    else:
        typer.echo(f"Reference already exists: {url}")

@app.command()
def addProduct(research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"), product: str = typer.Argument(...)):
    """
    Add a product for preliminary research
    """
    research_folder = resolve_output(research_folder)
    config = load_config(research_folder)
    if product not in config.products:
        config.products.append(product)
        save_config(research_folder, config)
        typer.echo(f"Added product: {product}")
    else:
        typer.echo(f"Product already exists: {product}")

@app.command()
def removeMaterial(research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"), form: str = typer.Argument(...)):
    """
    Remove a material from the preliminary research set
    """
    research_folder = resolve_output(research_folder)
    config = load_config(research_folder)
    if form in config.forms:
        config.forms.remove(form)
        save_config(research_folder, config)
        typer.echo(f"Removed form: {form}")
    else:
        typer.echo(f"Form not found: {form}")

@app.command()
def removeReference(research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"), url: str = typer.Argument(...)):
    """
    Remove a reference from the preliminary research set
    """
    research_folder = resolve_output(research_folder)
    config = load_config(research_folder)
    if url in config.references:
        config.references.remove(url)
        save_config(research_folder, config)
        typer.echo(f"Removed reference: {url}")
    else:
        typer.echo(f"Reference not found: {url}")

@app.command()
def removeProduct(research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"), product: str = typer.Argument(...)):
    """
    Remove a product from the preliminary research set
    """
    research_folder = resolve_output(research_folder)
    config = load_config(research_folder)
    if product in config.products:
        config.products.remove(product)
        save_config(research_folder, config)
        typer.echo(f"Removed product: {product}")
    else:
        typer.echo(f"Product not found: {product}")

@app.command()
def show(
        research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"),
        material: Annotated[str,None, typer.Option("--material", "-m", help="Default Base Model Name")] = None,
    ):
    """
    Display the preliminary research configuration/setup
    """
    research_folder = resolve_output(research_folder)
    config = load_config(research_folder)
    state_file = research_folder / "research_state.json"
    
    if material is None:
        typer.echo("\nResearch Configuration:\n------------------------")
        typer.echo(f"Primary Material: {config.material}")
        typer.echo("\nMaterials:")
        for form in config.materials:
            typer.echo(f"  - {form}")
        typer.echo("\nReferences:")
        for ref in config.references:
            typer.echo(f"  - {ref}")
        typer.echo("\nProducts:")
        for product in config.products:
            typer.echo(f"  - {product}")
            
        if state_file.exists():
            typer.echo("\nResearch State:")

            state=load_state(research_folder,ResearchPipelineState(research_config=config))
            
            typer.echo("Materials:")
            for material_id, material in state.materials.items():
                typer.echo(f" - {material.hs_code} {material.name} {'[Mined]' if material.mined else ''}")
                typer.echo(f"\t - {material.hs_description}\n\t - Processes:\n")
                material_processes = state.get_processes_for_material(material_id)
                for process in material_processes:
                    process_id = process.id
                    typer.echo(f"\t\t- [ {process_id} ] Scale: {process.scale} Score: {process.process_score} References: {len(process.references)}")
                    typer.echo(f"\t\t  {process.description[:60]}...")
                    typer.echo(f"\t\t  Precursors: {', '.join([str(p) for p in process.precursors])}")
                    typer.echo(f"\t\t  Products: {', '.join([str(b) for b in process.products])}")
                    typer.echo("\t\t  References:")
                    for ref in process.references:
                        if isinstance(ref, str):
                            typer.echo(f"\t\t\t - {ref} [Not Reviewed]")
                        else:
                            typer.echo(f"\t\t\t - {ref.url} Score: {ref.source_quality_score} Content Score: {ref.content_quality_score}\n\t\t\t   {ref.content_quality_reason}\n") 
                typer.echo("\n")
    else:
        typer.echo(f"\nResearch Details for Material: {material}\n------------------------")

        if state_file.exists():
            
            state=load_state(research_folder,ResearchPipelineState(research_config=config))
            
            # state_data = json.load(f)
            # state = ResearchPipelineState(**state_data,ResearchConfig=config)
            m = state.materials[material]
            if m is None:
                typer.echo(f"No research data found for material: {material}")
                raise typer.Exit(1)

            typer.echo(f"Material: {m.name} {'[Mined]' if m.mined else ''}")
            typer.echo(f"HS Code: {m.hs_code}\n\n({m.hs_description})\n")

            material_processes = state.get_processes_for_material(m.hs_code)
            if len(m.processes)>0:
                typer.echo(f"Processes:")
        
            for process in material_processes:
                process_id = process.id
                typer.echo(f"\t\t - [ {process_id} ] Scale: {process.scale} Score: {process.process_score} References: {len(process.references)}")
                typer.echo(f"\t\t   {process.description[:60]}...")
                typer.echo( "\t\t   References:")
                for ref in process.references:
                    if isinstance(ref,str):
                        typer.echo(f"\t\t\t - {ref} [Not Reviewed]")
                    else:
                        typer.echo(f"\t\t\t - {ref.url} Score: {ref.source_quality_score} Content Score: {ref.content_quality_score}\n\t\t\t   {ref.content_quality_reason}\n")


                typer.echo("\n")

@app.command()
def removeProcess(research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"), process_id: str = typer.Argument(...)):
    """
    Remove a process from the research state by its ID
    """
    research_folder = resolve_output(research_folder)
    config = load_config(research_folder)
    state_file = research_folder / "research_state.json"
    
    if state_file.exists():
        state=load_state(research_folder,ResearchPipelineState(research_config=config))
        state.remove_process(process_id)
        save_pipeline_state(research_folder,state)
        typer.echo(f"Removed process: {process_id}")
    else:
        typer.echo(f"No research state found at {state_file}")
        raise typer.Exit(1) 
    
@app.command()
def go(
    research_folder: Optional[Path] = typer.Option(os.getenv(ENV_RESEARCH_FOLDER, None), help="Path to research folder"),
    model: Annotated[str, typer.Option("--model", "-m", help="Default Base Model Name")] = UserConfig.get("model","llama3.3"),
    llm_api_url: Annotated[Optional[str], typer.Option("--llm-api-url", "-u", help="URL to LLM API")] = UserConfig.get("llm_api_url",None),
    llm_api_key: Annotated[str, typer.Option("--llm-api-key", "-k", help="API Key if needed for LLM")] = UserConfig.get("llm_api_key",None),
    google_api_key: Annotated[Optional[str], typer.Option("--google-api-key", help="Google API Key for custom search")] = UserConfig.get("google_api_key", None),
    wikimedia_access_token: Annotated[Optional[str], typer.Option("--wikimedia-access-token", help="Wikimedia Access Token for accessing Wikipedia API")] = UserConfig.get("wikimedia_access_token", None),
    google_custom_search_engine_id: Annotated[Optional[str], typer.Option("--google-cse-id", help="Google Custom Search Engine ID")] = UserConfig.get("google_custom_search_engine_id", None),
    generate_materials: Annotated[bool, typer.Option("--no-generate-materials","-G", help="Generate Materails")] = True,
    regenerate_materials: Annotated[bool, typer.Option("--regenerate-materials", "-r", help="Regenerate the list of materials to research")] = False,
    material_generation_rounds: Annotated[int, typer.Option("--material-generation-rounds", "-n", help="Number of rounds to generate materials")] = 2,
    generate_processess: Annotated[bool, typer.Option("--no-generate-processess", "-P", help="Generate Processes")] = True,   
    process_score_threshold: Annotated[float, typer.Option("--process-score-threshold", help="Minimum process score to consider a process supported")] = 0.5, 
    minimum_process_references: Annotated[int, typer.Option("--minimum-process-references", help="Minimum number of references required for a process to be considered supported")] = 2,
    maximum_reference_reviews: Annotated[int, typer.Option("--maximum-reference-reviews", help="Maximum number of review passes")] = 1,
    force_reference_review: Annotated[bool, typer.Option("--force-reference-review", help="Force a review of all references even if they have been reviewed before")] = False,
    save_state: Annotated[bool, typer.Option("--no-save-state", help="Save the state to the research folder (will save periodicall through out)")]=True,
    start: Annotated[str,None, typer.Option("--start", "-s", help=f"starting point in the pipeline ({', '.join(start_map.keys())})")]=None,
    solo: Annotated[bool, typer.Option("--solo", help="Run the research pipeline in solo task mode")] = False,
    distinct_domains_required: Annotated[int, typer.Option("--distinct-domains-required", help="Number of distinct domains required for a process to be considered supported")]=2,
    merge_duplicate_processes: Annotated[bool, typer.Option("--no-merge-duplicate-processes", "-M", help="Merge duplicate processes based on their description and references")]=True,
    purge_processes: Annotated[bool, typer.Option("--no-purge-processes", "-X", help="Purge processes from the research state")] = True,
    purge_dry_run: Annotated[bool, typer.Option("--purge-dry-run", "-d", help="Perform a dry run of the purge without actually removing anything")]=False,
    purge_scale_threshold: Annotated[float, typer.Option("--purge-scale-threshold", help="Scale threshold for purging unsupported processes")]=0.4,
    expand_process_materials: Annotated[bool, typer.Option("--no-expand-process-materials", "-E", help="Expand process materials based on the current research state")]=True,
    maximum_material_expansion_rounds: Annotated[int, typer.Option("--maximum-material-expansion-rounds", help="Number of rounds to expand precursors,products, and product family materials")]=2,
    expand_product_family_materials: Annotated[bool, typer.Option("--no-expand-product-family-materials", help="Expand product family materials based on the current research state")]=True,
    expansion_filter: Annotated[Optional[str], typer.Option("--expansion-filter", help="Comma-separated list of HS codes to limit expansion to")] = None,   
    reset_reference_reviews_on_material_expansion: Annotated[bool, typer.Option("--no-reset-reference-reviews-on-material-expansion", "-R", help="Reset reference reviews when expanding materials")]=True
): 
    """
    Launch a round of research.
    """
    research_folder = resolve_output(research_folder)
    mcp_config_file = research_folder / "mcp_supervisord.conf"
    reference_cache_folder = research_folder / "reference_content"
    
    if expansion_filter is not None:
        expansion_filter = [s.strip() for s in expansion_filter.split(",")]
    
    options = ResearchPipelineOptions(
        model_name=model,
        llm_api_url=llm_api_url,
        llm_api_key=llm_api_key,
        research_folder=research_folder,
        reference_cache_folder=str(reference_cache_folder),
        google_api_key=google_api_key,
        google_custom_search_engine_id=google_custom_search_engine_id,
        wikimedia_access_token=wikimedia_access_token,
        generate_materials=generate_materials,
        regenerate_materials=regenerate_materials,
        material_generation_rounds=material_generation_rounds,
        generate_processess=generate_processess,
        process_score_threshold=process_score_threshold,
        minimum_process_references=minimum_process_references,
        maximum_reference_reviews=maximum_reference_reviews,
        force_reference_review=force_reference_review,
        merge_duplicate_processes=merge_duplicate_processes,
        purge_processes=purge_processes,
        purge_dry_run=purge_dry_run,
        purge_scale_threshold=purge_scale_threshold,
        expand_process_materials=expand_process_materials,
        maximum_material_expansion_rounds=maximum_material_expansion_rounds,
        expand_product_family_materials=expand_product_family_materials,
        expansion_filter=expansion_filter,
        reset_reference_reviews_on_material_expansion=reset_reference_reviews_on_material_expansion,   
        solo=solo,
        distinct_domains_required=distinct_domains_required,
        save_state=save_state,
        start=start
    )

    if not check_all_running(mcp_config_file):
        print("One or more required MCP servers are not running and required for research. Run 'lia research mcp start' to launch them.")
        exit(1)

    results = asyncio.run(run_research_pipeline(options=options))

if __name__ == "__main__":
    app()

