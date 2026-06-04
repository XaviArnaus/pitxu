from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.utils.lists import Lists
from pitxu.lib.interaction.interaction import Interaction

import logging

from datetime import datetime


class StatefulLists(PyXavi, Command):

    _lists: Lists = None

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(StatefulLists, self).init_pyxavi(config=config, params=params)

        self._lists = Lists(config=config, params=params)

    def create_list(self, list_name: str) -> dict | str:
        '''
        Create a new list with the specified name.

        Args:
            list_name (str): The name of the list to create.

        Returns:
            dict: The created list or an error message.
        '''
        try:
            self._xlog.info(f"📝 Request for Creating a new list: {list_name}")
            created_list = self._lists.create_list(list_name)
            if created_list:
                return created_list
            else:
                existing_list = self._lists.get_list(list_name)
                return self._xconfig.get("language.lists.list_already_exists." + self._xparams.get("language")) % existing_list["name"]

        except Exception as e:
            self._xlog.error(f"🛑 Error creating list [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_creation_error." + self._xparams.get("language"))

    def get_lists(self) -> list[dict] | str:
        '''
        Retrieve all lists.

        Returns:
            list[dict] | str: A list of all registered lists or an error message as string.
        '''
        self._xlog.info(f"📝 Request for Retrieving all lists")
        try:
            return [list_object for list_object in self._lists.get_lists().values()]
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

        # Try to come closer to the list name that the user provided, in case there is a small typo
        parsed_list_name = self._find_list_with_highest_similarity_name(list_name)
        self._log_debug(f"Parsed list name: [{parsed_list_name}] for input list name: {list_name}")

        if parsed_list_name is None:
            return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name
        try:
            list_deleted = self._lists.delete_list(parsed_list_name)
            if list_deleted:
                return list_deleted
            else:
                return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % parsed_list_name
        except Exception as e:
            self._xlog.error(f"🛑 Error deleting list for [{parsed_list_name}]: {e}")
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
        parsed_list_name = self._find_list_with_highest_similarity_name(list_name)
        self._log_debug(f"Parsed list name: [{parsed_list_name}] for input list name: {list_name}")

        if parsed_list_name is None:
            return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name
        try:
            list_found = self._lists.get_list(parsed_list_name)
            if list_found:
                return list_found
            else:
                return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % parsed_list_name
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving list for [{parsed_list_name}]: {e}")
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
            dict | str: If successful, returns the updated list; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Updating a list for [{list_name}]")
        parsed_list_name = self._find_list_with_highest_similarity_name(list_name)
        self._log_debug(f"Parsed list name: [{parsed_list_name}] for input list name: {list_name}")

        if parsed_list_name is None:
            return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name
        try:
            new_list_data = self._lists.update_list(parsed_list_name, new_name=new_name, new_description=new_description)
            if new_list_data:
                return new_list_data
            else:
                return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % parsed_list_name
        except Exception as e:
            self._xlog.error(f"🛑 Error updating list for [{parsed_list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_update_error." + self._xparams.get("language"))

    def add_entry_to_list(self, list_name: str, entry_text: str) -> dict | str:
        '''
        Add an entry to a specific list.

        Args:
            list_name (str): The name of the list to add the entry to.
            entry_text (str): The text of the entry to add.

        Returns:
            dict | str: If successful, returns added entry details as a dictionary; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Adding an entry to list [{list_name}]")
        parsed_list_name = self._find_list_with_highest_similarity_name(list_name)
        self._log_debug(f"Parsed list name: [{parsed_list_name}] for input list name: {list_name}")

        if parsed_list_name is None:
            return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name
        try:
            new_entry_data = self._lists.add_entry(parsed_list_name, entry_text)
            if new_entry_data:
                return new_entry_data
            else:
                return self._xconfig.get("language.lists.entry_addition_error." + self._xparams.get("language")) % parsed_list_name
        except Exception as e:
            self._xlog.error(f"🛑 Error adding entry to list for [{parsed_list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_entry_addition_error." + self._xparams.get("language")) % parsed_list_name

    def delete_entry_from_list(self, list_name: str, position: int) -> dict | str:
        '''
        Delete an entry from a specific list.

        Args:
            list_name (str): The name of the list to delete the entry from.
            position (int): The position of the entry to delete.

        Returns:
            dict | str: If successful, returns deleted entry; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Deleting an entry from list [{list_name}] at position [{position}]")

        # Try to come closer to the list name that the user provided, in case there is a small typo
        parsed_list_name = self._find_list_with_highest_similarity_name(list_name)
        self._log_debug(f"Parsed list name: [{parsed_list_name}] for input list name: {list_name}")
        if parsed_list_name is None:
            return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name

        try:
            deleted_entry = self._lists.delete_entry(parsed_list_name, position=position)
            if deleted_entry:
                return deleted_entry
            else:
                return self._xconfig.get("language.lists.entry_deletion_error." + self._xparams.get("language")) % (parsed_list_name, str(position))
        except Exception as e:
            self._xlog.error(f"🛑 Error deleting entry from list for [{parsed_list_name}] at position [{position}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_entry_deletion_error." + self._xparams.get("language")) % (parsed_list_name, str(position))
    
    def update_entry_from_list(self, list_name: str, entry_text: str, position: int) -> dict | str:
        '''
        Update an entry from a specific list.

        Args:
            list_name (str): The name of the list to update the entry from.
            entry_text (str): The new text for the entry to update.
            position (int): The position of the entry to update.

        Returns:
            dict | str: If successful, returns updated entry; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Updating an entry from list [{list_name}] at position [{position}]")

        # Try to come closer to the list name that the user provided, in case there is a small typo
        parsed_list_name = self._find_list_with_highest_similarity_name(list_name)
        self._log_debug(f"Parsed list name: [{parsed_list_name}] for input list name: {list_name}")
        if parsed_list_name is None:
            return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name

        try:
            updated_entry = self._lists.update_entry(
                list_name=parsed_list_name, 
                new_text=entry_text, 
                position=position)
            if updated_entry:
                return updated_entry
            else:
                return self._xconfig.get("language.lists.list_entry_update_error." + self._xparams.get("language")) % (parsed_list_name, str(position))
        except Exception as e:
            self._xlog.error(f"🛑 Error updating entry from list for [{parsed_list_name}] at position [{position}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_entry_update_error." + self._xparams.get("language")) % (parsed_list_name, str(position))
        
    def get_all_entries_from_list(self, list_name: str) -> dict | str:
        '''
        Get all entries from a specific list.

        Args:
            list_name (str): The name of the list to get the entries from.
        Returns:
            dict | str: If successful, returns a dict with the list details including all entries and the list name; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Getting all entries from list [{list_name}]")

        # Try to come closer to the list name that the user provided, in case there is a small typo
        parsed_list_name = self._find_list_with_highest_similarity_name(list_name)
        self._log_debug(f"Parsed list name: [{parsed_list_name}] for input list name: {list_name}")
        if parsed_list_name is None:
            return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name

        try:
            all_entries = self._lists.get_entries(parsed_list_name)
            if all_entries:
                return {
                    "entries": all_entries,
                    "list_name": parsed_list_name
                }
            else:
                return self._xconfig.get("language.lists.all_entries_retrieval_error." + self._xparams.get("language")) % parsed_list_name
        except Exception as e:
            self._xlog.error(f"🛑 Error getting all entries from list for [{parsed_list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_all_entries_retrieval_error." + self._xparams.get("language")) % parsed_list_name

    def get_one_entry_from_list(self, list_name: str, position: int) -> dict | str:
        '''
        Get an entry from a specific list.

        Args:
            list_name (str): The name of the list to get the entry from.
            position (int): The position of the entry to get.

        Returns:
            dict | str: If successful, returns a dict with the entry details; otherwise, an error message.
        '''
        self._xlog.info(f"📝 Request for Getting an entry from list [{list_name}] at position [{position}]")

        # Try to come closer to the list name that the user provided, in case there is a small typo
        parsed_list_name = self._find_list_with_highest_similarity_name(list_name)
        self._log_debug(f"Parsed list name: [{parsed_list_name}] for input list name: {list_name}")
        if parsed_list_name is None:
            return self._xconfig.get("language.lists.list_not_found." + self._xparams.get("language")) % list_name

        try:
            entry = self._lists.get_entry(parsed_list_name, position=position)
            if entry:
                return entry
            else:
                return self._xconfig.get("language.lists.entry_retrieval_error." + self._xparams.get("language")) % (parsed_list_name, str(position))
        except Exception as e:
            self._xlog.error(f"🛑 Error getting entry from list for [{parsed_list_name}] at position [{position}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.lists.list_entry_retrieval_error." + self._xparams.get("language")) % (parsed_list_name, str(position))

    def show_affected_list(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            log.debug(f"📝 Showing Affected List on Foreground display: {value}")

            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=value["description"] if isinstance(value, dict) and "description" in value else None,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG,
                header=value["name"] if isinstance(value, dict) and "name" in value else None,
                font_header_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE
        )
        except Exception as e:
            log.error(f"🛑 Error showing Affected List on Foreground display: {e}")
    
    def show_list_of_lists(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            log.debug(f"📝 Showing List of lists on Foreground display: {len(value)} entries")

            counter = 1
            lists_text = []
            for list in value:
                lists_text.append(f"{counter}. {list['name']}")
                counter += 1
            lists_text = "\n".join(lists_text)

            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=lists_text,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG,
                header=self._xconfig.get("language.lists.list_header." + self._xparams.get("language")),
                font_header_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE
        )
        except Exception as e:
            log.error(f"🛑 Error showing List of lists on Foreground display: {e}")
    
    def show_entries_for_list(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            log.debug(f"📝 Showing Entries for List on Foreground display: {value}")

            list_name = value["list_name"]
            entries = value["entries"] if isinstance(value, dict) and "entries" in value else []
            
            counter = 1
            entries_text = []
            for entry in entries:
                entries_text.append(f"{counter}. {entry['text']}")
                counter += 1
            entries_text = "\n".join(entries_text)

            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=entries_text,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_MEDIUM,
                header=list_name,
                font_header_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE
            )
        except Exception as e:
            log.error(f"🛑 Error showing Entries for List on Foreground display: {e}")
    
    def show_entries_for_list_with_highlight(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:

        try:
            log.debug(f"📝 Showing Entries for List after an single-entry action, on Foreground display: {value}")

            # so, independently of the entry we received, we want to show the list of entries,
            # but we want to highlight the entry that we received in the foreground display. 
            # Could be that the entry that we received no longer exists (e.g., after a deletion),
            # but we want to show the list of entries anyway, and if the entry exists, we want to highlight it.

            list_name = value["list_name"]
            highlighted_entry_text = value["text"] if isinstance(value, dict) and "text" in value else None
            all_entries = self._lists.get_entries(list_name)
            
            counter = 1
            entries_text = []
            for entry in all_entries:
                if entry["text"] == highlighted_entry_text:
                    entries_text.append(f"{counter}. {entry['text']}  <--")
                else:
                    entries_text.append(f"{counter}. {entry['text']}")
                counter += 1
            entries_text = "\n".join(entries_text)

            interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="📝",
                text=entries_text,
                font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_MEDIUM,
                header=list_name,
                font_header_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_HUGE
            )
        except Exception as e:
            log.error(f"🛑 Error showing Entries for List with highlight on Foreground display: {e}")

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
                self.update_entry_from_list,
                self.get_list,
                self.get_one_entry_from_list,
                self.get_all_entries_from_list]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "create_list" or \
            function_name == "delete_list" or \
            function_name == "update_list" or \
            function_name == "get_list":
            return self.show_affected_list
        elif function_name == "get_lists":
            return self.show_list_of_lists
        elif function_name == "add_entry_to_list" or \
            function_name == "delete_entry_from_list" or \
            function_name == "update_entry_from_list" or \
            function_name == "get_one_entry_from_list":
            return self.show_entries_for_list_with_highlight
        elif function_name == "get_all_entries_from_list":
            return self.show_entries_for_list
        return self.default_empty_callback
    
    def _find_list_with_highest_similarity_name(self, list_name: str) -> str | None:
        '''
        Finds the existing list name with the highest similarity to the given list name.  

        Args:
            list_name: The name of the list to find the most similar one to.

        Returns:
            The name of the most similar list or None if no lists are found.
        '''
        all_lists_names = [list_object["name"] for list_object in self._lists.get_lists().values()]
        highest_similarity = 0
        minimum_similarity_threshold = 0.7  # You can adjust this threshold as needed
        most_similar_list_name = None
        for existing_list_name in all_lists_names:
            similarity = self._calculate_similarity(list_name, existing_list_name)
            if similarity > highest_similarity:
                highest_similarity = similarity
                most_similar_list_name = existing_list_name
        if highest_similarity >= minimum_similarity_threshold:
            return most_similar_list_name
        return None
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        '''
        Calculates the similarity between two strings using a simple ratio of common characters.

        Args:
            str1: The first string to compare.
            str2: The second string to compare.

        Returns:
            A float representing the similarity between the two strings (between 0 and 1).
        '''
        set_str1 = set(str1.lower())
        set_str2 = set(str2.lower())
        common_characters = set_str1.intersection(set_str2)
        total_characters = set_str1.union(set_str2)
        if total_characters:
            similarity = len(common_characters) / len(total_characters)
            return similarity
        else:
            return 0.0

# 2026-02-24 16:22:16,637 [MainProcess  | MainThread  ] INFO     oscar        Reacting to a Chatbot answer:
# 	- Text: I have deleted the last entry, "extend the animation of thinking to the audio", from your "To Do Client" list.
# 	- Function Calls: ['delete_entry_from_list']
# 	- Code blocks: 0
# 2026-02-24 16:22:16,637 [MainProcess  | MainThread  ] DEBUG    oscar        ⚡️ Reacting to function call: delete_entry_from_list
# 2026-02-24 16:22:16,638 [MainProcess  | MainThread  ] DEBUG    oscar        📺 Executing callback with value: {'created at': '', 'created_at': '2026-02-24 09:28', 'list_name': 'To do client', 'text': 'extend the animation of thinking to the audio'}
# 2026-02-24 16:22:16,640 [MainProcess  | MainThread  ] DEBUG    oscar        Waiting for queue lcd_queue to empty. Has now: 0 elements.
# 2026-02-24 16:22:16,642 [MainProcess  | MainThread  ] DEBUG    oscar        The queue lcd_queue is empty now. I've sleept 0s.
# 2026-02-24 16:22:16,643 [MainProcess  | MainThread  ] DEBUG    oscar        Waiting for the process lcd_busy to idle. It's now: IDLE.
# 2026-02-24 16:22:16,644 [MainProcess  | MainThread  ] DEBUG    oscar        The process lcd_busy is idle now. I've slept 0s.
# 2026-02-24 16:22:16,645 [MainProcess  | MainThread  ] DEBUG    oscar        📝 Showing Entries for List after an single-entry action, on Foreground display: {'created at': '', 'created_at': '2026-02-24 09:28', 'list_name': 'To do client', 'text': 'extend the animation of thinking to the audio'}
# 2026-02-24 16:22:16,647 [MainProcess  | MainThread  ] DEBUG    oscar        📝 Retrieving entries for the list [To do client]
# 2026-02-24 16:22:16,649 [MainProcess  | MainThread  ] ERROR    oscar        🛑 No list found for [To do client]
# 2026-02-24 16:22:16,650 [MainProcess  | MainThread  ] ERROR    oscar        🛑 Error showing Entries for List with highlight on Foreground display: 'bool' object is not iterable
# 2026-02-24 16:22:16,652 [MainProcess  | MainThread  ] DEBUG    oscar        Waiting for queue lcd_queue to empty. Has now: 0 elements.
# 2026-02-24 16:22:16,653 [MainProcess  | MainThread  ] DEBUG    oscar        The queue lcd_queue is empty now. I've sleept 0s.