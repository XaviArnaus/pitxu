from pyxavi import Config, Logger, Dictionary, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.command import SystemDate, SystemTime, SystemNetwork, SystemPowerManagement, SystemVolume, SystemLanguage, \
                                SystemJsonMetrics, SystemConversationFlow,\
                                WorldPosition, WorldWeather, WorldWikipedia, WorldWget, WorldGithub,\
                                GoogleMaps, GoogleSearch, GoogleCode,\
                                TrivagoMCPAccommodationSearch,\
                                StatefulReminders, StatefulLists, StatefulMemory,\
                                ServiceMail, ServicePrint

class ChatbotSessionManager(PyXavi):

    ENABLE_TOOLS = True
    ENABLE_TRIVAGO_MCP = False

    mcp_clients = {}
    clients = {}

    session_handlers = {}
    tools = []
    
    def __init__(self, config: Config, params: Dictionary):
        super(ChatbotSessionManager, self).init_pyxavi(config=config, params=params)

    async def initialize(self):

        if self.ENABLE_TOOLS is False:
            self._xlog.warning("ChatbotSessionManager: Tooling is disabled.")
            return

        self._xlog.debug("ChatbotSessionManager: Initializing instantiable tooling.")
        # The clients defined in self.clients and self.mcp_clients are instances to the classes that provide the tools
        #
        # They are used to:
        # 1) define the functions available to the LLM as tools
        # 2) map the function names to their related callbacks after the LLM calls them and get back to us.
        #
        # Therefore, ALL TOOLS MUST BE DEFINED HERE AS INSTANCES (no static method calling anymore in the tools list) 
        self.clients = {
            "google_maps": GoogleMaps(config=self._xconfig, params=self._xparams),
            "google_search": GoogleSearch(config=self._xconfig, params=self._xparams),
            "google_code": GoogleCode(config=self._xconfig, params=self._xparams),
            "world_wikipedia": WorldWikipedia(config=self._xconfig, params=self._xparams),
            "world_position": WorldPosition(config=self._xconfig, params=self._xparams),
            "world_weather": WorldWeather(config=self._xconfig, params=self._xparams),
            "system_time": SystemTime(config=self._xconfig, params=self._xparams),
            "system_date": SystemDate(config=self._xconfig, params=self._xparams),
            "system_language": SystemLanguage(config=self._xconfig, params=self._xparams),
            "json_metrics": SystemJsonMetrics(config=self._xconfig, params=self._xparams),
            "power_management": SystemPowerManagement(config=self._xconfig, params=self._xparams),
            "volume": SystemVolume(config=self._xconfig, params=self._xparams),
            "reminders": StatefulReminders(config=self._xconfig, params=self._xparams),
            "lists": StatefulLists(config=self._xconfig, params=self._xparams),
            "memory": StatefulMemory(config=self._xconfig, params=self._xparams),
            "mail": ServiceMail(config=self._xconfig, params=self._xparams),
            "print": ServicePrint(config=self._xconfig, params=self._xparams),
            "system_network": SystemNetwork(config=self._xconfig, params=self._xparams),
            "system_conversation_flow": SystemConversationFlow(config=self._xconfig, params=self._xparams),
            "world_wget": WorldWget(config=self._xconfig, params=self._xparams),
            "world_github": WorldGithub(config=self._xconfig, params=self._xparams),
        }
        
        self._xlog.debug("ChatbotSessionManager: Registering MCP clients.")
        if self.ENABLE_TRIVAGO_MCP:
            trivago_mcp_accommodation_search = TrivagoMCPAccommodationSearch(config=self._xconfig, params=self._xparams)
            self.mcp_clients["trivago"] = trivago_mcp_accommodation_search.get_client()
    
    def get_clients(self) -> dict[str, Command]:
        return self.clients
    
    async def initialize_tooling(self):

        if self.ENABLE_TOOLS is False:
            self._xlog.warning("ChatbotSessionManager: Tooling is disabled.")
            self.tools = []
            return

        self._xlog.debug("ChatbotSessionManager: Setting up tools.")
        self.tools = []
        logging_tools_summary = []
        for client_name, client in self.clients.items():
            if isinstance(client, Command):
                tools_from_client = client.get_tool_definition()
                logging_tools_summary.append((client_name, len(tools_from_client)))
                self.tools.extend(tools_from_client)
        self.log_summary("Tools Initialization", logging_tools_summary)
        if self.ENABLE_TRIVAGO_MCP:
            self.tools.append(
                # To embed a MCP tool, we need to pass the session. As simple as that.
                # But then we can't really change the output, it can be too big and too boring.
                self.mcp_clients["trivago"].session
            )

    async def __aenter__(self):
        await self.start_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop_session()
    
    async def start_session(self):
        try:
            self._xlog.debug("ChatbotSessionManager: Initializing.")
            await self.initialize()

            self._xlog.debug("ChatbotSessionManager: Connecting to all MCP servers.")
            if self.ENABLE_TRIVAGO_MCP:
                self.session_handlers["trivago"] = await self.mcp_clients["trivago"]._connect()

            self._xlog.debug("ChatbotSessionManager: Initializing all tooling.")
            await self.initialize_tooling()
        except Exception as e:
            self._xlog.error(f"🛑 ChatbotSessionManager: Error during initialization: {e}")
    
    async def stop_session(self):
        self._xlog.debug("ChatbotSessionManager: Disconnecting from all MCP servers.")
        if self.ENABLE_TOOLS and self.ENABLE_TRIVAGO_MCP:
            self.session_handlers["trivago"] = await self.mcp_clients["trivago"]._disconnect()

        self._xlog.debug("ChatbotSessionManager: Clearing all session handlers.")
        for key in list(self.session_handlers.keys()):
            del self.session_handlers[key]
        
        self._xlog.debug("ChatbotSessionManager: Closing ChatbotSessionManager itself.")
        await self.close()
        
        self._xlog.debug("ChatbotSessionManager: Closed.")
    
    def get_client_callbacks_by_function_name(self) -> dict[str, callable]:
        clients_by_function_name = {}
        clients_stacks = [self.clients, self.mcp_clients]
        # Iterate over all clients and map function names to clients
        for clients in clients_stacks:
            for name, client in dict(clients).items():
                # Only grab the ones that have the Command as base class
                if isinstance(client, Command):
                    # They are already instantiated clients
                    for function_name in client.get_function_names():
                        # Get the related callable for the given function name
                        clients_by_function_name[function_name] = client.get_callback_by_given_function_name(function_name)
        return clients_by_function_name
    
    def close(self):
        self._xlog.debug("ChatbotSessionManager: Closing clients.")
        for client_name, client in self.clients.items():
            if hasattr(client, "close") and callable(getattr(client, "close")):
                self._xlog.debug(f"ChatbotSessionManager: Closing client [{client_name}].")
                try:
                    client.close()
                except Exception as e:
                    self._xlog.error(f"🛑 ChatbotSessionManager: Error closing client [{client_name}]: {e}")