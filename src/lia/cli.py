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
import asyncio

app = typer.Typer()

class Options(BaseModel):
    debug: bool = False
    reasoning:bool = False
    agent: Union[str, None] = None
    storage_folder: str = "./lia"
    model_name: str = "llama3.2"
    model_base_url: str | None = "http://192.168.5.11:11434/v1"
    model_api_key: str = "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"


@app.command()
def reasoner(
    file: Annotated[str, typer.Option("--file", "-f", help="Path to a JSON file containing an analysis context object.")] = None,
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debugging output.")] = False,
    reasoning: Annotated[bool, typer.Option("--reasoning", "-r", help="Show reasoning discussion.")] = False,
    agent: Annotated[Union[str, None], typer.Option("--agent", "-a", help="Interact with a different agent than the default.")] = None,
    storage_folder: Annotated[str, typer.Option("--storage", "-s", help="Path to where files can be written and read")] = "./lia"
):
    """
    Start the interactive chat with reasoner.
    """
    print("Starting Reasoner")
    options = Options(debug=debug, agent=agent, storage_folder=storage_folder,reasoning=reasoning)
    
    try:
        os.makedirs(storage_folder, exist_ok=True)
    except Exception as err:
        print(f"Error creating storage folder: {err}")
        exit(1)
    
    try:
        ateam_shell = Reasoner(file, options)
        asyncio.run(ateam_shell.run_cli())
    except Exception as e:
        print(f"Error loading context: {e}")
        raise typer.Exit(code=1)

@app.command()
def ateam(
    file: Annotated[str, typer.Option("--file", "-f", help="Path to a JSON file containing an analysis context object.")] = None,
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debugging output.")] = False,
    reasoning: Annotated[bool, typer.Option("--reasoning", "-r", help="Show reasoning discussion.")] = False,
    agent: Annotated[Union[str, None], typer.Option("--agent", "-a", help="Interact with a different agent than the default.")] = None,
    storage_folder: Annotated[str, typer.Option("--storage", "-s", help="Path to where files can be written and read")] = "./lia"
):
    """
    Start the interactive chat with ATeam.
    """
    print("Starting ATeam")
    options = Options(debug=debug, agent=agent, storage_folder=storage_folder,reasoning=reasoning)
    
    try:
        os.makedirs(storage_folder, exist_ok=True)
    except Exception as err:
        print(f"Error creating storage folder: {err}")
        exit(1)
    
    try:
        ateam_shell = ATeam(file, options)
        asyncio.run(ateam_shell.run_cli())
    except Exception as e:
        print(f"Error loading context: {e}")
        raise typer.Exit(code=1)

@app.command()
def lia(
    file: Annotated[str, typer.Option("--file", "-f", help="Path to a JSON file containing an analysis context object.")] = None,
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debugging output.")] = False,
    agent: Annotated[Union[str, None], typer.Option("--agent", "-a", help="Interact with a different agent than the default.")] = None,
    storage_folder: Annotated[str, typer.Option("--storage", "-s", help="Path to where files can be written and read")] = "./lia"
):
    """
    Start the interactive chat with Lia.
    """
    options = Options(debug=debug, agent=agent, storage_folder=storage_folder)
    
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
