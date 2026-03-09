import json
from typing import Union

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from lia.research import ResearchMaterial, ResearchPipelineOptions
from lia.research.agents.generalist_prompts import GENERALIST_SYSTEM_PROMPT


class MaterialFinderAgentDeps(BaseModel):
    """
    Dependencies for the Material Finder Agent.
    """

    materials: Union[dict[str, ResearchMaterial], None] = Field(
        default=None,
        description="A dictionary of materials to classify, keyed by material name or identifier.",
    )


async def get_material_finder_agent(
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

    """.strip()

    generalist_role_schema_reminder = """
Task: Given a material name (and possibly a suggested HS code), return a single best-match 6-digit HS 2022 classification as a ResearchMaterial.
Return exactly one JSON object with fields:
name, mined, aliases, hs_code, hs_description, primary_uses.
Do NOT populate any processes field.
""".strip()

    if getattr(options, "agent_architecture", "multi") == "generalist":
        instructions = (
            f"{GENERALIST_SYSTEM_PROMPT}\n\n{generalist_role_schema_reminder}".strip()
        )
    else:
        instructions = specialized_instructions

    agent = Agent(
        model=llm_model,
        output_type=ResearchMaterial,
        deps_type=MaterialFinderAgentDeps,
        instructions=instructions,
        retries=5,
        mcp_servers=mcp_servers,
    )

    @agent.instructions
    async def known_material_instructions(ctx: RunContext[MaterialFinderAgentDeps]):
        """
        Existing Materials:
        """
        if ctx.deps.materials is None or len(ctx.deps.materials) == 0:
            return ""

        p = f"""
Existing Materials:
```json
{json.dumps({name: material.model_dump() for name, material in ctx.deps.materials.items()}, indent=4)}
```
"""
        return p

    return agent
