from pyxavi import Config, Dictionary
from pitxu.lib.utils.api_request import ApiRequest

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.shortcuts.status import Status

class WorldPosition(PyXavi, Command):

    status_shortcuts: Status = None

    URL = f"https://geocoding-api.open-meteo.com/v1/search?name=%s&count=1"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

        if self._xparams.key_exists("status_shortcuts"):
            self.status_shortcuts = self._xparams.get("status_shortcuts")
        else:
            raise ValueError("Missing 'status_shortcuts' parameter in WorldPosition initialization.")

    def get_latitude_and_longitude_from_location(self, location: str) -> dict | bool:
        '''
        Get the geographical coordinates (latitude and longitude) from the given location string.

        Args:
            location (str): The location string to get the coordinates for.

        Returns:
            dict | bool: The latitude and longitude in JSON format, or False if not found.
        '''
        retries = -1
        while retries < 1:
            retries += 1
            self._xlog.debug(f"Getting geo coordinates for location: {location}. Try #{retries}")
            self.status_shortcuts.add_new_status_line(f"🔧 Tool: Getting geo coordinates for location: [{location}]. Try #{retries}")

            url = WorldPosition.URL % location
            result = ApiRequest.do(url)
            results = result.get("results", [])
            if len(results) == 0:
                self._xlog.warning(f"No results found for location: {location}. Retrying with some extra cleaning.")
                # Try to clean the location a bit and retry
                location_cleaned = location.split(",")[0]  # Remove anything after a comma
                location_cleaned = location_cleaned.replace(" near ", " ")  # Remove ' near '
                location_cleaned = location_cleaned.replace(" close to ", " ")  # Remove ' close to '
                location_cleaned = location_cleaned.strip()
                location = location_cleaned
                continue
            else:
                return results
        
        if len(results) == 0:
            self._xlog.error(f"🛑 Error getting geo coordinates for location {location}: No results found after retries.")
            return False


    def get_latitude_and_longitude_from_current_location(self) -> dict | str:
        '''
        Get the geographical coordinates (latitude and longitude) from the current location of the local system.

        Returns:
            dict | str: The latitude and longitude in JSON format, or an error message.
        '''
        self._xlog.debug("Getting geo coordinates for current location of the local system.")
        self.status_shortcuts.add_new_status_line(f"🔧 Tool: Getting geo coordinates for current location of the local system.")

        try:
            # Results are very bad (I'm not in Berlin...)
            # g = geocoder.ip('me')
            # latitude = g.latlng[0]
            # longitude = g.latlng[1]
            # city = g.city
            # country = g.country

            # Results are better (Ekhradt...) but still not good.
            # https://docs.ipdata.co/docs/all-response-fields
            # Be careful, this lib is messing up with my logger: the main process disappears from the logs.
            from ipdata import IPData
            ipdata = IPData(api_key='a33544cf4265b29261ffc0e97d6e78b6689cc76d9a7b752dd8038deb')
            response = ipdata.lookup()

            latitude = response['latitude']
            longitude = response['longitude']
            city = response['city']
            country = response['country_name']

            self._xlog.debug(f"Geo coordinates for current location: {latitude}, {longitude} ({city}, {country})")

            return {
                "latitude": latitude,
                "longitude": longitude,
                "city": city,
                "country": country
            }
        except Exception as e:
            self._xlog.error(f"🛑 Error getting geo coordinates for current location: {e}")
            return f"Error getting geo coordinates for current location: {e}"

    def get_latitude_and_longitude_from_address(self, address: str) -> dict | str:
        '''
        Get the geographical coordinates (latitude and longitude) from a given address.

        Args:
            address (str): The address to get the coordinates for.

        Returns:
            dict | str: The latitude and longitude in JSON format, or an error message.
        '''
        self.status_shortcuts.add_new_status_line(f"🔧 Tool: Getting geo coordinates for address: [{address}]")
        self._xlog.debug(f"Getting geo coordinates for address: [{address}]")

        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="pitxu")
            location = geolocator.geocode(
                address,
                exactly_one=True,
                language=self._xparams.get("language", "en")
            )

            latitude = location.latitude
            longitude = location.longitude

            self._xlog.debug(f"Geo coordinates for address {address}: {latitude}, {longitude}")

            return {
                "latitude": latitude,
                "longitude": longitude
            }
        except Exception as e:
            self._xlog.error(f"🛑 Error getting geo coordinates for address {address}: {e}")
            return f"Error getting geo coordinates for address {address}: {e}"
    
    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_latitude_and_longitude_from_location,
                self.get_latitude_and_longitude_from_current_location,
                self.get_latitude_and_longitude_from_address]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        return self.default_empty_callback