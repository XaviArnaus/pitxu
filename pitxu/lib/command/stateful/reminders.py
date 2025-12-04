from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.eink import EinkCanvas
from pitxu.lib.utils.reminders import Reminders

from datetime import datetime


class StatefulReminders(PyXavi, Command):

    _reminders: Reminders = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(StatefulReminders, self).init_pyxavi(config=config, params=params)

        self._reminders = Reminders(config=config, params=params)

    def create_reminder(self, date: str, time: str, reminder_text: str) -> str:
        '''
        Creates a reminder for a specific date.
        
        Args:
            date: The date for the reminder in Year-Month-Day format.
            time: The time for the reminder in HH:MM format.
            reminder_text: The text of the reminder.
        
        Returns:
            A confirmation message or an error message.
        '''
        try:
            self._xlog.info(f"📝 Creating a reminder for [{date}] at [{time}]: {reminder_text}")
            # Validate date and time format
            try:
                datetime.strptime(date, Reminders.FORMAT_DATE)
            except ValueError:
                return self._xconfig.get("language.reminders.reminder_invalid_date." + self._xparams.get("language"))
            
            try:
                datetime.strptime(time, Reminders.FORMAT_TIME)
            except ValueError:
                return self._xconfig.get("language.reminders.reminder_invalid_time." + self._xparams.get("language"))
            
            result = self._reminders.create_reminder(date, time, reminder_text)
            if result:
                return self._xconfig.get("language.reminders.reminder_set." + self._xparams.get("language")) % (date, time, reminder_text)
            else:
                existing_reminder = self._reminders.get_reminder(date, time)
                return self._xconfig.get("language.reminders.reminder_already_exists." + self._xparams.get("language")) % existing_reminder["text"]

        except Exception as e:
            self._xlog.error(f"🛑 Error creating reminder for [{date}] [{time}] [{reminder_text}]: {e}")
            return self._xconfig.get("language.reminders.reminder_creation_error." + self._xparams.get("language"))
        
    def get_reminders_for_date(self, date: str) -> list[str]:
        '''
        Retrieves all reminders for a specific date.
        
        Args:
            date: The date to retrieve reminders for in Year-Month-Day format.
        
        Returns:
            A list of reminders for the specified date in a JSON format or an error message as string.
        '''

        self._xlog.info(f"📝 Retrieving reminders for [{date}]")
        try:
            return self._reminders.get_reminders_for_date(date)
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving reminders for date [{date}]: {e}")
            return self._xconfig.get("language.reminders.reminder_retrieval_error." + self._xparams.get("language"))
    
    def delete_reminder(self, date: str, time: str) -> str:
        '''
        Deletes a specific reminder.
        
        Args:
            date: The date of the reminder in Year-Month-Day format.
            time: The time of the reminder in HH:MM format.
        
        Returns:
            A confirmation message or an error message.
        '''
        self._xlog.info(f"📝 Deleting a reminder for [{date}] at [{time}]")
        try:
            success = self._reminders.delete_reminder(date, time)
            if success:
                return self._xconfig.get("language.reminders.reminder_deleted." + self._xparams.get("language")) % (date, time)
            else:
                return self._xconfig.get("language.reminders.reminder_not_found." + self._xparams.get("language")) % (date, time)
        except Exception as e:
            self._xlog.error(f"🛑 Error deleting reminder for [{date}] [{time}]: {e}")
            return self._xconfig.get("language.reminders.reminder_deletion_error." + self._xparams.get("language"))
        




        
    
    # def callback_show_date(self, main_instance, value: any, args: dict = None) -> None:
    #     """
    #     Callback for `get_current_date_without_time` that gets called AFTER chatbot from `main`.

    #     With this, we have the `main` context to play with for the given function call.
    #     For example, show the date in the eInk while we TTS the anwer from the Chatbot.

    #     It is meant to trigger stuff, not to return anything.
    #     Yeah, it couples it with other parts (why would I couple it with the eInk class?),
    #     but is thought as a feature of the application. Is the application that needs to evolve
    #     to abstract these actions (and therefore the communication() method there).

    #     Args:
    #         main_instance: The `main` application instance.
    #         value: The value returned from the Chatbot AFTER it ran `get_current_date_without_time`.

    #     """
    #     main_instance._xlog.info(f"The current date in the callback is: {value}")

    #     try:
    #         # Get a datetime object from the value
    #         date_obj = datetime.strptime(value, self.format)
    #         value = date_obj.strftime(self.displayed_format)

    #         main_instance._xlog.error(f"📆 Showing date on eInk: {value}")
    #         main_instance.show_arbitrary_text_on_eink(
    #             icon="📆",
    #             text=value,
    #             font_size=EinkCanvas.FONT_BIG_SIZE)
    #     except Exception as e:
    #         main_instance._xlog.error(f"🛑 Error showing date on eInk: {e}")

    # def get_tool_definition(self) -> list[callable]:
    #     """
    #     Returns the methods of the class that will be used as tools by the chatbot.

    #     It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
    #     """
    #     return [self.get_current_date_without_time]

    # def get_callback_by_given_function_name(self, function_name: str) -> callable:
    #     """
    #     Gets the callback function for a given function name.

    #     It expects the function_name because a class may provide multiple functions as tools.

    #     Args:
    #         function_name: The name of the function to get the callback for.
    #     """
    #     if function_name == "get_current_date_without_time":
    #         return self.callback_show_date
    #     return self.default_empty_callback