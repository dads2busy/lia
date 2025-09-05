from pydantic_ai import Agent,RunContext
from pydantic import BaseModel,Field
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.mcp import MCPServerStdio,MCPServerStreamableHTTP
from typing import List,Union,Dict,Any
from lia.research.config import ResearchConfig
from lia.research import ResearchPipelineOptions,ResearchMaterial
import json


class MaterialFinderAgentDeps(BaseModel):
  """
  Dependencies for the Material Finder Agent.
  """
  materials: Union[dict[str, ResearchMaterial], None] = Field(default=None, description="A dictionary of materials to classify, keyed by material name or identifier.")  

async def get_material_finder_agent(options: ResearchPipelineOptions, mcp_servers: list|None = None):
    provider = OpenAIProvider(base_url=options.llm_api_url, api_key=options.llm_api_key)
    llm_model = OpenAIModel(options.model_name, provider=provider)
    
    if mcp_servers is None:
      mcp_servers = [
        MCPServerStreamableHTTP(url="http://127.0.0.1:8000/mcp/"), # HS Code semantic search (H6 rollup)
        MCPServerStreamableHTTP(url="http://127.0.0.1:8001/mcp/"), # Research Content Semantic Search
        MCPServerStdio('wikipedia-mcp', ["--transport", "stdio", "--log-level", "INFO"]),
        MCPServerStdio('uvx', args=["mcp-google-cse"], env={"API_KEY": options.google_api_key, "ENGINE_ID": options.google_custom_search_engine_id}),
        MCPServerStdio('uvx', ["mcp-server-fetch"]),
      ]
    
    
    instructions = """
You are a trade classification agent specializing in materials science and international trade standards. 
Your goal is to first see if the material (in the form required by the process) already exists in the materials list below.
If it does, return a the matching ResearchMaterial object.
If it does not, generate a new ResearchMaterial.

Your goal in this task is to identify the best HS Code (Harmonized System, 2022 revision, 6-digit level) that exactly represents the material in the form in question.
Based on your knowledge of trade classifications and chemical/material taxonomy, you must define:
-
The name of the form or variant of the material (the most common, industrially relevant name)
The 6-digit HS Code
The "mined" status of the material (True if it is a mined material, False if it is an intermediate or other type). 
Primary industrial/commerical downstream uses/families of uses for this material
The canonical HS Code description as defined in the HS 2022 nomenclature
Do NOT populate the 'processes' field.

Return your result in the following JSON format:

{
  "name": "example refined form or compound",
  "mined": true|false,  # True if this material is a mined material, False if it is an intermediate or other type
  "aliases": ["aliases of the material or other materials that may be represented by this hs code"]
  "hs_code": "123456",
  "hs_description": "Official HS 2022 description of this code",
  "primary_uses": ["list of primary industrial/commerical downstream uses/families of uses for this material"],
}

- Use the common industrial and commercial name of the material as the name of the form or variant, and ensure it is clear and unambiguous.
- A material is considered "mined" if it is extracted from the earth in its raw form, such as ores or minerals.  If it is chemically separated from another material, it is not considered to be mined.
- Aliases of the material  or other materials that are also represented by this hs code. 
  
The result should be a single ResearchMaterial object (JSON).

    """

    agent = Agent(model=llm_model, output_type=ResearchMaterial, deps_type=MaterialFinderAgentDeps, instructions=instructions, retries=5, mcp_servers=mcp_servers)

    @agent.instructions
    async def known_material_instructions(ctx: RunContext[MaterialFinderAgentDeps]):
        """
         Existing Materials:
        """
        if ctx.deps.materials is None or len(ctx.deps.materials) == 0:
          return ""
        
        p=f"""
Existing Materials:
```json
{json.dumps({name: material.model_dump() for name, material in ctx.deps.materials.items()}, indent=4)}
```
"""
        # print(f"Known Materials in prompt:\n{p[:200]}")
        return p

    return agent