from .component_analysis_agent import ComponentAnalysisAgent
from pydantic_ai import RunContext

def getAgent(**kwargs) -> ComponentAnalysisAgent:
    """
    Returns a ComponentAnalysisAgent
    """
    return ComponentAnalysisAgent(**kwargs)

def getAgentTool(**kwargs):
    agent = getAgent(**kwargs)
    async def agent_tool(product: str) -> str:
        print(f"Using ComponentAnalysisTool: {product}")
        
        r = await agent.run(
            f'Please define the components for ${product}'
        )
        return r.data
    return agent_tool