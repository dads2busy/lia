from .supply_chain_agent import SupplyChainAgent
from pydantic_ai import RunContext

def getAgent(**kwargs) -> SupplyChainAgent:
    """
    Returns a SupplyChainAgent.
    """
    return SupplyChainAgent(**kwargs)

def getAgentTool(**kwargs):
    agent = getAgent(**kwargs)
    async def supply_chain_agent_tool(product: str) -> str:
        print(f"Using SupplyChainAgentTool: {product}")
        
        r = await agent.run(
            f'Please generate a supply chain network for ${product}'
        )
        return r.data
    return supply_chain_agent_tool