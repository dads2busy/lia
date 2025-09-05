#!/usr/bin/env python3
import typer
import asyncio
import json
from contextlib import asynccontextmanager

from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession
from mcp import JSONRPCResponse

app = typer.Typer(help="CLI for interacting with MCP servers (stdio or HTTP/SSE).")

# Patch: buffer SSE chunks until complete JSON message
class PatchedClientSession(ClientSession):
    async def _read_loop(self):
        buffer = b""
        async for chunk in self.read:
            buffer += chunk
            try:
                response = JSONRPCResponse.model_validate_json(buffer.decode("utf-8"))
                await self._on_message(response)
                buffer = b""
            except Exception as e:
                if "Expecting value" in str(e) or "EOF" in str(e):
                    continue  # incomplete, wait for more
                raise  # genuine error

@asynccontextmanager
async def get_session(server: str, transport: str):
    if transport == "stdio":
        async with stdio_client(program=server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    elif transport == "http":
        async with streamablehttp_client(url=server) as (read, write, _):
            async with PatchedClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        raise ValueError("Transport must be 'stdio' or 'http'")

@app.command()
def list_tools(
    server: str = typer.Option(..., help="Path to stdio server or HTTP SSE URL"),
    transport: str = typer.Option(..., help="Either 'stdio' or 'http'"),
):
    """List available tools on the MCP server."""
    async def _():
        async with get_session(server, transport) as sess:
            result = await sess.list_tools()
            for tool in result.tools:
                print(f"- {tool.name}: {tool.description or '<no description>'}")
    asyncio.run(_())

@app.command()
def run_tool(
    server: str = typer.Option(..., help="Path or URL to MCP server"),
    transport: str = typer.Option(..., help="Either 'stdio' or 'http'"),
    tool: str = typer.Argument(..., help="Name of the tool to run"),
    params: list[str] = typer.Option([], "--param", "-p", help="Parameters as key=value"),
):
    """Invoke a tool with optional parameters."""
    async def _():
        async with get_session(server, transport) as sess:
            kwargs = {}
            for param in params:
                if "=" not in param:
                    raise typer.BadParameter(f"Bad format '{param}', expected key=value")
                k, v = param.split("=", 1)
                kwargs[k] = json.loads(v) if (v.startswith("{") or v.startswith("[")) else v

            print(f"kwargs: {kwargs}")
            result = await sess.call_tool(tool, kwargs)
            print(json.dumps(result.dict(), indent=2))
    asyncio.run(_())

if __name__ == "__main__":
    app()
