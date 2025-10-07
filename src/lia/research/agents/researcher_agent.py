
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.usage import UsageLimits
from pydantic_ai import UsageLimitExceeded
from pydantic_ai.models.openai import OpenAIModel,OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.mcp import MCPServerStdio,MCPServerSSE,MCPServerHTTP,MCPServerStreamableHTTP
from pydantic import BaseModel,Field

from lia.research.config import ResearchConfig
from lia.system_prompts.network_agent_system_prompt import network_agent_system_prompt
from lia.research import ResearchPipelineOptions
from lia.research import ResearchMaterial

class ResearchAgentDependencies(BaseModel):
    research_config: ResearchConfig
    material: str
   
async def get_researcher_agent(options:ResearchPipelineOptions, mcp_servers:list|None = None):
    print(f"Get Researcher Agent: {options}")
    provider = OpenAIProvider(base_url=options.llm_api_url,api_key=options.llm_api_key)
    llm_model = OpenAIModel(options.model_name,provider=provider) 
    if mcp_servers is None:
      mcp_servers = [
        MCPServerStreamableHTTP(url="http://127.0.0.1:8000/mcp/"), # HS Code semantic search (H6 rollup)
        MCPServerStreamableHTTP(url="http://127.0.0.1:8001/mcp/"), # Research Content Semantic Search
        MCPServerStdio('wikipedia-mcp', ["--transport", "stdio", "--log-level", "INFO", "--enable-cache"] + (["--access-token", options.wikimedia_access_token] if options.wikimedia_access_token is not None else [])),
        MCPServerStdio('uvx', args=["mcp-google-cse"], env={"API_KEY": options.google_api_key, "ENGINE_ID": options.google_custom_search_engine_id,"RESULT_NUM":"50"}),
        MCPServerStdio('uvx', ["mcp-server-fetch"]),
      ]   
  
    agent = Agent(model=llm_model,output_type=ResearchMaterial,retries=5,deps_type=ResearchAgentDependencies,mcp_servers=mcp_servers)
    
    @agent.instructions()
    async def get_instructions(ctx: RunContext[ResearchAgentDependencies]) -> str:
        system_prompt = f"""
You are a research assistant tasked with producing a comprehensive material profile about '{ctx.deps.material}'.

First, categorize the material as "mined", "intermediate", or "other"
- "mined" materials are naturally occuring and extracted from the earth
- "intermediate" materials are compounds or other transformations of one or more materials not generally end products
- "other" is for materials that fall into neither category.

If the material is mined (naturally occuring), the process array should be empty.

If the material is not mined, identify any processes that are used to create the material industrially.

Identify primary uses (end products) of the material.

For each process involved, do the following:
    1. Describe the process clearly and concisely.
    2. List the precursor materials required as inputs to this process.
    3. List the products generated as outputs aside from the target material.
    4. Find at least two high-quality references (scientific articles, government reports, supplier technical documentation) that describe this process. Include the URLs.

Rules:
* Precursors and products should only list the common industrial name of the form of the percursor or byproduct required for a process. 
* Material precursors and products MUST be specifically named. For example,  "various organic compounds", "dye intermediates", "metal", "ore", and "carbon containing fuels" are not specific enough. Use specific names like "aniline" or "benzene" instead.
* If a specific precursor or byproduct is not known, do NOT include it in the list. Do not use "various", "other", "none", "unknown", or similar terms.
* Do not include 'scrap' or 'waste' forms of a material as a precursor or byproduct.
* Precursors are only materials that end up in the process.  Do not include materials that are used in the process but do not end up in the final product.
* Products should only be included if they have a downstream use.  Do not include waste products.  If there are no significant products, leave the products array empty.
* Do not include non-material items (e.g., eletricity, heat, etc.) or commonly available materials (water, water vapor, clay, steam) in the precursors or products lists. "none" is not a valid precursor or byproduct.
* If the material is a mined material, the processes array should be empty.
* If the material is a shipped product, identify its 6 digit HS Code (H6 2022) and the canonical description of that HSCode (do not include any periods in the HS-6 code)

Use the tools you have available to search for additional information as required.  Search existing research data before searching on the web.
        """
        return system_prompt

    @agent.instructions()
    async def get_examples(ctx: RunContext[ResearchAgentDependencies]) -> str:
        examples="""
Then, compile the full material profile as a JSON object matching the following schema:
{
    "name": "Canonical name of material",
    "mined": true|false,  # True if this material is a mined material, False if it is an intermediate or other type
    "aliases": ["Common or industry-specific alternative names"],
    "primary_uses": ["Brief descriptions of how this material is typically used"],
    "processes": [
        {
        "description": "Detailed explanation of one process to produce the material",
        "precursors": ["List of input materials"],
        "products": ["List of non-primary output materials"],
        "references": ["https://example1.com", "https://example2.com"]
        }
        // ... More processes
    ],
    "hs_code": "Harmonized System (HS) code if known",
    "hs_description": "Brief description of the HS classification if known"
}
Ensure all information is well-researched, complete, and technically accurate. Prioritize authoritative sources such as:
    Government agencies (e.g., NIST, EPA, DOE)
    Peer-reviewed journals
    Supplier technical datasheets
    Academic or industrial whitepapers
        """
        return examples
    
    return agent