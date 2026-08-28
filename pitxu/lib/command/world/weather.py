from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.utils.api_request import ApiRequest

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.interaction.shortcuts.status import Status

import logging

from datetime import datetime

class WorldWeather(PyXavi, Command):

    status_shortcuts: Status = None

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

        if self._xparams.key_exists("status_shortcuts"):
            self.status_shortcuts = self._xparams.get("status_shortcuts")
        else:
            raise ValueError("Missing 'status_shortcuts' parameter in WorldWeather initialization.")

    def get_weather_forecast_for_today(self, latitude: float, longitude: float, requested_hour: int = None) -> dict:
        '''
        Get the weather forecast for the current date (per hour) in the given latitude and longitude.

        To provide the information to the user, select the corresponding hour from the returned data.
        If no specific hour is requested, use the current hour of the day.
        The current hour can be found in the "current_hour" field of the returned JSON.
        Therefore, if the current hour is 14 (2 PM), select the 14th index from every array.

        Args:
            latitude (float): The latitude of the location.
            longitude (float): The longitude of the location.
            requested_hour (int, optional): The specific hour to retrieve the forecast for. If not provided, the current hour will be used.

        Returns:
            dict: The weather forecast information in JSON format.
        '''
        try:
            self._xlog.debug(f"Getting weather forecast for today at [{str(requested_hour)}] at location: {latitude}, {longitude}")
            self.status_shortcuts.add_new_status_line(f"🔧 Weather: forecast for today at [{str(requested_hour)}] location: [{round(latitude, 4)}, {round(longitude, 4)}]")

            url = WorldWeather.URL % (str(latitude), str(longitude), str(1))
            response: dict = ApiRequest.do(url)
            now = datetime.now().hour
            temperature = response.get("hourly", {}).get("temperature_2m", [])
            humidity = response.get("hourly", {}).get("relative_humidity_2m", [])
            pressure = response.get("hourly", {}).get("surface_pressure", [])
            wind_speed = response.get("hourly", {}).get("wind_speed_10m", [])
            wind_direction = response.get("hourly", {}).get("wind_direction_10m", [])
            weather_code = response.get("hourly", {}).get("weathercode", [])
            sunrise = response.get("daily", {}).get("sunrise", [])[0]
            sunset = response.get("daily", {}).get("sunset", [])[0]
            return {
                "current_hour": now,
                "temperature": temperature,
                "humidity": humidity,
                "pressure": pressure,
                "wind_speed": wind_speed,
                "wind_direction": wind_direction,
                "weather_code": weather_code,
                "sunrise": sunrise,
                "sunset": sunset
            }
        except Exception as e:
            self._xlog.error(f"🛑 Error getting weather forecast for today at location: {latitude}, {longitude}: {e}")
            return self._xconfig.get("language.general_error." + self._xparams.get("language")) + " " + str(e)
    
    def get_weather_forecast_for_next_days(self, latitude: float, longitude: float, days: int) -> str:
        '''
        Get the weather forecast for the next given days from the current date, in the given latitude and longitude.

        Args:
            latitude (float): The latitude of the location.
            longitude (float): The longitude of the location.
            days (int): The number of days from the current date to get the forecast for.

        Returns:
            The weather forecast information in JSON format.
        '''
        try:
            # days = 1 means actually today, so we need to add 1 to get the next days
            days += 1
            self._xlog.debug(f"Getting weather forecast for next {days} days at location: {latitude}, {longitude}")
            self.status_shortcuts.add_new_status_line(f"🔧 Weather: forecast for next {days} days at location: [{round(latitude, 4)}, {round(longitude, 4)}]")

            url = WorldWeather.URL % (str(latitude), str(longitude), str(days))
            response = ApiRequest.do(url)
            return response
        except Exception as e:
            self._xlog.error(f"🛑 Error getting weather forecast for next {days} days at location: {latitude}, {longitude}: {e}")
            return self._xconfig.get("language.general_error." + self._xparams.get("language")) + " " + str(e)
    
    def callback_weather_forecast_for_today(self, log: logging, interaction: Interaction, value: dict, args: dict = None) -> None:
        """
        Callback for `get_weather_forecast_for_today` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_weather_forecast_for_today`.

        """
        log.info(f"The weather forecast for today in the callback is: {value}")
        requested_hour = args.get("requested_hour", None) if args else None
        if requested_hour is not None:
            log.debug(f"The requested hour for the weather forecast in the callback is: {requested_hour}")

        try:
            if requested_hour is None:
                requested_hour = value.get("current_hour", datetime.now().hour)
            # Get the values from out time range that belongs to now
            temperature = value.get("temperature", [])[requested_hour]
            humidity = value.get("humidity", [])[requested_hour]
            # pressure = value.get("pressure", [])[requested_hour]
            wind_speed = value.get("wind_speed", [])[requested_hour]
            # wind_direction = value.get("wind_direction", [])[requested_hour]
            weather_code = value.get("weather_code", [])[requested_hour]
            weather_emoji = self.map_code_to_emoji.get(weather_code, "❓")

            # Create a summary string
            # Format: "☀️ 🌡️ 25°C,💧 60%, 🌬️ 15km/h"
            weather_header = f"{weather_emoji} {temperature}°C"
            weather_other = f"💧 {humidity}% | 💨 {wind_speed}km/h"

            log.debug(f"☀️ Showing weather forecast for today on eInk: {weather_header} {weather_other}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                header=weather_header,
                font_header_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE,
                text=weather_other,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_MEDIUM)
        except Exception as e:
            log.error(f"🛑 Error showing weather forecast for today on eInk: {e}")
            log.error(full_stack())

    # def callback_weather_forecast_for_next_days(self, main_instance, value) -> None:
    #     """
    #     Callback for `get_weather_forecast_for_next_days` that gets called AFTER chatbot from `main`.

    #     Args:
    #         main_instance: The `main` application instance.
    #         value: The value returned from the Chatbot AFTER it ran `get_weather_forecast_for_next_days`.

    #     """
    #     main_instance._xlog.info(f"The weather forecast for the next days in the callback is: {value}")

    #     try:

    #         # New approach, using the existing display instance via main
    #         main_instance._xlog.error(f"☀️ Showing weather forecast for the next days on eInk: {value}")
    #         main_instance.show_arbitrary_text_on_foreground(
    #             header=weather_header,
    #             font_header_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE,
    #             text=weather_other,
    #             font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
    #     except Exception as e:
    #         main_instance._xlog.error(f"🛑 Error showing weather forecast for the next days on eInk: {e}")

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
        # elif function_name == "get_weather_forecast_for_next_days":
        #     return self.callback_weather_forecast_for_next_days
        return self.default_empty_callback