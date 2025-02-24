from .reasoning_agent import ReasoningAgent
from pydantic_ai import RunContext
from typing import List

def getAgent(**kwargs) -> ReasoningAgent:
    """
    Returns a ReasoningAgent
    """
    return ReasoningAgent(**kwargs)