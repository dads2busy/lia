from .trade_supply_agent import TradeSupplyAgent
from pydantic_ai import RunContext

def getAgent(**kwargs) -> TradeSupplyAgent:
    """
    Returns a TradeSupplyAgent.
    """
    return TradeSupplyAgent(**kwargs)

