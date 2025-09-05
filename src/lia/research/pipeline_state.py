import json
import os
from pathlib import Path
from typing import List, Optional
import typer
from typing import List,Dict,Any,Union
from pydantic import BaseModel,Field
from lia.research import ResearchMaterial,ResearchPipelineOptions,ResearchPipelineState, MaterialProcess
from lia.research.config import ResearchConfig


    
STATE_FILENAME = "research_state.json"

def load_state(folder: Path,state:ResearchPipelineState) -> ResearchPipelineState:
    state_file = folder / STATE_FILENAME
    if not state_file.exists():
        typer.echo(f"Error: No state found at {state_file}", err=True)
        raise FileNotFoundError(f"Error: No state found at {state_file}")
                                
    with state_file.open("r") as f:
        research_state = json.load(f)
        
        if 'materials' in research_state:
            state.materials = {k: ResearchMaterial(**v) for k, v in research_state["materials"].items()}  
        
        if 'processes' in research_state:
            state.processes = {k: MaterialProcess(**v) for k, v in research_state["processes"].items()}  
        

            
        return state

def save_state(folder: Path, state: ResearchPipelineState, silent: bool = False):
    if not silent:
        print(f"Saving state to {folder / STATE_FILENAME}")
        
    state_file = folder / STATE_FILENAME
    with state_file.open("w") as f:
        # save_state = {
        #     "materials": {k: v.model_dump() for k, v in state.materials.items()},
        # }
        json.dump(state.model_dump(), f, indent=2)
        
def backup_state(folder: Path, backup_filename: Optional[str] = None):
    state_file = folder / STATE_FILENAME
    if not state_file.exists():
        print("No state file found to backup.")
        return
    
    if backup_filename is None:
        backup_filename = STATE_FILENAME + ".backup"
    
    backup_file = folder / backup_filename
    with state_file.open("rb") as src, backup_file.open("wb") as dst:
        dst.write(src.read())