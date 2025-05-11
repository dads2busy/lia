from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from pydantic_ai.models.openai import OpenAIModel
# from lia.tools import add_analysis_question, set_analysis_objective, update_analysis_question,delete_analysis_question
# from lia.tools import add_analysis_constraint, update_analysis_constraint, delete_analysis_constraint,get_analysis_context
from lia.analysis_context import AnalysisContext
from dataclasses import dataclass
from typing import Union
import json


class NetworkAnalysisAgent(Agent):
    def __init__(self, model:OpenAIModel,retries:int=1):
        name = "Network Analysis Agent"
        system_prompt = (
                "You are an expert in network and graph analysis\n"
                "You have tools that can examine networks and extract information and statistics from the network.\n"
                "You have access to all of the algorithms that Stanford SNAP provides.\n"
                "Your job is to analyze the provided network.\n"
                "If you don't have a network, respond with an error saying so.\n"
        )  
        tools = []
        
        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=str, tools=tools,retries=retries)

