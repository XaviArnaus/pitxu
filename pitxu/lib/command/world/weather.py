from pyxavi import Config, Dictionary
from pitxu.lib.utils.api_request import ApiRequest

from pitxu.lib.abstract.pyxavi import PyXavi

class WorldWeather(PyXavi):

    URL = f"https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&hourly=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m,weathercode&daily=sunrise,sunset&forecast_days=%s"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

    def get_weather_forecast_for_today(self, latitude: float, longitude: float) -> str:
        '''
        Gets the weather forecast for a specific location.

        Returns:
            The weather forecast information in JSON format.
        '''
        try:
            self._xlog.debug(f"Getting weather forecast for today at location: {latitude}, {longitude}")

            url = WorldWeather.URL % (str(latitude), str(longitude), str(1))
            return ApiRequest.do(url)
        except Exception as e:
            self._xlog.error(f"🛑 Error getting weather forecast for today at location: {latitude}, {longitude}: {e}")
            return self._xconfig.get("language.general_error." + self._xparams.get("language")) + " " + str(e)
    
    def get_weather_forecast_for_next_days(self, latitude: float, longitude: float, days: int) -> str:
        '''
        Gets the weather forecast for a specific location.

        Returns:
            The weather forecast information in JSON format.
        '''
        try:
            # days = 1 means actually today, so we need to add 1 to get the next days
            days += 1
            self._xlog.debug(f"Getting weather forecast for next {days} days at location: {latitude}, {longitude}")

            url = WorldWeather.URL % (str(latitude), str(longitude), str(days))
            return ApiRequest.do(url)
        except Exception as e:
            self._xlog.error(f"🛑 Error getting weather forecast for next {days} days at location: {latitude}, {longitude}: {e}")
            return self._xconfig.get("language.general_error." + self._xparams.get("language")) + " " + str(e)