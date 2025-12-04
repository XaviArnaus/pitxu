
from pyxavi import Storage, Config, Dictionary

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

        self.state.set(reminder_key, reminder_text)
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
        reminders = []
        stored_reminders = self.state.get(date, {})
        for time, reminder_text in stored_reminders.items():
            reminders.append({
                "time": time,
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

        reminder_key = f"{date}.{time}"
        if self.state.key_exists(reminder_key):
            self.state.delete(reminder_key)
            self.state.write_file()
            self._xlog.info(f"📝 Reminder deleted for [{date}] at [{time}]")
            return True
        else:
            self._xlog.info(f"📝 No reminder found for [{date}] at [{time}]")
            return False
    
    def get_reminder(self, date: str, time: str) -> str | False:
        '''
        Retrieves a specific reminder.
        
        Args:
            date: The date of the reminder in Year-Month-Day format.
            time: The time of the reminder in HH:MM format.
        
        Returns:
            The reminder details as a JSON object or False if not found.
        '''
        self._xlog.info(f"📝 Retrieving a reminder for [{date}] at [{time}]")

        reminder_key = f"{date}.{time}"
        if self.state.key_exists(reminder_key):
            reminder_text = self.state.get(reminder_key)
            self._xlog.info(f"📝 Reminder found for [{date}] at [{time}]: {reminder_text}")
            return {
                "date": date,
                "time": time,
                "text": reminder_text
            }
        else:
            self._xlog.info(f"📝 No reminder found for [{date}] at [{time}]")
            return False