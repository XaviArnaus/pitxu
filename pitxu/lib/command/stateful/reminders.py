from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.utils.reminders import Reminders
from pitxu.lib.interaction.interaction import Interaction

import logging

from datetime import datetime


class StatefulReminders(PyXavi, Command):

    _reminders: Reminders = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(StatefulReminders, self).init_pyxavi(config=config, params=params)

        self._reminders = Reminders(config=config, params=params)

    def create_reminder(self, date: str, time: str, reminder_text: str) -> str:
        '''
        Create a reminder for a specific date and time, with a specified text.
        
        Args:
            date (str): The date for the reminder in Year-Month-Day format.
            time (str): The time for the reminder in HH:MM format.
            reminder_text (str): The text of the reminder.
        
        Returns:
            str: A confirmation message or an error message.
        '''
        try:
            self._xlog.info(f"📝 Request for Creating a reminder for [{date}] at [{time}]: {reminder_text}")
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
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.reminders.reminder_creation_error." + self._xparams.get("language"))
        
    def get_reminders_for_date(self, date: str) -> list[str]:
        '''
        Retrieve all reminders for a specific date.
        
        Args:
            date (str): The date to retrieve reminders for in Year-Month-Day format.
        
        Returns:
            list[str]: A list of reminders for the specified date in a JSON format or an error message as string.
        '''

        self._xlog.info(f"📝 Request for Retrieving reminders for [{date}]")
        try:
            return self._reminders.get_reminders_for_date(date)
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving reminders for date [{date}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.reminders.reminder_retrieval_error." + self._xparams.get("language"))
    
    def delete_reminder(self, date: str, time: str) -> str:
        '''
        Delete a specific reminder by date and time.
        
        Args:
            date (str): The date of the reminder in Year-Month-Day format.
            time (str): The time of the reminder in HH:MM format.
        
        Returns:
            dict | str: If successful, returns a JSON with the deleted reminder details; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Deleting a reminder for [{date}] at [{time}]")
        try:
            reminder_deleted = self._reminders.get_reminder(date, time)
            success = self._reminders.delete_reminder(date, time)
            if success:
                # return self._xconfig.get("language.reminders.reminder_deleted." + self._xparams.get("language")) % (date, time)
                return {
                    "date": date,
                    "time": time,
                    "text": reminder_deleted["text"]
                }
            else:
                return self._xconfig.get("language.reminders.reminder_not_found." + self._xparams.get("language")) % (date, time)
        except Exception as e:
            self._xlog.error(f"🛑 Error deleting reminder for [{date}] [{time}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.reminders.reminder_deletion_error." + self._xparams.get("language"))
    
    def get_reminder(self, date: str, time: str) -> dict | str:
        '''
        Retrieve a specific reminder by date and time.
        
        Args:
            date (str): The date of the reminder in Year-Month-Day format.
            time (str): The time of the reminder in HH:MM format.
        
        Returns:
            dict | str: The reminder in a JSON format or an error message as string.
        '''
        self._xlog.info(f"📝 Request for Retrieving a reminder for [{date}] at [{time}]")
        try:
            reminder = self._reminders.get_reminder(date, time)
            if reminder:
                return reminder
            else:
                return self._xconfig.get("language.reminders.reminder_not_found." + self._xparams.get("language")) % (date, time)
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving reminder for [{date}] [{time}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.reminders.reminder_retrieval_error." + self._xparams.get("language"))
    
    def update_reminder(self, date: str, time: str, new_text: str) -> str:
        '''
        Update the text of a specific reminder by date and time.
        
        Args:
            date (str): The date of the reminder in Year-Month-Day format.
            time (str): The time of the reminder in HH:MM format.
            new_text (str): The new text for the reminder.
        
        Returns:
            dict | str: If successful, returns a JSON with the updated reminder details; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Updating a reminder for [{date}] at [{time}] to: {new_text}")
        try:
            success = self._reminders.update_reminder(date, time, new_text)
            if success:
                return {
                    "date": date,
                    "time": time,
                    "text": new_text
                }
            else:
                return self._xconfig.get("language.reminders.reminder_not_found." + self._xparams.get("language")) % (date, time)
        except Exception as e:
            self._xlog.error(f"🛑 Error updating reminder for [{date}] [{time}] to [{new_text}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.reminders.reminder_update_error." + self._xparams.get("language"))
    
    def move_reminder(self, old_date: str, old_time: str, new_date: str, new_time: str) -> str:
        '''
        Move a reminder from one date and time to another.
        
        Args:
            old_date (str): The current date of the reminder in Year-Month-Day format.
            old_time (str): The current time of the reminder in HH:MM format.
            new_date (str): The new date for the reminder in Year-Month-Day format.
            new_time (str): The new time for the reminder in HH:MM format.

        Returns:
            dict | str: If successful, returns a JSON with the moved reminder details; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Moving a reminder from [{old_date}] at [{old_time}] to [{new_date}] at [{new_time}]")
        try:
            success = self._reminders.move_reminder(old_date, old_time, new_date, new_time)
            if success:
                return {
                    "date": new_date,
                    "time": new_time,
                    "text": success["text"]
                }
            else:
                return self._xconfig.get("language.reminders.reminder_not_found." + self._xparams.get("language")) % (old_date, old_time)
        except Exception as e:
            self._xlog.error(f"🛑 Error moving reminder from [{old_date}] [{old_time}] to [{new_date}] [{new_time}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.reminders.reminder_move_error." + self._xparams.get("language"))

    def show_create_reminder(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            log.debug(f"📝 Showing Create Reminder on eInk: {value}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=value,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
        except Exception as e:
            log.error(f"🛑 Error showing Create Reminder on eInk: {e}")

    def show_get_reminders_for_date(self, log: logging, interaction: Interaction, value: list, args: dict = None) -> None:

        try:
            reminders_count = len(value)

            log.debug(f"📝 Showing Get Reminders for Date on eInk: {reminders_count}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=f"{reminders_count} reminder{'s' if reminders_count != 1 else ''}.",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing Get Reminders for Date on eInk: {e}")

    def show_affected_reminder(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            log.debug(f"📝 Showing Affected Reminder on eInk: {value}")

            if isinstance(value, dict):
                value = f"{value['date']} {value['time']}"

            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=value,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
        except Exception as e:
            log.error(f"🛑 Error showing Affected Reminder on eInk: {e}")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.create_reminder,
                self.get_reminders_for_date,
                self.delete_reminder,
                self.update_reminder,
                self.move_reminder,
                self.get_reminder]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "create_reminder":
            return self.show_create_reminder
        elif function_name == "get_reminders_for_date":
            return self.show_get_reminders_for_date
        elif function_name == "delete_reminder" or \
                function_name == "update_reminder" or \
                function_name == "move_reminder" or \
                function_name == "get_reminder":
            return self.show_affected_reminder
        return self.default_empty_callback
    
# '2025-12-31':
#     13-00: 'Project Idea: Use four lasers to project a visible frame onto the desk. This frame will show the camera''s exact field of view, allowing for perfect, screen-less positioning of objects for analysis.'
#     13-15: 'Project Idea: Create an `email_myself(subject, body)` tool. It will use Python''s `smtplib` and a secure App Password to send notes and ideas directly to your email inbox.'
#     13-30: Delete the lines of code related to the conversation response timeout.