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

        # The application shares one Reminders (one connection to the database) with the tools, through the params.
        self._reminders = self._xparams.get("reminders") if self._xparams.key_exists("reminders") \
            else Reminders(config=config, params=params)

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

    def _as_id(self, reminder_id) -> int | None:
        """ The id as the integer it is, or None if it is not a number (the chatbot may send anything). """
        try:
            return int(reminder_id)
        except (TypeError, ValueError):
            return None

    def _not_found(self, reminder_id) -> str:
        return self._message("reminder_not_found") % reminder_id

    def _is_in_the_past(self, date: str, time: str) -> bool:
        """ The minute of the reminder is over. The current minute is not the past. """
        reminder_datetime = datetime.strptime(f"{date} {time}", f"{Reminders.FORMAT_DATE} {Reminders.FORMAT_TIME}")
        return reminder_datetime < datetime.now().replace(second=0, microsecond=0)

    def create_reminder(self, date: str, time: str, reminder_text: str) -> dict | str:
        '''
        Create a reminder for a specific date and time, with a specified text.
        The date and time must not be in the past. Several reminders can share the same date and time.
        
        Args:
            date (str): The date for the reminder in Year-Month-Day format.
            time (str): The time for the reminder in HH:MM format.
            reminder_text (str): The text of the reminder.
        
        Returns:
            dict | str: The reminder created, with its `id`, or an error message.
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
            
            return self._reminders.create_reminder(date, time, reminder_text)

        except Exception as e:
            self._xlog.error(f"🛑 Error creating reminder for [{date}] [{time}] [{reminder_text}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("reminder_creation_error")
        
    def get_reminders_for_date(self, date: str) -> list[dict] | str:
        '''
        Retrieve the reminders still pending for a specific date, in time order.
        
        Args:
            date (str): The date to retrieve reminders for in Year-Month-Day format.
        
        Returns:
            list[dict] | str: A list of reminders with their `id`, `time` and `text`, or an error message.
        '''

        self._xlog.info(f"📝 Request for Retrieving reminders for [{date}]")
        try:
            validated = self._validate_date_and_time(date)
            if isinstance(validated, str):
                return validated
            date, _ = validated

            return [{"id": reminder["id"], "time": reminder["time"], "text": reminder["text"]}
                    for reminder in self._reminders.get_reminders_for_date(date)]
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving reminders for date [{date}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("reminder_retrieval_error")
    
    def delete_reminder(self, reminder_id: int) -> dict | str:
        '''
        Delete a reminder by its id.
        
        Args:
            reminder_id (int): The id of the reminder.
        
        Returns:
            dict | str: If successful, the reminder that was deleted; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Deleting the reminder [{reminder_id}]")
        try:
            found = self._as_id(reminder_id)
            deleted = self._reminders.delete_reminder(found) if found is not None else False
            return deleted if deleted else self._not_found(reminder_id)
        except Exception as e:
            self._xlog.error(f"🛑 Error deleting the reminder [{reminder_id}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("reminder_deletion_error")
    
    def get_reminder(self, reminder_id: int) -> dict | str:
        '''
        Retrieve a reminder by its id, also if it was already announced (`announced` tells).
        
        Args:
            reminder_id (int): The id of the reminder.
        
        Returns:
            dict | str: The reminder, or an error message.
        '''
        self._xlog.info(f"📝 Request for Retrieving the reminder [{reminder_id}]")
        try:
            found = self._as_id(reminder_id)
            reminder = self._reminders.get_reminder(found) if found is not None else False
            return reminder if reminder else self._not_found(reminder_id)
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving the reminder [{reminder_id}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("reminder_retrieval_error")
    
    def update_reminder(self, reminder_id: int, new_text: str) -> dict | str:
        '''
        Update the text of a reminder by its id.
        
        Args:
            reminder_id (int): The id of the reminder.
            new_text (str): The new text for the reminder.
        
        Returns:
            dict | str: If successful, the reminder updated; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Updating the reminder [{reminder_id}] to: {new_text}")
        try:
            found = self._as_id(reminder_id)
            updated = self._reminders.update_reminder(found, new_text) if found is not None else False
            return updated if updated else self._not_found(reminder_id)
        except Exception as e:
            self._xlog.error(f"🛑 Error updating the reminder [{reminder_id}] to [{new_text}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("reminder_update_error")
    
    def move_reminder(self, reminder_id: int, new_date: str, new_time: str) -> dict | str:
        '''
        Move a reminder by its id to another date and time, that must not be in the past.
        A reminder that was already announced is pending again after it is moved (a snooze).

        Args:
            reminder_id (int): The id of the reminder.
            new_date (str): The new date for the reminder in Year-Month-Day format.
            new_time (str): The new time for the reminder in HH:MM format.

        Returns:
            dict | str: If successful, the reminder moved, with its `previous_date` and `previous_time`; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Moving the reminder [{reminder_id}] to [{new_date}] at [{new_time}]")
        try:
            validated = self._validate_date_and_time(new_date, new_time)
            if isinstance(validated, str):
                return validated
            new_date, new_time = validated

            # Moving to the past would be a reminder that is never announced.
            if self._is_in_the_past(new_date, new_time):
                return self._message("reminder_past_datetime")

            found = self._as_id(reminder_id)
            moved = self._reminders.move_reminder(found, new_date, new_time) if found is not None else False
            return moved if moved else self._not_found(reminder_id)
        except Exception as e:
            self._xlog.error(f"🛑 Error moving the reminder [{reminder_id}] to [{new_date}] [{new_time}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("reminder_move_error")

    def show_create_reminder(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            # The reminder created is told in the language of the session. A message (an error) is shown as it is.
            text = value if not isinstance(value, dict) else \
                self._message("reminder_set") % (value["date"], value["time"], value["text"])
            log.debug(f"📝 Showing Create Reminder on eInk: {text}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=text,
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
        self._show_changed_reminder(
            log, interaction, value, "reminder_moved",
            lambda r: (r["previous_date"], r["previous_time"], r["date"], r["time"]))

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