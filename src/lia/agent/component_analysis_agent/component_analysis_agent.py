from pydantic_ai import Agent
from dataclasses import dataclass
from pydantic import BaseModel
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel

model_name = "gpt-4o"
api_key = "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"
default_model = OpenAIModel(model_name=model_name,api_key=api_key)

# default_model = OpenAIModel(model_name="llama3.2",base_url="http://localhost:11434/v1",api_key="none")                
# default_model = OpenAIModel(model_name="llama3.3",base_url="http://localhost:11434/v1",api_key="none") 

class ComponentAnalysisAgent(Agent):
    """
    Returns a context manager agent for the analysis context.
    """
    def __init__(self, model=default_model,name:str="ComponentAnalysisAgent",tools=[],system_prompt=None, result_type=str,retries:int=5):
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
    