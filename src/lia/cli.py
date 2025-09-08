# src/lia/cli.py
import typer
from typing import Union
from typing_extensions import Annotated
from pathlib import Path
from lia.analysis_context import load_context, AnalysisContext
from lia.lia import Lia
from lia.ateam import ATeam
from lia.reasoner import Reasoner
from pydantic import BaseModel
from dataclasses import asdict
from typing import List, Optional, Annotated,Union
import os
import json
import asyncio
from lia.supply_chain_network_generator import analyze_product, Product
from lia.raw_material_network_generator import get_raw_material_network,MaterialNetworkGeneratorOptions,serialize_material_network,PreliminaryResearch,Reference
from lia.identify_raw_materials import identify_raw_materials as call_identify_raw_materials,IdentifyRawMaterialsOptions
from lia.research.research_cli import app as research_app
from lia.search import llmsearch,SearchOptions
app = typer.Typer()
app.add_typer(research_app,name="research",)

DEFAULT_LIA_CONFIG = Path.home() / ".lia" / "config.json"

def load_user_config() -> dict:
    if DEFAULT_LIA_CONFIG.exists():
        with DEFAULT_LIA_CONFIG.open() as f:
            return json.load(f)
    return {}

UserConfig = load_user_config()
class Options(BaseModel):
    debug: bool = False
    reasoning:bool = False
    agent: Union[str, None] = None
    storage_folder: str = "./lia"
    model_name: str = "llama3.3"
    llm_api_url: str | None
    llm_api_key: str = ""
    python_tool_container: str | None = None
                
@app.command()
def search (
    query: str,
    model: Annotated[str, typer.Option("--model", "-m", help="Default Base Model Name")] = UserConfig.get("model","llama3.3"),
    llm_api_url: Annotated[Optional[str], typer.Option("--llm-api-url", "-u", help="URL to LLM API")] = UserConfig.get("llm_api_url",None),
    llm_api_key: Annotated[str, typer.Option("--llm-api-key", "-k", help="API Key if needed for LLM")] = UserConfig.get("llm_api_key",None),
    google_api_key: Annotated[Optional[str], typer.Option("--google-api-key", "-g", help="Google API Key for custom search")] = UserConfig.get("google_api_key", None),
    google_custom_search_engine_id: Annotated[Optional[str], typer.Option("--google-cse-id", "-c", help="Google Custom Search Engine ID")] = UserConfig.get("google_custom_search_engine_id", None)
):
    """
    Perform LLM assisted web search
    """   
    options = SearchOptions(
        model_name=model,
        llm_api_url=llm_api_url,
        llm_api_key=llm_api_key,
        google_api_key=google_api_key,
        google_custom_search_engine_id=google_custom_search_engine_id
    )
    print(f"from options: {options.google_api_key}")
    print(f"Options: {options}")
    return asyncio.run(llmsearch(query,options=options))

@app.command()
def identify_raw_materials (
    material: str,
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debugging output.")] = False,
    model:  Annotated[str, typer.Option("--model", "-m", help="Default Base Model Name")] = "llama3.3",
    llm_api_url: Annotated[str,None, typer.Option("--llm-api-url", "-u", help="URL to LLM API")] = None,
    llm_api_key: Annotated[str, typer.Option("--llm-api-key", "-k", help="API Key if needed for LLM")] = "None",
    max_reviews: Annotated[int,None,typer.Option("--max-reviews","-R",help="Maximum number of reviews")] = 6,
    min_reviews: Annotated[int,None,typer.Option("--min-reviews","-r",help="Minimum number of reviews")] = 3,
    output: Annotated[str,None, typer.Option("--output", "-o", help="Output file.  If not provided, output stdout")] = None
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
        min_reviews=min_reviews
    )
    
    print(f"Identifying raw materials required for the production of '{material}'")
    try: 
        results = asyncio.run(call_identify_raw_materials(material,options))
        # results=None
        if results is not None:
            print(f"results: {results}")
            if output is not None:    
                with open(output, 'w') as f:
                    f.write(json.dumps([asdict(mat) for mat in results], indent=2))
                    f.close()
                print(f"Wrote Raw Material list to {output}")
            else:
                print(f"{json.dumps([asdict(mat) for mat in results], indent=4)}")
        else:
            print("No Results")
            
    except Exception as err:
        print(f"Error generator supply chain network:\n{err}")

@app.command()
def generate_material_network (
    material: str = typer.Argument(..., help="Material to analyze for network generation"),
    output: Annotated[str,None, typer.Option("--output", "-o", help="Output file.  If not provided, output stdout")] = None,
    preliminary_only: Annotated[bool, typer.Option("--prelim-only", "-P", help="Only perform the preliminary analysis, no network generation")] = False,
    preliminary_out: Annotated[str,None, typer.Option("--prelim-out", "-p", help="Output for Preliminary Research. Do not save if not provided.")] = None,
    preliminary_in: Annotated[str,None, typer.Option("--prelim-in", "-i", help="Input for Preliminary Research. Uses this data as the starting point.")] = None,
    preliminary_rounds: Annotated[int,None,typer.Option("--prelim-rounds",help="Number of preliminary research rounds")]=3,
    max_preliminary_rounds: Annotated[int,None,typer.Option("--max-prelim-rounds",help="Maximum number of preliminary research rounds")]=6,
    references: Annotated[str,None, typer.Option("--references", "-r", help="Storage for references. If not provided, all references will be re-evaluated")] = None,
    reference_cache_folder: Annotated[str,None, typer.Option("--reference-cache", "-c", help="Path to folder where reference content is stored.")] = None,
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debugging output.")] = False,
    model:  Annotated[str, typer.Option("--model", "-m", help="Default Base Model Name")] = "llama3.3",
    llm_api_url: Annotated[str,None, typer.Option("--llm-api-url", "-u", help="URL to LLM API")] = None,
    llm_api_key: Annotated[str, typer.Option("--llm-api-key", "-k", help="API Key if needed for LLM")] = "None",
):
    """
    Start the Material Network Generator
    """

    print("Starting Material Network Generator")
    prelim_data = None
    
    if preliminary_in:
        path = Path(preliminary_in)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    
            prelim_data = PreliminaryResearch(**data)

    if references:
        path = Path(references)
        reference_data = None
        if not path.exists():
            print("Reference file not found. References will be re-evaluated.")
        else:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                reference_data = {k: Reference(**v) for k, v in data.items()}


    
    options = MaterialNetworkGeneratorOptions(
        debug=debug,
        model_name=model,
        llm_api_url=llm_api_url,
        llm_api_key=llm_api_key,
        preliminary_research_only=preliminary_only,
        preliminary_research_data=prelim_data,
        preliminary_research_rounds=preliminary_rounds,
        max_preliminary_research_rounds=max_preliminary_rounds,
        reference_cache_folder=reference_cache_folder,
        references=reference_data if reference_data else None
    )
    
    print(f"Material: {material}")
    if debug:
        print(f"Options:\n{options}")
        
    try: 
        results = asyncio.run(get_raw_material_network(material,options))
        # print(f"Results: {results.output}")
        if results.output is not None:
            if results.output.preliminary_research is not None:
                research_dict = results.output.preliminary_research.dict()
                if preliminary_out:
                    with open(preliminary_out, 'w') as f:
                        f.write(json.dumps(research_dict, indent=2))
                        f.close()
                        print(f"Wrote preliminary research data to {preliminary_out}")
                else:
                    if debug:
                        print("Preliminary Research:")
                        print(json.dumps(research_dict, indent=2))
            

            if references is not None:
                # if debug:
                #     print("References:")
                #     print(json.dumps({k: v.model_dump() for k, v in results.output.references.items()},indent=2))

                if references and results.output.references is not None and hasattr(results.output, 'references'):
                    print(f"Writing references data to file: {references}")
                    with open(references, 'w') as f:
                        f.write(json.dumps({k: v.model_dump() for k, v in results.output.references.items()},indent=2))
                        f.close()
                    print(f"Wrote references to {references}")
               
            if results.output.network is not None:
                print("Store output network")
                with open(output, 'w') as f:
                    f.write(serialize_material_network(results.output.network))
                    f.close()
            
        else:
            print(results)
            
    except Exception as err:
        print(f"Error generator supply chain network:\n{err}")


@app.command()
def generate_supply_chain_network (
    product: str,
    output: Annotated[str,None, typer.Option("--output", "-o", help="Output file.  If not provided, output stdout")] = None,
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debugging output.")] = False,
    model:  Annotated[str, typer.Option("--model", "-m", help="Default Base Model Name")] = "llama3.3",
    llm_api_url: Annotated[str,None, typer.Option("--llm-api-url", "-u", help="URL to LLM API")] = "http://localhost:11434/v1",
    llm_api_key: Annotated[str, typer.Option("--llm-api-key", "-k", help="API Key if needed for LLM")] = "None",
):
    """
    Start the Supply Chain Network Generator
    """
    print("Starting Supply Chain Network Generator")
    options = MaterialNetworkGeneratorOptions(debug=debug,model_name=model,llm_api_url=llm_api_url,llm_api_key=llm_api_key)
    try: 
        results = asyncio.run(analyze_product(Product(name=product),options))
        
        print(f"Product: {results['product'].name}\nDescription:\n{results['product'].description}")
        if output is not None:
            with open(output, 'w') as f:
                json.dump(results["tree"], f, indent=4)
                f.close()
        else:
            print(results)
            
    except Exception as err:
        print(f"Error generator supply chain network:\n{err}")

@app.command()
def reasoner(
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debugging output.")] = False,
    reasoning: Annotated[bool, typer.Option("--reasoning", "-r", help="Show inter agent messaging.")] = False,
    model:  Annotated[str, typer.Option("--model", "-m", help="Default Base Model Name")] = "llama3.3",
    llm_api_url: Annotated[str,None, typer.Option("--llm-api-url", "-u", help="URL to LLM API")] = "http://localhost:11434/v1",
    llm_api_key: Annotated[str, typer.Option("--llm-api-key", "-k", help="API Key if needed for LLM")] = "None",
    python_tool_container:  Annotated[str, typer.Option("--tool-container", "-t", help="Path to singularity image for tools")] = "/project/biocomplexity/singularity_images/python_tool_container.sif",
    storage_folder: Annotated[str, typer.Option("--storage", "-s", help="Path to where files can be written and read")] = "./lia_work_dir"
):
    """
    Start the interactive chat with reasoner.
    """
    print("Starting Reasoner")
    options = Options(debug=debug, agent=None, storage_folder=storage_folder,reasoning=reasoning,model=model,llm_api_url=llm_api_url,llm_api_key=llm_api_key,python_tool_container=python_tool_container)
    
    try:
        os.makedirs(storage_folder, exist_ok=True)
    except Exception as err:
        print(f"Error creating storage folder: {err}")
        exit(1)
    
    try:
        ateam_shell = Reasoner(options)
        asyncio.run(ateam_shell.run_cli())
    except Exception as e:
        print(f"Error loading context: {e}")
        raise typer.Exit(code=1)

@app.command()
def ateam(
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debugging output.")] = False,
    reasoning: Annotated[bool, typer.Option("--reasoning", "-r", help="Show reasoning discussion.")] = False,
    model:  Annotated[str, typer.Option("--model", "-m", help="Default Base Model Name")] = "llama3.3",
    llm_api_url: Annotated[str,None, typer.Option("--llm-api-url", "-u", help="")] = None,
    llm_api_key: Annotated[str, typer.Option("--llm-api-key", "-k", help="")] = "None",
    python_tool_container:  Annotated[str, typer.Option("--tool-container", "-t", help="Path to singularity image for tools")] = "/project/biocomplexity/singularity_images/python_tool_container.sif",
    storage_folder: Annotated[str, typer.Option("--storage", "-s", help="Path to where files can be written and read")] = "./lia_work_dir"
):
    """
    Start the interactive chat with ATeam.
    """
    print("Starting Automoteam")
    options = Options(debug=debug, agent=None, storage_folder=storage_folder,reasoning=reasoning,model=model,llm_api_url=llm_api_url,llm_api_key=llm_api_key)
    
    try:
        os.makedirs(storage_folder, exist_ok=True)
    except Exception as err:
        print(f"Error creating storage folder: {err}")
        exit(1)
    
    try:
        ateam_shell = ATeam(options)
        asyncio.run(ateam_shell.run_cli())
    except Exception as e:
        print(f"Error loading context: {e}")
        raise typer.Exit(code=1)

# @app.callback(invoke_without_command=True)
@app.command()
def lia(
    file: Annotated[str, typer.Option("--file", "-f", help="Path to a JSON file containing an analysis context object.")] = None,
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debugging output.")] = False,
    agent: Annotated[Union[str, None], typer.Option("--agent", "-a", help="Interact with a different agent than the default.")] = None,
    model:  Annotated[str, typer.Option("--model", "-m", help="Default Base Model Name")] = "llama3.3",
    llm_api_url: Annotated[str,None, typer.Option("--llm-api-url", "-u", help="")] = "http://localhost:11434/v1",
    llm_api_key: Annotated[str, typer.Option("--llm-api-key", "-k", help="")] = "None",
    python_tool_container:  Annotated[str, typer.Option("--tool-container", "-t", help="Path to singularity image for tools")] = "/project/biocomplexity/singularity_images/python_tool_container.sif",
    storage_folder: Annotated[str, typer.Option("--storage", "-s", help="Path to where files can be written and read")] = "./lia_work_dir"
):
    """
    Start the interactive chat with Lia.
    """
    print(f"Model: {model}")
    options = Options(debug=debug, agent=agent, storage_folder=storage_folder,model_name=model,llm_api_url=llm_api_url,llm_api_key=llm_api_key)
    print(f"Options: {options}")
    try:
        os.makedirs(storage_folder, exist_ok=True)
    except Exception as err:
        print(f"Error creating storage folder: {err}")
        exit(1)
    
    try:
        if file is not None:
            context = load_context(file)
            print(f"Analysis Context loaded from {file}.")
        else:
            context = AnalysisContext(name="New Analysis")
    except Exception as e:
        print(f"Error loading context: {e}")
        raise typer.Exit(code=1)
   
    asyncio.run(Lia(context, file, options).run_cli())

if __name__ == "__main__":
    app()
