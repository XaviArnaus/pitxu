import time

class SystemTime:

    format = "%H:%M"
    @staticmethod
    def get_current_time() -> str:
        '''
        Gets the current system time

        Returns:
            The current time in HH:MM format
        '''
        return time.strftime(SystemTime.format, time.localtime())