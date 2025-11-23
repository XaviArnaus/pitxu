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
# - The session that generates the tools and performs the chat call need to be under the same context (async with)
#   otherwise it complains with "ClosedResourceError: The connection to the MCP server was closed"
# - This is a problem for the Chat set up, because then we need to set up the chat on every interaction.
#   It seems to produce a problem with chat history, because the chat is re-initialized every time.


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

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(TrivagoMCPAccommodationSearch, self).init_pyxavi(config=config, params=params)

        nest_asyncio.apply()
        transport = StreamableHttpTransport(self.MCP_SERVER_URL)
        self.client = Client(transport=transport, log_handler=self._xlog)
    
    def get_client(self):
        """
        Returns the MCP client.
        """
        return self.client