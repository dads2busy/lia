from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from lia.research import ContentReviewResult, ResearchPipelineOptions
from lia.research.agents.generalist_prompts import GENERALIST_SYSTEM_PROMPT

default_mcp_servers = []


async def get_reference_reviewer_agent(
    options: ResearchPipelineOptions, mcp_servers: list = default_mcp_servers
):
    provider = OpenAIProvider(base_url=options.llm_api_url, api_key=options.llm_api_key)
    llm_model = OpenAIModel(options.model_name, provider=provider)

    specialized_instructions = """
You are a reference reviewer agent tasked with evaluating whether a given body of content can serve as a valid reference for a specific process description.

You will be provided with:
    * The text content extracted from a web page or document (may be messy, contain unrelated navigation or site metadata).
    * A description of a process, expected precursors, and products.

Your goal is to determine whether any part of the content provides a meaningful and credible description of the process. The entire content does not need to be relevant — only that the process is described clearly somewhere within it.
A valid reference means that the process, even if surrounded by unrelated text, is sufficiently described to support downstream research or documentation.
Evaluate the content using the following scale:
    1.0: The process is described in detail. All precursors and products are explicitly identified and explained.
    0.8: The process and all precursors are clearly described. Some products are missing or only briefly mentioned.
    0.6: The process is described, but some precursors and products are missing or vague.
    0.4: The process is only vaguely described. Most precursors and products are missing or unclear.
    0.2: The content is largely irrelevant to the process, or the process is not described at all.
    0.0: The content is completely unrelated or not credible (e.g., spam, boilerplate, or entirely off-topic).

Please be tolerant of noisy formatting, but focus on content that supports the process description.

Return a JSON object with the following fields:
```json
{
    "score": float,  # The score between 0.0 and 1.0.
    "reason": str,  # A brief explanation of the score given.
}
```
    """.strip()

    generalist_role_schema_reminder = """
Task: Given a process description and reference content, score whether the content supports the process.
Return exactly one JSON object with fields:
score (float 0.0..1.0) and reason (string).
Return JSON only; no extra commentary.
""".strip()

    if getattr(options, "agent_architecture", "multi") == "generalist":
        instructions = (
            f"{GENERALIST_SYSTEM_PROMPT}\n\n{generalist_role_schema_reminder}"
        ).strip()
    else:
        instructions = specialized_instructions

    agent = Agent(
        model=llm_model,
        output_type=ContentReviewResult,
        instructions=instructions,
        retries=5,
        mcp_servers=mcp_servers,
    )

    return agent
