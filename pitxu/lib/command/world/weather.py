from pyxavi import Config, Dictionary, dd
from pitxu.lib.utils.api_request import ApiRequest

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.eink import EinkDisplay
from pitxu.lib.objects.point import Point

from datetime import datetime

class WorldWeather(PyXavi, Command):

    # Weather Code meanings:
    # Code	Description
    # 0	        Clear sky
    # 1, 2, 3	    Mainly clear, partly cloudy, and overcast
    # 45, 48	    Fog and depositing rime fog
    # 51, 53, 55	Drizzle: Light, moderate, and dense intensity
    # 56, 57	    Freezing Drizzle: Light and dense intensity
    # 61, 63, 65	Rain: Slight, moderate and heavy intensity
    # 66, 67	    Freezing Rain: Light and heavy intensity
    # 71, 73, 75	Snow fall: Slight, moderate, and heavy intensity
    # 77	        Snow grains
    # 80, 81, 82	Rain showers: Slight, moderate, and violent
    # 85, 86	    Snow showers slight and heavy
    # 95 *	    Thunderstorm: Slight or moderate
    # 96, 99 *	Thunderstorm with slight and heavy hail

    map_code_to_emoji = {
        0: "☀️",
        1: "🌤️",
        2: "🌥️",
        3: "☁️",
        45: "🌫️",
        48: "🌫️",
        51: "🌧️",
        53: "🌧️",
        55: "🌧️",
        56: "🌧️",
        57: "🌧️",
        61: "🌧️",
        63: "🌧️",
        65: "🌧️",
        66: "🌧️",
        67: "🌧️",
        71: "❄️",
        73: "❄️",
        75: "❄️",
        77: "❄️",
        80: "🌦️",
        81: "🌦️",
        82: "🌦️",
        85: "🌨️",
        86: "🌨️",
        95: "⛈️",
        96: "⛈️",
        99: "⛈️",
    }

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
            response = ApiRequest.do(url)
            dd(response)
            return response
        except Exception as e:
            self._xlog.error(f"🛑 Error getting weather forecast for next {days} days at location: {latitude}, {longitude}: {e}")
            return self._xconfig.get("language.general_error." + self._xparams.get("language")) + " " + str(e)
    
    def callback_weather_forecast_for_today(self, main_instance, value: dict) -> None:
        """
        Callback for `get_weather_forecast_for_today` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_weather_forecast_for_today`.

        """
        main_instance._xlog.info(f"The weather forecast for today in the callback is: {value}")

        try:
            # Get the time range that belongs to now
            now = datetime.now().hour
            # Get the values from out time range that belongs to now
            temperature = value.get("hourly", {}).get("temperature_2m", [])[now]
            humidity = value.get("hourly", {}).get("relative_humidity_2m", [])[now]
            pressure = value.get("hourly", {}).get("surface_pressure", [])[now]
            wind_speed = value.get("hourly", {}).get("wind_speed_10m", [])[now]
            wind_direction = value.get("hourly", {}).get("wind_direction_10m", [])[now]
            weather_code = value.get("hourly", {}).get("weathercode", [])[now]
            weather_emoji = self.map_code_to_emoji.get(weather_code, "❓")

            # Create a summary string
            # Format: "☀️ 🌡️ 25°C,💧 60%, 🌬️ 15km/h"
            weather_summary = f"{weather_emoji} {temperature}°C\n💧 {humidity}% | 🌬️ {wind_speed}km/h"

            main_instance._xlog.error(f"☀️ Showing weather forecast for today on eInk: {weather_summary}")
            # main_instance.show_arbitrary_text_centered_on_eink(weather_summary)
            # Be careful. We use some shortcuts to create a canvas,
            # but we should NOT use the Display class directly from here.
            display: EinkDisplay = EinkDisplay(config=self._xconfig, params=self._xparams)
            canvas = display.create_canvas(reset_base_image=True)
            screen_size = Point(self._xconfig.get("display.size.x"), self._xconfig.get("display.size.y"))
            # Apparently, the e-ink display is rotated 90 degrees, so swap coordinates for real GPIO work.
            canvas.text(Point(screen_size.y / 2, screen_size.x / 2).to_image_point(),
                        text = value,
                        font = display.FONT_BIG,
                        fill = display.COLOR_BLACK,
                        anchor = "mm",
                        align = "center")

            # Show the time in the eInk display
            image = display.get_image()
            main_instance.show_image_on_eink(image.tobytes().hex())
        except Exception as e:
            main_instance._xlog.error(f"🛑 Error showing weather forecast for today on eInk: {e}")

    def callback_weather_forecast_for_next_days(self, main_instance, value) -> None:
        """
        Callback for `get_weather_forecast_for_next_days` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_weather_forecast_for_next_days`.

        """
        main_instance._xlog.info(f"The weather forecast for the next days in the callback is: {value}")

        try:

            # New approach, using the existing display instance via main
            main_instance._xlog.error(f"☀️ Showing weather forecast for the next days on eInk: {value}")
            main_instance.show_arbitrary_text_centered_on_eink(value)
        except Exception as e:
            main_instance._xlog.error(f"🛑 Error showing weather forecast for the next days on eInk: {e}")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_weather_forecast_for_today, self.get_weather_forecast_for_next_days]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_weather_forecast_for_today":
            return self.callback_weather_forecast_for_today
        elif function_name == "get_weather_forecast_for_next_days":
            return self.callback_weather_forecast_for_next_days
        return self.default_empty_callback