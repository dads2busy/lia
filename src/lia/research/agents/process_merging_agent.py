from pydantic_ai import Agent,RunContext
from pydantic import BaseModel,Field
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.mcp import MCPServerStdio,MCPServerStreamableHTTP
from typing import List,Union,Dict,Any

from lia.research.config import ResearchConfig
from lia.research import ResearchPipelineOptions,MaterialProcess,ResearchMaterial,RemoveProcessInstruction,AddMaterialToProcessInstruction,AddProcessInstruction,RemoveMaterialFromProcessInstruction,SetProcessInstruction,AddReferenceToProcessInstruction

async def get_process_merging_agent(options: ResearchPipelineOptions, mcp_servers: list|None = None):
    provider = OpenAIProvider(base_url=options.llm_api_url, api_key=options.llm_api_key)
    llm_model = OpenAIModel(options.model_name, provider=provider)
    
    if mcp_servers is None:
      mcp_servers = [
        MCPServerStreamableHTTP(url="http://127.0.0.1:8000/mcp/"), # HS Code semantic search (H6 rollup)
        MCPServerStreamableHTTP(url="http://127.0.0.1:8001/mcp/"), # Research Content Semantic Search
        MCPServerStdio('wikipedia-mcp', ["--transport", "stdio", "--log-level", "INFO", "--enable-cache"] + (["--access-token", options.wikimedia_access_token] if options.wikimedia_access_token is not None else [])),
        MCPServerStdio('uvx', args=["mcp-google-cse"], env={"API_KEY": options.google_api_key, "ENGINE_ID": options.google_custom_search_engine_id}),
        MCPServerStdio('uvx', ["mcp-server-fetch"]),
      ]  
    instructions = """
  You are a manufacturing expert.  You will be provided with a set of manufacturing processes that are duplicates or very similar.
  Your task is to merge these processes into a single process that captures the essence of all the provided processes.
  
  In many cases the specific precursors and products may be slightly different, but they are considered the same because they are all part of the same HS Code.
  You can describe that there are slight variations in the process and that the specifics of the precursors and products may vary, but they are all the same HS Code and process families.
  Use only the best references from the provided processes.
  Do not include an ID in the new Material process.
  
  Return a new MaterialProcess object that combines the information from all the provided processes.
  
  """
    
    agent = Agent(model=llm_model, output_type=MaterialProcess, retries=5, mcp_servers=mcp_servers) 
    
    return agent
  
  
