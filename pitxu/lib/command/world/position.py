from pyxavi import Config, Logger
from pitxu.lib.utils.config_loader import ConfigLoader
from pitxu.lib.utils.api_request import ApiRequest

class WorldPosition:

    URL = f"https://geocoding-api.open-meteo.com/v1/search?name=%s&count=1"

    @staticmethod
    def get_geo_coordinates_from_location(location: str) -> str:
        '''
        Gets the geographical coordinates (latitude and longitude) from a location string.

        Returns:
            The latitude and longitude in JSON format.
        '''
        config: Config = ConfigLoader.load_config_files()
        logger = Logger(config=config, base_path="").get_logger()
        logger.debug(f"Getting geo coordinates for location: {location}")

        url = WorldPosition.URL % location
        return ApiRequest.do(url)