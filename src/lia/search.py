from pydantic_graph import BaseNode,End,GraphRunContext,Graph
from typing import List,Any,Union
from dataclasses import dataclass,field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel,OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic import BaseModel,Field
import asyncio
from pydantic_ai.mcp import MCPServerStdio,MCPServerHTTP
from pydantic_ai.usage import UsageLimits
from lia.util.mcp_server_manager import launch_all_mcp_servers
from pydantic_ai.mcp import MCPServerStdio,MCPServerStreamableHTTP
import os
class SearchOptions(BaseModel):
    model_name: str = "llama3.3"
    llm_api_url: str | None = "http://localhost:11434/v1"
    llm_api_key: str = ""
    google_api_key: str | None = None
    google_custom_search_engine_id: str | None = None


async def llmsearch(query: str, options: SearchOptions=SearchOptions()):
    print(f"Search Options: {options}")    
    provider = OpenAIProvider(base_url=options.llm_api_url,api_key=options.llm_api_key)
    default_model = OpenAIModel(options.model_name,provider=provider)
    system_prompt = f"""You are a researcher.  Perform a search with the given prompt and return the most relevant results.  Use the google search tool for performing the queries."""    
    mcp_servers = [
        MCPServerStdio('uvx', args=["mcp-google-cse"],env={"API_KEY":options.google_api_key,"ENGINE_ID":options.google_custom_search_engine_id}),
    ]
    agent = Agent(model=default_model, output_type=str,system_prompt=system_prompt,mcp_servers=mcp_servers,output_retries=5)
    
    async with launch_all_mcp_servers([agent]):
        print("Launched MCP Servers")
        results = await agent.run(user_prompt=f"The query is '{query}'")
        print(results.output)
        
