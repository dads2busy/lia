
from typing import List
from pydantic_ai import Agent
import anyio
from typing import List, Optional

class MCPServerManager:
    def __init__(self, agents: List[Agent]):
        self.agents = agents
        self._contexts = []
        self._entered = []

    async def __aenter__(self):
        self._contexts.clear()
        self._entered.clear()
        for agent in self.agents:
            ctx = agent.run_mcp_servers()
            self._contexts.append(ctx)
            try:
                await ctx.__aenter__()  # must not be in separate tasks!
                self._entered.append(ctx)
            except Exception as e:
                # Cleanup entered contexts on failure
                for entered in reversed(self._entered):
                    await entered.__aexit__(None, None, None)
                raise RuntimeError(f"Failed to enter MCP server for agent: {agent}") from e
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for ctx in reversed(self._entered):
            try:
                await ctx.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                print(f"Warning: Error while exiting MCP server context: {e}")


def launch_all_mcp_servers(agents: List[Agent]) -> MCPServerManager:
    return MCPServerManager(agents)
