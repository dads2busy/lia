from pydantic_ai import Agent
from dataclasses import dataclass

class ComponentAnalysisAgent(Agent):
    """
    Returns a context manager agent for the analysis context.
    """
    def __init__(self, model,retries:int=1):
        name = "Component Analysis Agent"
        system_prompt = (
            "You are an expert in categorization of products."
            "identify if there are different types of this product.\n"
            "The difference between types may exist becuase of differences in manufacturing techniques, product use case, or materials.\n"
            "For example, batteries can be lead acid, lithium-ion, Nickel metal hydride, nickel-cadmium, etc.\n"
            "The items in the list should use their industry standard name and should have no adornments.\n"
            "Output should be a valid JSON array."
        )
          
        tools = []
        
        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=str, tools=tools,retries=retries)
    