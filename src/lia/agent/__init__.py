import importlib
import pkgutil
from dataclasses import dataclass
from lia.analysis_context import AnalysisContext
from pydantic_ai import RunContext, Tool
@dataclass
class AgentDeps:
   analysis_context: AnalysisContext

def load_agent_tool(agent_name, **kwargs):
    print(f"Get Agent Tool: {agent_name}")
    module = load_agent_module(agent_name)
    
    if not hasattr(module, 'getAgentTool'):
        raise AttributeError(f"Module '{agent_name}' does not have a getAgentTool() function.")

    return module.getAgentTool(**kwargs) 
 
def load_agent(agent_name, **kwargs):
    print(f"Get Agent Instance: {agent_name}")

    module = load_agent_module(agent_name)
    
    if not hasattr(module, 'getAgent'):
        raise AttributeError(f"Module '{agent_name}' does not have a getAgent() function.")

    return module.getAgent(**kwargs)

def load_agent_module(agent_name):
    """
    Dynamically load an agent module and return the agent instance.

    Each module in this package should define a getAgent() function that accepts
    keyword arguments to initialize the agent. The first parameter is the module name,
    and all additional parameters are passed directly to getAgent().

    Example:
        agent = load_agent("context_manager_agent", model=self.model)

    Parameters:
        agent_name (str): The name of the agent module (without the .py extension).
        **kwargs: Additional keyword arguments to be passed to the module's getAgent() function.

    Returns:
        The agent instance returned by the module's getAgent() function.

    Raises:
        ImportError: If the module cannot be imported.
        AttributeError: If the module does not define a getAgent() function.
    """
    print(f"Importing Agent Model: {agent_name}")
    try:
        # Import the module dynamically from the current package.
        module = importlib.import_module(f'.{agent_name}', package=__package__)
    except ModuleNotFoundError as e:
        raise ImportError(f"Agent module '{agent_name}' not found in package '{__package__}'.") from e

    if not hasattr(module, 'getAgent'):
        raise AttributeError(f"Module '{agent_name}' does not have a getAgent() function.")

    # Call the getAgent() function with all keyword arguments.
    return module

def list_agents():
    """
    Returns a list of available agent module names in the current package.

    This function iterates over all modules in the package directory and returns
    those module names that define a getAgent() function.

    Returns:
        List[str]: A list of agent module names.
    """
    agents = []
    # Iterate over all modules in the package directory.
    for finder, name, ispkg in pkgutil.iter_modules(__path__):
        # Skip any sub-packages.
        # if not ispkg:
        try:
            module = importlib.import_module(f'.{name}', package=__package__)
            if hasattr(module, 'getAgent'):
                agents.append(name)
        except Exception:
            # If there's an error importing the module, skip it.
            continue
    return agents
