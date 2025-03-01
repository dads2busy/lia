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
import os
import json
import asyncio
from lia.supply_chain_network_generator import analyze_product,Product,GenerateSupplyChainNetworkOptions
app = typer.Typer()

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
    options = GenerateSupplyChainNetworkOptions(debug=debug,model_name=model,llm_api_url=llm_api_url,llm_api_key=llm_api_key)
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
    llm_api_url: Annotated[str,None, typer.Option("--llm-api-url", "-u", help="")] = "http://localhost:11434/v1",
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
    options = Options(debug=debug, agent=agent, storage_folder=storage_folder,model=model,llm_api_url=llm_api_url,llm_api_key=llm_api_key)
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
        
        # Assuming Lia also has a run_cli() method similar to ATeam.
        asyncio.run(Lia(context, file, options).run_cli())
    except Exception as e:
        print(f"Error loading context: {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
