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

    def _message(self, key: str) -> str:
        """ The message `language.reminders.<key>` in the current language. """
        return self._xconfig.get("language.reminders." + key + "." + self._xparams.get("language"))

    def _validate_date_and_time(self, date: str, time: str = None) -> tuple | str:
        """
        Checks the date (and the time, if given) and gives them normalized, like the Reminders store and look them up:
        `2026-1-5` is `2026-01-05` and `9:05` is `09:05`. Otherwise they are never found.

        Returns:
            tuple: (date, time) normalized (time is None if none was given), or
            str: the message to answer when the date or the time are not valid.
        """
        try:
            date = datetime.strptime(date, Reminders.FORMAT_DATE).strftime(Reminders.FORMAT_DATE)
        except (ValueError, TypeError):
            return self._message("reminder_invalid_date")

        if time is not None:
            try:
                time = datetime.strptime(time, Reminders.FORMAT_TIME).strftime(Reminders.FORMAT_TIME)
            except (ValueError, TypeError):
                return self._message("reminder_invalid_time")

        return (date, time)

    def _is_in_the_past(self, date: str, time: str) -> bool:
        """ The minute of the reminder is over. The current minute is not the past. """
        reminder_datetime = datetime.strptime(f"{date} {time}", f"{Reminders.FORMAT_DATE} {Reminders.FORMAT_TIME}")
        return reminder_datetime < datetime.now().replace(second=0, microsecond=0)

    def create_reminder(self, date: str, time: str, reminder_text: str) -> str:
        '''
        Create a reminder for a specific date and time, with a specified text.
        The date and time must not be in the past.
        
        Args:
            date (str): The date for the reminder in Year-Month-Day format.
            time (str): The time for the reminder in HH:MM format.
            reminder_text (str): The text of the reminder.
        
        Returns:
            str: A confirmation message or an error message.
        '''
        try:
            self._xlog.info(f"📝 Request for Creating a reminder for [{date}] at [{time}]: {reminder_text}")
            # Validate date and time format, and keep them normalized.
            validated = self._validate_date_and_time(date, time)
            if isinstance(validated, str):
                return validated
            date, time = validated

            # A reminder in the past would never be announced.
            if self._is_in_the_past(date, time):
                return self._message("reminder_past_datetime")
            
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
            validated = self._validate_date_and_time(date)
            if isinstance(validated, str):
                return validated
            date, _ = validated

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
            validated = self._validate_date_and_time(date, time)
            if isinstance(validated, str):
                return validated
            date, time = validated

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
            validated = self._validate_date_and_time(date, time)
            if isinstance(validated, str):
                return validated
            date, time = validated

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
            validated = self._validate_date_and_time(date, time)
            if isinstance(validated, str):
                return validated
            date, time = validated

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
            validated_old = self._validate_date_and_time(old_date, old_time)
            if isinstance(validated_old, str):
                return validated_old
            old_date, old_time = validated_old
            validated_new = self._validate_date_and_time(new_date, new_time)
            if isinstance(validated_new, str):
                return validated_new
            new_date, new_time = validated_new

            # Moving to the past would be a reminder that is never announced.
            if self._is_in_the_past(new_date, new_time):
                return self._message("reminder_past_datetime")

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
            canvas = interaction.get_canvas_from_foreground_display()
            if not isinstance(value, list):
                # The tool answered with a message (an error): just show it.
                text, font_size = str(value), canvas.FONT_SIZE_BIG
            elif len(value) == 0:
                text, font_size = self._message("reminder_list_empty"), canvas.FONT_SIZE_BIG
            elif len(value) == 1:
                text, font_size = self._message("reminder_count_one"), canvas.FONT_SIZE_HUGE
            else:
                text, font_size = self._message("reminder_count_many") % len(value), canvas.FONT_SIZE_HUGE

            log.debug(f"📝 Showing Get Reminders for Date on eInk: {text}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=text,
                font_size=font_size)
        except Exception as e:
            log.error(f"🛑 Error showing Get Reminders for Date on eInk: {e}")

    def show_affected_reminder(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """ For a reminder that was only read: its date and time. A message (an error) is shown as it is. """

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

    def _show_changed_reminder(self, log: logging, interaction: Interaction, value: any, message_key: str, message_values: callable) -> None:
        """
        Shows what was done to a reminder, in the language of the message `language.reminders.<message_key>`.
        `message_values` gives the values for its placeholders from the reminder. A message (an error) is shown as it is.
        """
        try:
            text = value if not isinstance(value, dict) else self._message(message_key) % message_values(value)
            log.debug(f"📝 Showing the changed reminder on eInk: {text}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=text,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
        except Exception as e:
            log.error(f"🛑 Error showing the changed reminder on eInk: {e}")

    def show_deleted_reminder(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        self._show_changed_reminder(log, interaction, value, "reminder_deleted", lambda r: (r["date"], r["time"]))

    def show_updated_reminder(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        self._show_changed_reminder(log, interaction, value, "reminder_updated", lambda r: (r["date"], r["time"], r["text"]))

    def show_moved_reminder(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        # The old date and time are what the chatbot asked for.
        args = args or {}
        self._show_changed_reminder(
            log, interaction, value, "reminder_moved",
            lambda r: (args.get("old_date", "?"), args.get("old_time", "?"), r["date"], r["time"]))

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
        elif function_name == "delete_reminder":
            return self.show_deleted_reminder
        elif function_name == "update_reminder":
            return self.show_updated_reminder
        elif function_name == "move_reminder":
            return self.show_moved_reminder
        elif function_name == "get_reminder":
            return self.show_affected_reminder
        return self.default_empty_callback
    
# '2025-12-31':
#     13-00: 'Project Idea: Use four lasers to project a visible frame onto the desk. This frame will show the camera''s exact field of view, allowing for perfect, screen-less positioning of objects for analysis.'
#     13-15: 'Project Idea: Create an `email_myself(subject, body)` tool. It will use Python''s `smtplib` and a secure App Password to send notes and ideas directly to your email inbox.'
#     13-30: Delete the lines of code related to the conversation response timeout.