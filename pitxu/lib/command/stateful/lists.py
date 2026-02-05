from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.utils.lists import Lists
from pitxu.lib.interaction.interaction import Interaction

import logging

from datetime import datetime


class StatefulLists(PyXavi, Command):

    _lists: Lists = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(StatefulLists, self).init_pyxavi(config=config, params=params)

        self._lists = Lists(config=config, params=params)

    def create_list(self, list_name: str) -> dict | str:
        '''
        Create a new list with the specified name.

        Args:
            list_name (str): The name of the list to create.

        Returns:
            str: A confirmation message or an error message.
        '''
        try:
            self._xlog.info(f"📝 Request for Creating a new list: {list_name}")
            result = self._lists.create_list(list_name)
            if result:
                # It should return the created list, not the success string.
                return result
            else:
                existing_list = self._lists.get_list(list_name)
                return self._xconfig.get("language.lists.list_already_exists." + self._xparams.get("language")) % existing_list["name"]

        except Exception as e:
            self._xlog.error(f"🛑 Error creating list [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_creation_error." + self._xparams.get("language"))

    def get_lists(self) -> list[str]:
        '''
        Retrieve all lists.

        Returns:
            list[str]: A list of all lists in a JSON format or an error message as string.
        '''
        self._xlog.info(f"📝 Request for Retrieving all lists")
        try:
            return [list_object["name"] for list_object in self._lists.get_lists()]
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving lists: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_retrieval_error." + self._xparams.get("language"))

    def delete_list(self, list_name: str) -> dict | str:
        '''
        Delete a specific list by name.

        Args:
            list_name (str): The name of the list to delete.

        Returns:
            dict | str: If successful, returns a JSON with the deleted list details; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Deleting a list for [{list_name}]")
        try:
            list_deleted = self._lists.get_list(list_name)
            success = self._lists.delete_list(list_name)
            if success:
                return list_deleted
            else:
                return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name
        except Exception as e:
            self._xlog.error(f"🛑 Error deleting list for [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_deletion_error." + self._xparams.get("language"))

    def get_list(self, list_name: str) -> dict | str:
        '''
        Retrieve a specific list by name.

        Args:
            list_name (str): The name of the list to retrieve.

        Returns:
            dict | str: If successful, returns a JSON with the list details; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Retrieving a list for [{list_name}]")
        try:
            list_found = self._lists.get_list(list_name)
            if list_found:
                return list_found
            else:
                return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving list for [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_retrieval_error." + self._xparams.get("language"))

    def update_list(self, list_name: str, new_name: str = None, new_description: str = None) -> dict | str:
        '''
        Update the description of a specific list by name.

        Args:
            list_name (str): The name of the list to update.
            new_name (str, optional): The new name for the list.
            new_description (str): The new description for the list.

        Returns:
            dict | str: If successful, returns a JSON with the updated list details; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Updating a list for [{list_name}]")
        try:
            success = self._lists.update_list(list_name, new_name=new_name, new_description=new_description)
            if success:
                return success
            else:
                return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name
        except Exception as e:
            self._xlog.error(f"🛑 Error updating list for [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_update_error." + self._xparams.get("language"))

    def add_entry_to_list(self, list_name: str, entry_text: str) -> dict | str:
        '''
        Add an entry to a specific list.

        Args:
            list_name (str): The name of the list to add the entry to.
            entry_text (str): The text of the entry to add.

        Returns:
            dict | str: If successful, returns a JSON with the updated list details; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Adding an entry to list [{list_name}]")
        try:
            success = self._lists.add_entry(list_name, entry_text)
            if success:
                return success
            else:
                return self._xconfig.get("language.lists.entry_addition_error." + self._xparams.get("language")) % list_name
        except Exception as e:
            self._xlog.error(f"🛑 Error adding entry to list for [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_entry_addition_error." + self._xparams.get("language"))

    def delete_entry_from_list(self, list_name: str, by_position: int = None, by_datetime: str = None) -> dict | str:
        '''
        Delete an entry from a specific list.

        Args:
            list_name (str): The name of the list to delete the entry from.
            by_position (int, optional): The position of the entry to delete.
            by_datetime (str, optional): The datetime of the entry to delete.

        Returns:
            dict | str: If successful, returns a JSON with the updated list details; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Deleting an entry from list [{list_name}] by {'Position [' + str(by_position) + ']' if by_position else 'Time [' + by_datetime + ']'}")
        try:
            success = self._lists.delete_entry(list_name, by_position=by_position, by_datetime=by_datetime)
            if success:
                return success
            else:
                return self._xconfig.get("language.lists.entry_deletion_error." + self._xparams.get("language")) % (list_name, by_position, by_datetime)
        except Exception as e:
            self._xlog.error(f"🛑 Error deleting entry from list for [{list_name}] by {'Position [' + str(by_position) + ']' if by_position else 'Time [' + by_datetime + ']'}: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_entry_deletion_error." + self._xparams.get("language"))
    
    def get_all_entries_from_list(self, list_name: str) -> list | str:
        '''
        Get all entries from a specific list.

        Args:
            list_name (str): The name of the list to get the entries from.
        Returns:
            list | str: If successful, returns a list with the list details including all entries; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Getting all entries from list [{list_name}]")
        try:
            success = self._lists.get_entries(list_name)
            if success:
                return list(success.values()) if isinstance(success, dict) else success
            else:
                return self._xconfig.get("language.lists.all_entries_retrieval_error." + self._xparams.get("language")) % list_name
        except Exception as e:
            self._xlog.error(f"🛑 Error getting all entries from list for [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_all_entries_retrieval_error." + self._xparams.get("language"))

    def get_one_entry_from_list(self, list_name: str, by_position: int = None, by_datetime: str = None) -> dict | str:
        '''
        Get an entry from a specific list.

        Args:
            list_name (str): The name of the list to get the entry from.
            by_position (int, optional): The position of the entry to get.
            by_datetime (str, optional): The datetime of the entry to get.

        Returns:
            dict | str: If successful, returns a JSON with the entry details; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Getting an entry from list [{list_name}] by {'Position [' + str(by_position) + ']' if by_position else 'Time [' + by_datetime + ']'}")
        try:
            success = self._lists.get_entry(list_name, by_position=by_position, by_datetime=by_datetime)
            if success:
                return success
            else:
                return self._xconfig.get("language.lists.entry_retrieval_error." + self._xparams.get("language")) % (list_name, by_position, by_datetime)
        except Exception as e:
            self._xlog.error(f"🛑 Error getting entry from list for [{list_name}] by [{'Position [' + str(by_position) + ']' if by_position else 'Time [' + by_datetime + ']'}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_entry_retrieval_error." + self._xparams.get("language"))

    def show_create_list(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            log.debug(f"📝 Showing Create List on Foreground display: {value}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=value["name"] if isinstance(value, dict) and "name" in value else str(value),
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
        except Exception as e:
            log.error(f"🛑 Error showing Create List on Foreground display: {e}")

    def show_get_list_counter(self, log: logging, interaction: Interaction, value: list, args: dict = None) -> None:

        try:
            lists_count = len(value)

            log.debug(f"📝 Showing Get Lists Counter on Foreground display: {lists_count}")
            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=f"{lists_count} list{'s' if lists_count != 1 else ''}.",
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE)
        except Exception as e:
            log.error(f"🛑 Error showing Get Lists Counter on Foreground display: {e}")

    def show_affected_list(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            log.debug(f"📝 Showing Affected List on Foreground display: {value}")

            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=value["description"] if isinstance(value, dict) and "description" in value else None,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG,
                header=value["name"] if isinstance(value, dict) and "name" in value else None,
                header_font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE
        )
        except Exception as e:
            log.error(f"🛑 Error showing Affected List on Foreground display: {e}")
    
    def show_affected_entry(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            log.debug(f"📝 Showing Affected Entry on Foreground display: {value}")

            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=value["text"] if isinstance(value, dict) and "text" in value else None,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG,
                header=f"{value['list_name']}" if isinstance(value, dict) and "list_name" in value else None,
                header_font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE
        )
        except Exception as e:
            log.error(f"🛑 Error showing Affected Entry on Foreground display: {e}")
    
    def show_entries_for_list(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            log.debug(f"📝 Showing Entries for List on Foreground display: {value}")

            value = dict(value).values()
            entries_text = "\n".join([f"{entry['text']}" for entry in value]) if isinstance(value, list) else str(value)
            list_name = value[0]["list_name"] if isinstance(value, list) and len(value) > 0 and "list_name" in value[0] else None

            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=entries_text,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_MEDIUM,
                header=f"Entries for {list_name}" if list_name else None,
                header_font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE if list_name else None
            )
        except Exception as e:
            log.error(f"🛑 Error showing Entries for List on Foreground display: {e}")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.create_list,
                self.get_lists,
                self.delete_list,
                self.update_list,
                self.add_entry_to_list,
                self.delete_entry_from_list,
                self.get_list,
                self.get_one_entry_from_list,
                self.get_all_entries_from_list,
                self.get_all_entries_from_list]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "create_list":
            return self.show_create_list
        elif function_name == "delete_list" or \
                function_name == "update_list" or \
                function_name == "get_lists" or \
                function_name == "get_list":
            return self.show_affected_list
        elif function_name == "add_entry_to_list" or \
                function_name == "delete_entry_from_list" or \
                function_name == "get_one_entry_from_list":
            return self.show_affected_entry
        elif function_name == "get_all_entries_from_list":
            return self.show_entries_for_list
        return self.default_empty_callback
    
# '2025-12-31':
#     13-00: 'Project Idea: Use four lasers to project a visible frame onto the desk. This frame will show the camera''s exact field of view, allowing for perfect, screen-less positioning of objects for analysis.'
#     13-15: 'Project Idea: Create an `email_myself(subject, body)` tool. It will use Python''s `smtplib` and a secure App Password to send notes and ideas directly to your email inbox.'
#     13-30: Delete the lines of code related to the conversation response timeout.