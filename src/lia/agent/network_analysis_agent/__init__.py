from .network_analysis_agent import NetworkAnalysisAgent

def getAgent(**kwargs) -> NetworkAnalysisAgent:
    """
    Returns a NetworkAnalysisAgent
    """
    return NetworkAnalysisAgent(**kwargs)

def getAgentTool(**kwargs):
    agent = getAgent(**kwargs)
    async def network_analysis_agent_tool(input: str) -> str:
        print(f"Using NetworkAnalysisAgentTool: {str}")
        
        r = await agent.run(
            input
        )
        return r.data
    return network_analysis_agent_tool