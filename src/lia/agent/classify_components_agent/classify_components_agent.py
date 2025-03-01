from pydantic_ai import Agent
from dataclasses import dataclass
from pydantic import BaseModel
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel


class RawCompOutput(BaseModel):
    raw_materials: list[str]
    components: list[str]
    software: list[str]
    manufacturing_equipment: list[str]

class ClassifyComponentsAgent(Agent):
    """
        ClassifyComponentsAgent distinguishes between raw materials and components.
    """
    def __init__(self, model:OpenAIModel,name:str="ClassifyComponentsAgent",tools=[], result_type=RawCompOutput,retries:int=5):
        system_prompt = f"""
            Distinguish between raw components (elemental materials, basic commodities) and components.
            Categorize the individual components into one of these categories: 'raw_materials', 'manufacturing_equipment', 'software', or 'components'. 'components' should represent everything not in the prior categories.
            Raw materials should be considered to items such as: 
            elements, chemicals, mined materials, nuts, bolts,lugs, screws,washers,brackets,clamps, metal plates, extrusions,
            platics,cables, wires, gaskets,fuses,buttons,labels,clips, connectors, cable management,electrical terminals,containers,
            simcard, antenna, PCB, "printed circuit board","voltage regulator", thermistor, photodiode,"soldering and welding supplies",
            "Power supply", "mounting hardware", capacitors,resistors,"glass","common circuits",sealants, wood,glue,adhesives,knobs
             and any other commodoties.
            Return an object containing an array for each category.
            For any elemental raw materials, convert their name to the Element symbol.
            Respond with JSON.
        """
            
        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries)
    