import json
import os
from pathlib import Path
from typing import List, Optional
import typer
from typing import List,Dict,Any,Union
from pydantic import BaseModel,Field

class ResearchConfig(BaseModel):
    material: str
    materials: List[str] = Field(default_factory=List)
    references: List[str] = Field(default_factory=List)
    products: List[str] = Field(default_factory=List)
    
CONFIG_FILENAME = "research_config.json"
ENV_RESEARCH_FOLDER = "LIA_RESEARCH_FOLDER"

def load_config(folder: Union[Path,str]) -> ResearchConfig:
    if isinstance(folder, str):
        folder = Path(folder)
        
    config_path = folder / CONFIG_FILENAME
    if not config_path.exists():
        typer.echo(f"Error: No config found at {config_path}", err=True)
        raise typer.Exit(1)
    with config_path.open("r") as f:
        d=json.load(f)
        return ResearchConfig(**d)

def save_config(folder: Path, config: ResearchConfig):
    print(f"Saving config to {folder / CONFIG_FILENAME}")
    config_path = folder / CONFIG_FILENAME
    with config_path.open("w") as f:
        json.dump(config.model_dump(), f, indent=2)