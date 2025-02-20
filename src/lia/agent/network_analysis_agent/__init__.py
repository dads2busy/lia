from .network_analysis_agent import NetworkAnalysisAgent

def getAgent(**kwargs) -> NetworkAnalysisAgent:
    """
    Returns a NetworkAnalysisAgent
    """
    return NetworkAnalysisAgent(**kwargs)

def getAgentTool(**kwargs):
    agent = getAgent(**kwargs)
    async def agent_tool(ctx: RunContext[None], input: str) -> str:
        print(f"Using NetworkAnalysisAgentTool: {str}")
        
        r = await agent.run(
            input,
            usage = ctx.usage
        )
        return r.data