import time

class SystemDate:

    format = "%Y-%m-%d"
    @staticmethod
    def get_current_date() -> str:
        '''
        Gets the current system date
        
        Returns:
            The current date in YYYY-MM-DD format
        '''
        return time.strftime(SystemDate.format, time.localtime())