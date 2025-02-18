# src/lia/cli.py
import typer
from typing_extensions import Annotated
from pathlib import Path
from lia.analysis_context import load_context,AnalysisContext
from lia.lia import Lia
app = typer.Typer()
from dataclasses import dataclass
from pydantic import BaseModel

class Options(BaseModel):
    debug:bool = False

@app.callback(invoke_without_command=True)
def default_command(
    file: Annotated[str, typer.Option("--file", "-f",help="Path to a JSON file containing the context object.")] = None,
    debug: Annotated[bool, typer.Option("--debug","-d",help="Enable debugging output.")] = False
    ):
  
    """
    Start the interactive shell with the provided context.
    """
    
    options = Options(debug=debug)
    
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