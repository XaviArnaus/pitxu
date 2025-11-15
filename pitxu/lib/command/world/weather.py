from pyxavi import Config, Logger
from pitxu.lib.utils.config_loader import ConfigLoader
from pitxu.lib.utils.api_request import ApiRequest

class WorldWeather:

    URL = f"https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&hourly=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m&forecast_days=1"

    @staticmethod
    def get_weather_forecast(latitude: float, longitude: float) -> str:
        '''
        Gets the weather forecast for a specific location.

        Returns:
            The weather forecast information in JSON format.
        '''
        config: Config = ConfigLoader.load_config_files()
        logger = Logger(config=config, base_path="").get_logger()
        logger.debug(f"Getting weather forecast for location: {latitude}, {longitude}")

        url = WorldWeather.URL % (str(latitude), str(longitude))
        return ApiRequest.do(url)