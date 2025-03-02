from pydantic_ai import Agent
from dataclasses import dataclass
from pydantic import BaseModel
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel


class PythonDeveloperAgent(Agent):
    """
    Returns a context manager agent for the analysis context.
    """
    def __init__(self, model:OpenAIModel,name:str="PythonDeveloperAgent",tools=[], result_type=str,retries:int=5):
        system_prompt="""
            You are an expert python developer.
            Your job is too look at a piece of code and its error output to make suggestions on how to resolve any errors.
        """
 
        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries)
    