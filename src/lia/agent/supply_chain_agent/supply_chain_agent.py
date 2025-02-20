from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from pydantic_ai.models.openai import OpenAIModel
from lia.tools import add_analysis_question, set_analysis_objective, update_analysis_question,delete_analysis_question
from lia.tools import add_analysis_constraint, update_analysis_constraint, delete_analysis_constraint,get_analysis_context
from lia.analysis_context import AnalysisContext
from dataclasses import dataclass
from typing import Union
from lia.agent import load_agent_tool
import json

class SupplyChainAgent(Agent):
    def __init__(self, model,retries:int=1):
        name = "Supply Chain Agent"
        system_prompt = (
            "You are an expert in supply chains.\n"
            "Your job is to create a supply chain network given a product.\n"
            "The steps are:\n"
            "1. Categorize the Product. Use the product categorization tool for this step.\n"
            "2. Identify Major Components of products in each category. Be as detailed as possible.\n"
            "3. Identify the subcomponents of each major component. Be as detailed as possible\n"
            "4. Identify the raw materials required to product each subcomponent. Be as detailed as possible\n"
            "5. Combine results into a JSON.  Output the JSON only."
        )  
        tools = [
            load_agent_tool('component_analysis_agent',model=model)
        ]
        
        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=str, tools=tools,retries=retries)

