from .component_analysis_agent import ComponentAnalysisAgent
from pydantic_ai import RunContext
from typing import List

def getAgent(**kwargs) -> ComponentAnalysisAgent:
    """
    Returns a ComponentAnalysisAgent
    """
    return ComponentAnalysisAgent(**kwargs)

def getAgentTool(**kwargs):
    agent = getAgent(**kwargs)
    async def component_analysis_agent_tool(product: str) -> List[str]:
        print(f"Using ComponentAnalysisTool: {product}")
        
        r = await agent.run(
            f'Please define the components for ${product}'
        )
        return r.data
    return component_analysis_agent_tool