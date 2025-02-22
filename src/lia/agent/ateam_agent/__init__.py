from .ateam_agent import ATeamAgent
from pydantic_ai import RunContext
from typing import List

def getAgent(**kwargs) -> ATeamAgent:
    """
    Returns a ATeamAgent
    """
    return ATeamAgent(**kwargs)