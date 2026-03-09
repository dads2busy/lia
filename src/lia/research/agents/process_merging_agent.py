from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from lia.research import MaterialProcess, ResearchPipelineOptions
from lia.research.agents.generalist_prompts import GENERALIST_SYSTEM_PROMPT


async def get_process_merging_agent(
    options: ResearchPipelineOptions, mcp_servers: list[object] | None = None
):
    provider = OpenAIProvider(base_url=options.llm_api_url, api_key=options.llm_api_key)
    llm_model = OpenAIModel(options.model_name, provider=provider)

    # Default MCP servers for this agent are the local HTTP MCP services only.
    # External stdio-based tools (uvx / google-cse / fetch / wikipedia) are intentionally
    # NOT started by default because they often fail to initialize depending on the
    # local environment, and the pipeline currently requires all MCP servers to enter
    # successfully before any work can begin.
    if mcp_servers is None:
        mcp_servers = [
            MCPServerStreamableHTTP(
                url="http://127.0.0.1:8000/mcp/"
            ),  # HS Code semantic search (H6 rollup)
            MCPServerStreamableHTTP(
                url="http://127.0.0.1:8001/mcp/"
            ),  # Research Content Semantic Search
        ]

    specialized_instructions = """
  You are a manufacturing expert.  You will be provided with a set of manufacturing processes that are duplicates or very similar.
  Your task is to merge these processes into a single process that captures the essence of all the provided processes.

  In many cases the specific precursors and products may be slightly different, but they are considered the same because they are all part of the same HS Code.
  You can describe that there are slight variations in the process and that the specifics of the precursors and products may vary, but they are all the same HS Code and process families.
  Use only the best references from the provided processes.
  Do not include an ID in the new Material process.

  Return a new MaterialProcess object that combines the information from all the provided processes.
  """.strip()

    generalist_role_schema_reminder = """
Task: Merge a set of duplicate or highly similar processes into one consolidated MaterialProcess.
Return exactly one JSON object matching the MaterialProcess schema (no id field in the output).
Prefer the best references from the inputs and keep the description clear and complete.
""".strip()

    if getattr(options, "agent_architecture", "multi") == "generalist":
        instructions = (
            f"{GENERALIST_SYSTEM_PROMPT}\n\n{generalist_role_schema_reminder}"
        ).strip()
    else:
        instructions = specialized_instructions

    agent = Agent(
        model=llm_model,
        output_type=MaterialProcess,
        instructions=instructions,
        retries=5,
        mcp_servers=mcp_servers,
    )

    return agent
