from pydantic_ai import Agent
from dataclasses import dataclass
from pydantic import BaseModel
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel


class ComponentAnalysisAgent(Agent):
    """
    Returns a context manager agent for the analysis context.
    """
    def __init__(self, model:OpenAIModel,name:str="ComponentAnalysisAgent",tools=[],system_prompt=None, result_type=str,retries:int=5):
        base_prompt = ' '.join([
            "You are an expert in product manufacturing.\n"
            "You understand that any product is made up of a number of key systems.\n"
            "The systems are made of components and subcomponents.\n"
            "The components and subcomponents are made of raw materials.\n"
        ])
        if system_prompt is None:
            system_prompt = base_prompt
        else:
            system_prompt = base_prompt + system_prompt
            
        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries)
    