from pyxavi import Config, Logger, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.command import SystemDate, SystemTime, SystemPowerManagement,\
                                WorldPosition, WorldWeather, WorldWikipedia,\
                                GoogleMaps, GoogleSearch,\
                                TrivagoMCPAccommodationSearch

from functools import partial

class ChatbotSessionManager(PyXavi):

    mcp_clients = {}
    clients = {}

    _safe_close_callback = None

    session_handlers = {}
    tools = []
    
    def __init__(self, config: Config, params: Dictionary, safe_close_callback = None):
        super(ChatbotSessionManager, self).init_pyxavi(config=config, params=params)
        self._safe_close_callback = safe_close_callback

    async def initialize(self):

        self._xlog.debug("ChatbotSessionManager: Initializing instantiable tooling.")
        self.clients = {
            "google_maps": GoogleMaps(config=self._xconfig, params=self._xparams),
            "google_search": GoogleSearch(config=self._xconfig, params=self._xparams),
            "world_position": WorldPosition(config=self._xconfig, params=self._xparams),
            "world_weather": WorldWeather(config=self._xconfig, params=self._xparams)
        }
        

        self._xlog.debug("ChatbotSessionManager: Registering MCP clients.")
        trivago_mcp_accommodation_search = TrivagoMCPAccommodationSearch(config=self._xconfig, params=self._xparams)
        self.mcp_clients = {
            "trivago": trivago_mcp_accommodation_search.get_client()
        }
    
    async def initialize_tooling(self):

        self._xlog.debug("ChatbotSessionManager: Setting up tools.")
        self.tools = [
                # Grounding workaround so it can use Google Search
                self.clients["google_search"].get_google_search_response_to_a_prompt,
                # Grounding workaround so it can use Google Maps
                self.clients["google_maps"].get_google_maps_response_to_a_prompt,
                # # Custom Commands
                SystemDate.get_current_date,
                SystemTime.get_current_time,
                SystemPowerManagement.get_battery_level,
                SystemPowerManagement.is_power_cable_connected,
                partial(SystemPowerManagement.shutdown_local_machine, self._safe_close_callback),
                partial(SystemPowerManagement.reboot_local_machine, self._safe_close_callback),
                self.clients["world_position"].get_latitude_and_longitude_from_location,
                self.clients["world_position"].get_latitude_and_longitude_from_current_location,
                self.clients["world_position"].get_latitude_and_longitude_from_address, 
                self.clients["world_weather"].get_weather_forecast_for_today,
                self.clients["world_weather"].get_weather_forecast_for_next_days,
                WorldWikipedia.get_summary_from_wikipedia_by_term,
                # To embed a MCP tool, we need to pass the session. As simple as that.
                # But then we can't really change the output, it can be too big and too boring.
                self.mcp_clients["trivago"].session
            ]

    async def __aenter__(self):
        self._xlog.debug("ChatbotSessionManager: Initializing.")
        await self.initialize()

        self._xlog.debug("ChatbotSessionManager: Connecting to all MCP servers.")
        self.session_handlers["trivago"] = await self.mcp_clients["trivago"]._connect()

        self._xlog.debug("ChatbotSessionManager: Initializing all tooling.")
        await self.initialize_tooling()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._xlog.debug("ChatbotSessionManager: Disconnecting from all MCP servers.")
        self.session_handlers["trivago"] = await self.mcp_clients["trivago"]._disconnect()

        self._xlog.debug("ChatbotSessionManager: Clearing all session handlers.")
        for key in list(self.session_handlers.keys()):
            del self.session_handlers[key]