from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from pydantic_ai.models.openai import OpenAIModel
from dataclasses import dataclass
from typing import Union
from lia.agent import load_agent_tool
import json
from pydantic_ai import Agent



class TradeSupplyAgent(Agent):
    def __init__(self, model:OpenAIModel,result_type=str,mcp_servers=[],retries:int=1):
        name = "Trade Supply Agent"
        system_prompt = """
            You are a trade-supply-chain analyst.

            ** TASK **
            Build a directed-acyclic graph (DAG) that traces the value-added
            processing chain for:

                {material_name}

            where {material_name} is supplied by the user as an ordinary
            language string (e.g., “lithium”, “nickel”, “graphite”).

            ** STEPS ** 
            STEP 1 – Identify base HS codes  
            • Search HS 2022 for every 6-digit heading that represents a **natural,
            mined, or crude form** of {material_name}.  
            – Include ores, concentrates, crude/unwrought metal, crude minerals,
                and brines.  
            – Exclude chemicals or alloys unless they occur naturally (e.g., spodumene
                concentrate is OK).  
            • Treat each qualifying HS6 heading as a *root node* in the graph.

            STEP 2 – Build the network  
            Output **one** Markdown ```json``` code-block with this structure:

            {
            "nodes": [
                { "id": "HS6", "label": "<concise description>", "stage": "<Mining|Refinery|Base chem|Intermediate|Component|Assembly|Finished product|Recycling|Other>" },
                …
            ],
            "links": [
                { "source": "HS6_src", "target": "HS6_tgt", "process": "<industrial transformation>" },
                …
            ]
            }

            Rules  
            1. Begin with *all* base HS codes from STEP 1 as roots.  
            2. Add major intermediate chemicals, alloys, catalysts, battery
            precursors, magnet alloys, superalloys, etc., where the material
            remains an essential constituent.  
            3. Reach **≥ 2** distinct end-use product families (e.g., batteries,
            magnets, superalloy parts).  
            4. Show recycling loops if relevant (scrap → refined metal), but keep
            the graph acyclic otherwise.  

            Field definitions  
            * **id**  6-digit HS 2022 heading.  
            * **label** ≤ 60 characters, plain English.  
            * **stage** pick from list above.  
            * **process** 3–10 words summarising the industrial step.

            STEP 3 – Cite HS sources  
            Immediately **after** the JSON block, list concise bullet lines:

            **HS-code references**  
            • HS6 — description  
            • HS6 — description  
            (One line per code; no extra commentary.)

            Formatting constraints  
            * Provide **only** the code block plus the HS-reference bullets—no other
            narrative.  
            * Indent JSON with two spaces.

        """

        tools = [
            # load_agent_tool('component_analysis_agent',model=model)
        ]
        
        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries,mcp_servers=mcp_servers)

