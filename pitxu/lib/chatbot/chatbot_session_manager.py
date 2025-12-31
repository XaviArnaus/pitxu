from pyxavi import Config, Logger, Dictionary, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.command import SystemDate, SystemTime, SystemPowerManagement, SystemVolume, SystemLanguage,\
                                WorldPosition, WorldWeather, WorldWikipedia,\
                                GoogleMaps, GoogleSearch,\
                                TrivagoMCPAccommodationSearch,\
                                StatefulReminders,\
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
            "world_wikipedia": WorldWikipedia(config=self._xconfig, params=self._xparams),
            "world_position": WorldPosition(config=self._xconfig, params=self._xparams),
            "world_weather": WorldWeather(config=self._xconfig, params=self._xparams),
            "system_time": SystemTime(config=self._xconfig, params=self._xparams),
            "system_date": SystemDate(config=self._xconfig, params=self._xparams),
            "system_language": SystemLanguage(config=self._xconfig, params=self._xparams),
            "power_management": SystemPowerManagement(config=self._xconfig, params=self._xparams),
            "volume": SystemVolume(config=self._xconfig, params=self._xparams),
            "reminders": StatefulReminders(config=self._xconfig, params=self._xparams),
            "mail": ServiceMail(config=self._xconfig, params=self._xparams),
            "print": ServicePrint(config=self._xconfig, params=self._xparams),
        }
        
        self._xlog.debug("ChatbotSessionManager: Registering MCP clients.")
        if self.ENABLE_TRIVAGO_MCP:
            trivago_mcp_accommodation_search = TrivagoMCPAccommodationSearch(config=self._xconfig, params=self._xparams)
            self.mcp_clients["trivago"] = trivago_mcp_accommodation_search.get_client()
    
    async def initialize_tooling(self):

        if self.ENABLE_TOOLS is False:
            self._xlog.warning("ChatbotSessionManager: Tooling is disabled.")
            self.tools = []
            return

        self._xlog.debug("ChatbotSessionManager: Setting up tools.")
        # The tools defined in self.tools and self.mcp_tools are used to define the functions available to the LLM as tools
        # self.tools = [
        #         # Grounding workaround so it can use Google Search
        #         self.clients["google_search"].get_google_search_response_to_a_prompt,
        #         # Grounding workaround so it can use Google Maps
        #         self.clients["google_maps"].get_google_maps_response_to_a_prompt,
        #         # # Custom Commands
        #         self.clients["system_date"].get_current_system_calendar_date_as_year_month_date,
        #         self.clients["system_time"].get_current_system_clock_time_as_hours_and_minutes,
        #         self.clients["power_management"].get_battery_level,
        #         self.clients["power_management"].is_power_cable_connected,
        #         self.clients["power_management"].shutdown_local_machine,
        #         self.clients["power_management"].reboot_local_machine,
        #         self.clients["volume"].get_volume_level,
        #         self.clients["volume"].get_mute_status,
        #         self.clients["volume"].set_volume_level,
        #         self.clients["volume"].set_mute_status,
        #         self.clients["world_position"].get_latitude_and_longitude_from_location,
        #         self.clients["world_position"].get_latitude_and_longitude_from_current_location,
        #         self.clients["world_position"].get_latitude_and_longitude_from_address, 
        #         self.clients["world_weather"].get_weather_forecast_for_today,
        #         self.clients["world_weather"].get_weather_forecast_for_next_days,
        #         self.clients["world_wikipedia"].get_summary_from_wikipedia_by_term,
        #         self.clients["reminders"].create_reminder,
        #         self.clients["reminders"].delete_reminder,
        #         self.clients["reminders"].get_reminders_for_date,
        #         self.clients["reminders"].update_reminder,
        #         self.clients["reminders"].move_reminder,
        #     ]
        self.tools = []
        for client_name, client in self.clients.items():
            if isinstance(client, Command):
                tools_from_client = client.get_tool_definition()
                self._xlog.debug(f"ChatbotSessionManager: Adding tools from client [{client_name}]: {len(tools_from_client)}")
                self.tools.extend(tools_from_client)
        if self.ENABLE_TRIVAGO_MCP:
            self.tools.append(
                # To embed a MCP tool, we need to pass the session. As simple as that.
                # But then we can't really change the output, it can be too big and too boring.
                self.mcp_clients["trivago"].session
            )

    async def __aenter__(self):
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

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._xlog.debug("ChatbotSessionManager: Disconnecting from all MCP servers.")
        if self.ENABLE_TOOLS and self.ENABLE_TRIVAGO_MCP:
            self.session_handlers["trivago"] = await self.mcp_clients["trivago"]._disconnect()

        self._xlog.debug("ChatbotSessionManager: Clearing all session handlers.")
        for key in list(self.session_handlers.keys()):
            del self.session_handlers[key]
    
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