import os
import json
import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
import nest_asyncio

from pyxavi import Dictionary, Config
from pitxu.lib.abstract.pyxavi import PyXavi

# TEST MCP n.3

# {
#   "mcpServers": {
#     "mcp_trivago_search": {
#       "url": "https://mcp.trivago.com/mcp"
#     }
#   }
# }

class TrivagoMCPClient(PyXavi):
    """
    A client for interacting with Trivago through the Trivago MCP (Model Context Protocol) server.
    
    This client establishes and manages a connection to an MCP server using Server-Sent Events (SSE),
    allowing for tool discovery and execution of Trivago-related operations.
    
    Attributes:
        session (Optional[ClientSession]): The active client session with the MCP server.
        exit_stack (AsyncExitStack): Context manager for handling async resources.
    """

    MCP_SERVER_URL = "https://mcp.trivago.com/mcp"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(TrivagoMCPClient, self).init_pyxavi(config=config, params=params)

        nest_asyncio.apply()
        transport = StreamableHttpTransport(self.MCP_SERVER_URL)
        self.client = Client(transport=transport)
    
    async def get_tools(self):
        """
        Retrieves and formats available tools from the MCP server.
        
        Fetches the list of available tools from the connected MCP server and converts
        them into OpenAI-compatible function schemas.
        
        Returns:
            list[dict]: A list of tool definitions in Google Gemini function calling format.
            Each tool is represented as a dictionary containing:
                - type: The type of the tool (always "function")
                - function: Dictionary containing name, description, and parameters schema
                
        Raises:
            RuntimeError: If called before establishing a server connection.
        """
        async with self.client:
            # Tool Discovery i.e. query the available tools from the MCP server and print them
            tools = await self.client.list_tools()

            tools = [{
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            } for tool in tools]
            self._xlog.debug(f"Available tools: {json.dumps([t['name'] for t in tools])}")
            
            # return openai_tools_schema
            return tools
    
    async def call_tool(self, tool_name: str, parameters: dict):
        """
        Calls a specified tool on the MCP server with given parameters.
        
        Args:
            tool_name (str): The name of the tool to be called.
            parameters (dict): A dictionary of parameters to pass to the tool.
        """
        async with self.client:
            response = await self.client.call_tool(tool_name, parameters)
            return response