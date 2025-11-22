import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
import nest_asyncio

from google.genai import types

from pyxavi import Dictionary, Config
from pitxu.lib.abstract.pyxavi import PyXavi

# TEST MCP n.4

# {
#   "mcpServers": {
#     "mcp_trivago_search": {
#       "url": "https://mcp.trivago.com/mcp"
#     }
#   }
# }

# Resources:
# - https://gofastmcp.com/integrations/gemini
# - https://ai.google.dev/gemini-api/docs/function-calling?lang=python&example=weather#mcp
# - https://mcp.trivago.com/docs


## Notes about this implementation:
# - It uses fastmcp to connect to the Trivago MCP server
# - The only really needed method is get_client():
#    https://gofastmcp.com/integrations/gemini
# - The example hangs when asking to Gemini, with this stack trace:
#       Traceback (most recent call last):
#   File "<string>", line 1, in <module>
#   File "/Users/xarnaus/Repositories/xavier/pitxu/runner.py", line 59, in run
#     asyncio.run(main.run())
#   File "/Users/xarnaus/.pyenv/versions/3.11.7/lib/python3.11/asyncio/runners.py", line 190, in run
#     return runner.run(main)
#   File "/Users/xarnaus/.pyenv/versions/3.11.7/lib/python3.11/asyncio/runners.py", line 118, in run
#     return self._loop.run_until_complete(task)
#   File "/Users/xarnaus/.pyenv/versions/3.11.7/lib/python3.11/asyncio/base_events.py", line 640, in run_until_complete
#     self.run_forever()
#   File "/Users/xarnaus/.pyenv/versions/3.11.7/lib/python3.11/asyncio/base_events.py", line 607, in run_forever
#     self._run_once()
#   File "/Users/xarnaus/Library/Caches/pypoetry/virtualenvs/pitxu-GVy1ZTK5-py3.11/lib/python3.11/site-packages/nest_asyncio.py", line 133, in _run_once
#     handle._run()
#   File "/Users/xarnaus/.pyenv/versions/3.11.7/lib/python3.11/asyncio/events.py", line 80, in _run
#     self._context.run(self._callback, *self._args)
#   File "/Users/xarnaus/Repositories/xavier/pitxu/pitxu/main.py", line 226, in run
#     answer = await self._chatbot.ask_async(question)
#   File "/Users/xarnaus/Repositories/xavier/pitxu/pitxu/lib/chatbot/gemini_chatbot.py", line 110, in ask_async
#     response = await self._chat.send_message(question)
#                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#   File "/Users/xarnaus/Library/Caches/pypoetry/virtualenvs/pitxu-GVy1ZTK5-py3.11/lib/python3.11/site-packages/google/genai/chats.py", line 416, in send_message
#     response = await self._modules.generate_content(
#                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#   File "/Users/xarnaus/Library/Caches/pypoetry/virtualenvs/pitxu-GVy1ZTK5-py3.11/lib/python3.11/site-packages/google/genai/models.py", line 6820, in generate_content
#     await _extra_utils.parse_config_for_mcp_sessions(config)
#   File "/Users/xarnaus/Library/Caches/pypoetry/virtualenvs/pitxu-GVy1ZTK5-py3.11/lib/python3.11/site-packages/google/genai/_extra_utils.py", line 546, in parse_config_for_mcp_sessions
#     tool, await tool.list_tools()
#           ^^^^^^^^^^^^^^^^^^^^^^^
#   File "/Users/xarnaus/Library/Caches/pypoetry/virtualenvs/pitxu-GVy1ZTK5-py3.11/lib/python3.11/site-packages/mcp/client/session.py", line 494, in list_tools
#     result = await self.send_request(
#              ^^^^^^^^^^^^^^^^^^^^^^^^
#   File "/Users/xarnaus/Library/Caches/pypoetry/virtualenvs/pitxu-GVy1ZTK5-py3.11/lib/python3.11/site-packages/mcp/shared/session.py", line 263, in send_request
#     await self._write_stream.send(SessionMessage(message=JSONRPCMessage(jsonrpc_request), metadata=metadata))
#   File "/Users/xarnaus/Library/Caches/pypoetry/virtualenvs/pitxu-GVy1ZTK5-py3.11/lib/python3.11/site-packages/anyio/streams/memory.py", line 243, in send
#     self.send_nowait(item)
#   File "/Users/xarnaus/Library/Caches/pypoetry/virtualenvs/pitxu-GVy1ZTK5-py3.11/lib/python3.11/site-packages/anyio/streams/memory.py", line 212, in send_nowait
#     raise ClosedResourceError
# anyio.ClosedResourceError


class TrivagoMCPAccommodationSearch(PyXavi):
    """
    A client for interacting with Trivago through the Trivago MCP (Model Context Protocol) server.
    
    This client establishes and manages a connection to an MCP server using Server-Sent Events (SSE),
    allowing for tool discovery and execution of Trivago-related operations.
    
    Attributes:
        session (Optional[ClientSession]): The active client session with the MCP server.
        exit_stack (AsyncExitStack): Context manager for handling async resources.
    """

    MCP_SERVER_URL = "https://mcp.trivago.com/mcp"
    # TOOL_NAME = "trivago-accommodation-search"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(TrivagoMCPAccommodationSearch, self).init_pyxavi(config=config, params=params)

        nest_asyncio.apply()
        transport = StreamableHttpTransport(self.MCP_SERVER_URL)
        self.client = Client(transport=transport)
    
    def get_client(self):
        """
        Returns the MCP client.
        """
        return self.client
    
    # def accommodation_search(self, location: str, check_in: str, check_out: str, guests: int, rooms: int):
    #     """
    #     Performs an accommodation search on Trivago MCP server with the given parameters.
        
    #     Args:
    #         location (str): The location to search accommodations in.
    #         check_in (str): The check-in date in YYYY-MM-DD format.
    #         check_out (str): The check-out date in YYYY-MM-DD format.
    #         guests (int): The number of guests.
    #         rooms (int): The number of rooms.
        
    #     Returns:
    #         dict: The search results returned by the MCP server.
    #     """
    #     parameters = {
    #         "location": location,
    #         "check_in": check_in,
    #         "check_out": check_out,
    #         "guests": guests,
    #         "rooms": rooms
    #     }
    #     return asyncio.run(self.call_tool(self.TOOL_NAME, parameters))
    
    # def get_tools(self):
    #     """
    #     Retrieves and formats available tools from the MCP server.
        
    #     Fetches the list of available tools from the connected MCP server and converts
    #     them into OpenAI-compatible function schemas.
        
    #     Returns:
    #         list[dict]: A list of tool definitions in Google Gemini function calling format.
    #         Each tool is represented as a dictionary containing:
    #             - type: The type of the tool (always "function")
    #             - function: Dictionary containing name, description, and parameters schema
    #     """
    #     # return asyncio.run(self.get_tools_async())
    #     return self.client.session
    
    # async def call_tool(self, tool_name: str, parameters: dict):
    #     """
    #     Calls a specified tool on the MCP server with given parameters.
        
    #     Args:
    #         tool_name (str): The name of the tool to be called.
    #         parameters (dict): A dictionary of parameters to pass to the tool.
    #     """
    #     async with self.client:
    #         await self.get_tools()
    #         response = await self.client.call_tool(tool_name, parameters)
    #         return response
    
    # async def get_tools_async(self):
    #     """
    #     Retrieves and formats available tools from the MCP server.
        
    #     Fetches the list of available tools from the connected MCP server and converts
    #     them into OpenAI-compatible function schemas.
        
    #     Returns:
    #         list[dict]: A list of tool definitions in Google Gemini function calling format.
    #         Each tool is represented as a dictionary containing:
    #             - type: The type of the tool (always "function")
    #             - function: Dictionary containing name, description, and parameters schema
                
    #     Raises:
    #         RuntimeError: If called before establishing a server connection.
    #     """
    #     async with self.client:
    #         # Tool Discovery i.e. query the available tools from the MCP server and print them
    #         tools = await self.client.list_tools()

    #         # tools = [{
    #         #     "name": tool.name,
    #         #     "description": tool.description,
    #         #     "input_schema": tool.inputSchema
    #         # } for tool in tools]

    #         tools = [
    #             types.ToolDict(types.FunctionDeclarationDict(
    #                 name=tool.name,
    #                 description=tool.description,
    #                 parameters=tool.inputSchema
    #             )) for tool in tools
    #         ]
            
    #         # return openai_tools_schema
    #         return tools