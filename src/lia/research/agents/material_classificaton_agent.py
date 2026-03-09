from typing import Union

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from lia.research import ResearchMaterial, ResearchPipelineOptions
from lia.research.agents.generalist_prompts import GENERALIST_SYSTEM_PROMPT


class MaterialClassificatonAgentDeps(BaseModel):
    """
    Dependencies for the Material Classification Agent.
    """

    materials: Union[dict[str, ResearchMaterial], None] = Field(
        default=None,
        description="A dictionary of materials to classify, keyed by material name or identifier.",
    )


async def get_material_classification_agent(
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
Your goal is to identify all relevant HS Codes (Harmonized System, 2022 revision, 6-digit level) that represent intermediate, mined, refined, or compound forms where a given set of materials are a significant precusor or product.
You must include intermediate materials such that all nodes can be traced back to a mined or refined form, and all intermediate forms must be included in the classification.
The ultimate goal is to complete a completely connected graph of materials, so it is imporant to identify all forms of the material, including intermediates and compounds.

You will be provided with a list of materials.  Based on your knowledge of trade classifications and chemical/material taxonomy, you must:

Identify any HS Codes that pertain to:
The raw, mined form of the material
The refined or purified form of the material
Intermediate forms used in industrial processes
Compounds where one of the materials or one of the newly identified materials is a significant precursor or product

Ensure the HS Codes are:
From the HS 2022 system
At the 6-digit level only

For each identified HS Code, return:
The name of the form or variant of the material
The 6-digit HS Code
The "mined" status of the material (True if it is a mined material, False if it is an intermediate or other type).
A material is considered "mined" if it is extracted from the earth in its raw form, such as ores or minerals.  If it is chemically separated from another material, it is not considered to be mined.
Aliases of the material  or other materials that are also represented by this hs code
Primary industrial/commerical downstream uses/families of uses for this material
The canonical HS Code description as defined in the HS 2022 nomenclature
Do NOT populate the 'processes' field.

Use the common industrial and commercial name of the material as the name of the form or variant, and ensure it is clear and unambiguous.

Return your results in the following JSON format:
[
  {
    "name": "example refined form or compound",
    "mined": true|false,  # True if this material is a mined material, False if it is an intermediate or other type
    "aliases": ["aliases of the material or other materials that may be represented by this hs code"]
    "hs_code": "123456",
    "hs_description": "Official HS 2022 description of this code",
    "primary_uses": ["list of primary industrial/commerical downstream uses/families of uses for this material"],
  }
]
"""

    generalist_role_schema_reminder = """
Task: Identify all relevant 6-digit HS 2022 codes (mined, refined, intermediates, and key compounds) for the provided material(s).
Return a JSON array of ResearchMaterial objects with fields:
name, mined, aliases, hs_code, hs_description, primary_uses.
Do NOT populate any processes field.
"""

    if getattr(options, "agent_architecture", "multi") == "generalist":
        instructions = (
            f"{GENERALIST_SYSTEM_PROMPT}\n\n{generalist_role_schema_reminder}".strip()
        )
    else:
        instructions = specialized_instructions.strip()

    agent = Agent(
        model=llm_model,
        output_type=list[ResearchMaterial],
        deps_type=MaterialClassificatonAgentDeps,
        instructions=instructions,
        retries=5,
        mcp_servers=mcp_servers,
    )

    @agent.instructions
    async def known_material_instructions(
        ctx: RunContext[MaterialClassificatonAgentDeps],
    ):
        """
        Generate instructions based on the known materials.
        """
        if ctx.deps.materials is None or len(ctx.deps.materials) == 0:
            return ""

        material_list = "\n".join(
            [
                f"- HS Code: {hscode} Material: {material.name}"
                for hscode, material in ctx.deps.materials.items()
            ]
        )
        return f"""
Here is a list of materials with HS Codes that have already been classified
{material_list}
"""

    return agent
