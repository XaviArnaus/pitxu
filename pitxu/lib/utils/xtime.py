from datetime import datetime
import time

class Xtime:

    FORMAT: str = "%Y-%m-%d %H:%M:%S"
    FORMAT_WITH_MILLISECONDS: str = "%Y-%m-%d %H:%M:%S.%f"
    FORMAT_WITHOUT_SECONDS: str = "%Y-%m-%dT%H:%M:%S"
    FORMAT_ISO: str = "%Y-%m-%dT%H:%M:%S"

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
        """
        Returns the current time as a formatted string.
        Just a shortcut for miliseconds.
        """
        from slugify import slugify
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
    
    @staticmethod
    def slugify_datetime(dt: datetime, format: str = None) -> str:
        """
        Converts a datetime object to a slugified string based on the given format.
        If no format is provided, it defaults to FORMAT_WITH_MILLISECONDS.
        """
        from slugify import slugify
        if format is None:
            format = Xtime.FORMAT_WITH_MILLISECONDS
        return slugify(dt.strftime(format), replacements=[[" ", "_"], [":", "-"], [".", "-"]])

    @staticmethod
    def str_to_datetime(date_str: str, format: str = None) -> datetime:
        """
        Converts a date string to a datetime object based on the given format.
        If no format is provided, it defaults to FORMAT.
        """
        if format is None:
            format = Xtime.FORMAT
        return datetime.strptime(date_str, format)
    
    @staticmethod
    def get_seconds_since(date_str: str, format: str = None) -> float:
        """
        Returns the number of seconds that have passed since the given date string.
        The date string is parsed based on the given format, or defaults to FORMAT.
        """
        if format is None:
            format = Xtime.FORMAT
        try:
            past_time = Xtime.str_to_datetime(date_str, format)
            now = Xtime.now()
            elapsed_time = now - past_time
            return elapsed_time.total_seconds()
        except Exception as e:
            print(f"⚙️  Error calculating seconds since {date_str}: {e}")
            return None
    
    @staticmethod
    def get_human_format_from_seconds(seconds: float) -> str:
        """
        Converts a number of seconds into a human-readable format (e.g., "2 minutes, 30 seconds").
        """
        if seconds is None:
            return "N/A"
        try:
            minutes, sec = divmod(int(seconds), 60)
            hours, minutes = divmod(minutes, 60)
            parts = []
            if hours > 0:
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes > 0:
                parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if sec > 0 or not parts:
                parts.append(f"{sec} second{'s' if sec != 1 else ''}")
            return ", ".join(parts)
        except Exception as e:
            print(f"⚙️  Error converting seconds to human format: {e}")
            return "N/A" 