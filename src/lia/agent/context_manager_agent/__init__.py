from .context_manager_agent import ContextManagerAgent

def getAgent(**kwargs) -> ContextManagerAgent:
    """
    Returns a context manager agent for the analysis context.
    """
    return ContextManagerAgent(**kwargs)