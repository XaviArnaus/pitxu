from datetime import datetime
import time

class Xtime:

    FORMAT: str = "%Y-%m-%d %H:%M:%S"
    FORMAT_WITH_MILLISECONDS: str = "%Y-%m-%d %H:%M:%S.%f"

    @staticmethod
    def current_time_str(format: str = None) -> str:
        """Returns the current time as a formatted string."""
        if format is None:
            format = Xtime.FORMAT
        return datetime.now().strftime(format)
    
    @staticmethod
    def now() -> datetime:
        """
        Returns the current datetime object
        Just a shortcut.
        """
        return datetime.now()
    
    @staticmethod
    def now_str(format: str = None) -> str:
        """
        Returns the current time as a formatted string.
        Just a shortcut for miliseconds.
        """
        if format is None:
            format = Xtime.FORMAT_WITH_MILLISECONDS
        return Xtime.now().strftime(format)
    
    @staticmethod
    def now_key(format: str = None) -> str:
        from slugify import slugify
        """
        Returns the current time as a formatted string.
        Just a shortcut for miliseconds.
        """
        if format is None:
            format = Xtime.FORMAT_WITH_MILLISECONDS
        return slugify(Xtime.now().strftime(format), replacements=[[" ", "_"], [":", "-"], [".", "-"]])
    
    @staticmethod
    def now_as_milliseconds() -> int:
        """Returns the current time in milliseconds since epoch."""
        # return datetime.now().microsecond // 1000 + int(datetime.now().timestamp() * 1000)
        return int(time.time() * 1000)
    
    @staticmethod
    def now_minus_seconds_as_milliseconds(seconds: float) -> int:
        """Returns the current time in milliseconds since epoch minus the converted given time in seconds (with decimals)"""
        if seconds is None:
            raise ValueError("Xtime.now_minus_seconds_as_milliseconds() requires a valid \"seconds\" argument.")
        return Xtime.now_as_milliseconds() - int(seconds * 1000)