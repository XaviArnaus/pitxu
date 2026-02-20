from datetime import datetime
import time

class Xtime:
    @staticmethod
    def current_time_str(format: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Returns the current time as a formatted string."""
        return datetime.now().strftime(format)
    
    @staticmethod
    def now_milliseconds() -> int:
        """Returns the current time in milliseconds since epoch."""
        # return datetime.now().microsecond // 1000 + int(datetime.now().timestamp() * 1000)
        return int(time.time() * 1000)
    
    @staticmethod
    def now_minus_seconds_milliseconds(seconds: float) -> int:
        """Returns the current time in milliseconds since epoch minus the converted given time in seconds (with decimals)"""
        if seconds is None:
            raise ValueError("Xtime.now_minus_seconds_milliseconds() requires a valid \"seconds\" argument.")
        return Xtime.now_milliseconds() - int(seconds * 1000)