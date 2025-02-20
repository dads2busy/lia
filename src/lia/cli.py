# src/lia/cli.py
import typer
from typing import Union
from typing_extensions import Annotated
from pathlib import Path
from lia.analysis_context import load_context,AnalysisContext
from lia.lia import Lia
from dataclasses import dataclass
from pydantic import BaseModel
import os

app = typer.Typer()

class Options(BaseModel):
    debug:bool = False,
    agent:Union[str,None] = None
    model_name:str = "djm-tools-8b2"
    model_base_url:str = "http://localhost:11434/v1"
    model_api_key:str = "none"
    storage_folder: str = "./lia"

@app.callback(invoke_without_command=True)
def default_command(
    file: Annotated[str, typer.Option("--file", "-f",help="Path to a JSON file containing an analysis context object.")] = None,
    debug: Annotated[bool, typer.Option("--debug","-d",help="Enable debugging output.")] = False,
    agent: Annotated[Union[str,None], typer.Option("--agent","-a",help="Interact with a different agent than the default." )] = None,
    storage_folder: Annotated[str, typer.Option("--storage", "-s",help="Path to where files can be written and read")] = "./lia"
    ):
  
    """
    Start the interactive shell with the provided context.
    """
    
    options = Options(debug=debug,agent=agent,storage_folder=storage_folder)
    
    try:
        os.makedirs(storage_folder, exist_ok=True)
    except Exception as err:
        print("Error creating storage folder: {err}")
        exit(1)
    
    try:
        if file is not None:
            context = load_context(file)
            typer.echo("Analysis Context loaded from {file}.")
        else:
            context = AnalysisContext(name="New Analysis")
        
        print(f"Starting interactive chat with Lia.\nType '/help' for commands or '/exit' to quit.\n")
        shell = Lia(context,file,options).cmdloop()

    except Exception as e:
        typer.echo(f"Error loading context: {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()