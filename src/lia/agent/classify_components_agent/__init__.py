from .classify_components_agent import ClassifyComponentsAgent
from pydantic_ai import RunContext
from typing import List

def getAgent(**kwargs) -> ClassifyComponentsAgent:
    """
    Returns a ClassifyComponentsAgent
    """
    return ClassifyComponentsAgent(**kwargs)
