
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


async def get_url_scorer_agent(options:ResearchPipelineOptions, mcp_servers:list|None = None ):
    print(f"Get url_scorer_agent: {options}")
    provider = OpenAIProvider(base_url=options.llm_api_url,api_key=options.llm_api_key)
    llm_model = OpenAIModel(options.model_name,provider=provider)
    if mcp_servers is None:
      mcp_servers = [
        MCPServerStdio('uvx', args=["mcp-google-cse"], env={"API_KEY": options.google_api_key, "ENGINE_ID": options.google_custom_search_engine_id}),
        MCPServerStdio('uvx', ["mcp-server-fetch"]),
      ]   
    instructions = """
You are a reference validation agent tasked with scoring the credibility and trustworithiness of web pages based on their source URLs.
You will be given an URL and your task is to score the URL based on its source quality.

Given a **url**, assign a **source_quality_score** between `0.0` and `1.0` (inclusive), following this scale:
- 1.0 : Highly authoritative (e.g., peer-reviewed papers, government reports, scientific publishers)
        Examples:
          https://www.nature.com
          https://pubmed.ncbi.nlm.nih.gov
          https://www.sciencedirect.com
          https://www.nist.gov
          https://www.epa.gov
          https://www.fda.gov
          https://www.cdc.gov
          https://www.ncbi.nlm.nih.gov
          https://www.osti.gov
- 0.8 : Supplier datasheets, technical industry white papers
        Examples:
          https://www.sigmaaldrich.com
          https://www.basf.com
          https://www.3m.com
          https://www.dow.com
          https://www.ti.com (Texas Instruments)
          https://www.intel.com
- 0.6 : Educational sources (Wikipedia, LibreTexts, university-hosted material)
        Examples:
          https://en.wikipedia.org
          https://chem.libretexts.org
          https://ocw.mit.edu
          https://courses.lumenlearning.com
          https://www.khanacademy.org
          https://web.mit.edu
          https://www.stanford.edu
- 0.4 : Commercial websites with unclear authorship
        Examples:
          https://www.britannica.com
          https://www.chemicalsafetyfacts.org
          https://www.thoughtco.com
          https://www.instructables.com
          https://www.sciencing.com
- 0.2 : Blogs, message boards, social media
        Examples:
          https://medium.com
          https://reddit.com
          https://quora.com
          https://stackexchange.com
          https://hackaday.com
          https://wordpress.com
          https://x.com (formerly Twitter)
- 0.0 : Spam, broken pages, empty content
        These vary. Add logic to detect:
          Dead domains
          Sites with <200 words
          4xx/5xx status codes
          Known spam domains

""" 
  
    agent = Agent(model=llm_model,output_type=float,instructions=instructions,retries=5,mcp_servers=mcp_servers)
   
    return agent