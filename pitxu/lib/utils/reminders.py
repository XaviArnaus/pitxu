
from pyxavi import Storage, Config, Dictionary, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command

from datetime import datetime


class Reminders(PyXavi, Command):

    REMINDER_FILENAME = "reminders.yaml"

    FORMAT_DATE = "%Y-%m-%d"  # E.g., 2023-12-25
    FORMAT_TIME = "%H:%M"     # E.g., 14:30

    state: Storage = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Reminders, self).init_pyxavi(config=config, params=params)

        self.state = self._state = Storage(filename=self._xconfig.get("storage.path") + self.REMINDER_FILENAME)
        self.delete_past_reminders()

    def create_reminder(self, date: str, time: str, reminder_text: str) -> bool:
        '''
        Creates a reminder for a specific date.
        
        Args:
            date: The date for the reminder in Year-Month-Day format.
            time: The time for the reminder in HH:MM format.
            reminder_text: The text of the reminder.
        
        Returns:
            A boolean indicating success or failure.
        '''
        self._xlog.info(f"📝 Creating a reminder for [{date}] at [{time}]: {reminder_text}")

        # First check if there are existing reminders for that key
        reminder_key = f"{date}.{time}"
        if self.state.key_exists(reminder_key):
            self._xlog.info(f"📝 Reminder already exists for [{date}] at [{time}]")
            return False

        self.state.set(reminder_key, reminder_text, slugify_param_name=True)
        self.state.write_file()
        self._xlog.info(f"📝 Reminder set for [{date}] at [{time}]: {reminder_text}")

        return True
        
    def get_reminders_for_date(self, date: str) -> list[dict[str, str]]:
        '''
        Retrieves all reminders for a specific date.
        
        Args:
            date: The date to retrieve reminders for in Year-Month-Day format.
        
        Returns:
            A list of reminders for the specified date in a JSON format
        '''

        self._xlog.info(f"📝 Retrieving reminders for [{date}]")
        self.state.read_file()
        reminders = []
        stored_reminders = self.state.get(date, {}, slugify_param_name=True)
        for time, reminder_text in stored_reminders.items():
            reminders.append({
                "time": self._unslugify_time(time),
                "text": reminder_text
            })
        return reminders
    
    def delete_reminder(self, date: str, time: str) -> bool:
        '''
        Deletes a specific reminder.
        
        Args:
            date: The date of the reminder in Year-Month-Day format.
            time: The time of the reminder in HH:MM format.
        
        Returns:
            A boolean indicating success or failure.
        '''
        self._xlog.info(f"📝 Deleting a reminder for [{date}] at [{time}]")
        self.state.read_file()
        reminder_key = f"{date}.{time}"
        if self.state.key_exists(reminder_key, slugify_param_name=True):
            self.state.delete(reminder_key, slugify_param_name=True)
            self.state.write_file()
            self._xlog.info(f"📝 Reminder deleted for [{date}] at [{time}]")
            return True
        else:
            self._xlog.info(f"📝 No reminder found for [{date}] at [{time}]")
            return False
    
    def get_reminder(self, date: str, time: str) -> dict | bool:
        '''
        Retrieves a specific reminder.
        
        Args:
            date: The date of the reminder in Year-Month-Day format.
            time: The time of the reminder in HH:MM format.
        
        Returns:
            The reminder details as a JSON object or False if not found.
        '''
        self._xlog.info(f"📝 Retrieving a reminder for [{date}] at [{time}]")
        self.state.read_file()
        reminder_key = f"{date}.{time}"
        dd(reminder_key)
        dd(self.state.get_all())
        dd(self.state.key_exists(reminder_key, slugify_param_name=True))
        dd(self.state.get(reminder_key, slugify_param_name=True))
        if self.state.key_exists(reminder_key, slugify_param_name=True):
            reminder_text = self.state.get(reminder_key, slugify_param_name=True)
            self._xlog.info(f"📝 Reminder found for [{date}] at [{time}]: {reminder_text}")
            return {
                "date": date,
                "time": time,
                "text": reminder_text
            }
        else:
            self._xlog.info(f"📝 No reminder found for [{date}] at [{time}]")
            return False
    
    def delete_past_reminders(self) -> int:
        '''
        Deletes all reminders that are in the past.
        
        Returns:
            The number of reminders deleted.
        '''
        self._xlog.info(f"📝 Deleting past reminders")

        now = datetime.now()
        deleted_count = 0
        self.state.read_file()
        all_reminders = self.state.get_all()
        for date_str, times in all_reminders.items():
            for time_str in list(times.keys()):
                reminder_datetime_str = f"{date_str} {self._unslugify_time(time_str)}"
                reminder_datetime = datetime.strptime(reminder_datetime_str, f"{self.FORMAT_DATE} {self.FORMAT_TIME}")
                if reminder_datetime < now:
                    self.state.delete(f"{date_str}.{time_str}")
                    deleted_count += 1
                    self._xlog.info(f"📝 Deleted past reminder for [{date_str}] at [{time_str}]")

        if deleted_count > 0:
            self.state.write_file()

        self._xlog.info(f"📝 Deleted {deleted_count} past reminders")
        return deleted_count
    
    def _unslugify_time(self, slugified_time: str) -> str:
        '''
        Converts a slugified time back to its original format.

        Args:
            slugified_time: The slugified time string.

        Returns:
            The original time string.
        '''
        return slugified_time.replace("-", ":")