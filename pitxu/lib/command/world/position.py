from pyxavi import Config, Logger
from pitxu.lib.utils.config_loader import ConfigLoader
from pitxu.lib.utils.api_request import ApiRequest

class WorldPosition:

    URL = f"https://geocoding-api.open-meteo.com/v1/search?name=%s&count=1"

    @staticmethod
    def get_latitude_and_longitude_from_location(location: str) -> str:
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
    
    @staticmethod
    def get_latitude_and_longitude_from_current_location() -> str:
        '''
        Gets the geographical coordinates (latitude and longitude) from the current location of the device.

        Returns:
            The latitude and longitude in JSON format.
        '''
        config: Config = ConfigLoader.load_config_files()
        logger = Logger(config=config, base_path="").get_logger()
        logger.debug("Getting geo coordinates for current location")

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

            logger.debug(f"Geo coordinates for current location: {latitude}, {longitude} ({city}, {country})")

            return {
                "latitude": latitude,
                "longitude": longitude,
                "city": city,
                "country": country
            }
        except Exception as e:
            logger.error(f"Error getting geo coordinates for current location: {e}")
            return f"Error getting geo coordinates for current location: {e}"