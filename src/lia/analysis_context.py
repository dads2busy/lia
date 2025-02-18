# src/mytool/context.py
import json
from dataclasses import dataclass
from pathlib import Path
from pydantic import BaseModel, ValidationError
from typing import List, Optional,Union

class ContextModel(BaseModel):
    name: str
    verbose: bool = False


class PreliminaryAnalysis(BaseModel):
    module: str
    available_data: List[str]
    available_tools: List[str]
    suggested_plan: str

class KeyQuestion(BaseModel):
    question: str
    user_question: bool
    preliminary_analysis: List[PreliminaryAnalysis]

class Plan(BaseModel):
    steps: List[str]=[]

class AnalysisContext(BaseModel):
    name: str = ''
    objective: str = ''
    key_questions: List[str] = []
    constraints: List[str] = []
    methodology: Plan = Plan()  


def load_context(filepath: Path) -> AnalysisContext:
    """
    Load and validate the context from a JSON file.
    """
    try:
        with open(filepath,"r") as f:
            data = json.load(f)
    except Exception as e:
        raise Exception(f"Failed to read file {filepath}: {e}")

    try:
        validated = AnalysisContext(**data)
    except ValidationError as e:
        raise Exception(f"Context validation error: {e}")

    return validated