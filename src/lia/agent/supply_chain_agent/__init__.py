from .supply_chain_agent import SupplyChainAgent
from pydantic_ai import RunContext

def getAgent(**kwargs) -> SupplyChainAgent:
    """
    Returns a SupplyChainAgent.
    """
    return SupplyChainAgent(**kwargs)

def getAgentTool(**kwargs):
    agent = getAgent(**kwargs)
    async def agent_tool(ctx: RunContext[None], product: str) -> str:
        print(f"Using SupplyChainAgentTool: {product}")
        
        r = await agent.run(
            f'Please generate a supply chain network for ${product}',
            usage = ctx.usage
        )
        return r.data