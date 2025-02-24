from .message_routing_agent import MessageRoutingAgent
from pydantic_ai import RunContext
from typing import List

def getAgent(**kwargs) -> MessageRoutingAgent:
    """
    Returns a MessageRoutingAgent
    """
    return MessageRoutingAgent(**kwargs)