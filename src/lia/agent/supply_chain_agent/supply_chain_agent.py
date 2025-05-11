from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from pydantic_ai.models.openai import OpenAIModel
from dataclasses import dataclass
from typing import Union
from lia.agent import load_agent_tool
import json
from pydantic_ai import Agent



class SupplyChainAgent(Agent):
    def __init__(self, model:OpenAIModel,result_type=str,mcp_servers=[],retries:int=1):
        name = "Supply Chain Agent"
        system_prompt = """
            You are an expert in supply chains.
            Your job is to create a supply chain network given a product.
            The steps are:
            1. Categorize the Product. Use the product categorization tool for this step.
            2. Identify Major Components of products in each category. Be as detailed as possible.
            3. Identify the subcomponents of each major component. Be as detailed as possible
            4. Identify the raw materials required to product each subcomponent. Be as detailed as possible
            5. Combine results into a JSON.  Output the JSON only.
        """
        system_prompt = """
            You are an expert in Supply chains and Technology depdency networks.
        """
        tools = [
            # load_agent_tool('component_analysis_agent',model=model)
        ]
        
        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries,mcp_servers=mcp_servers)

