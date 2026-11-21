from pyxavi import Config, Dictionary, full_stack, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.utils.memory import Memory
from pitxu.lib.interaction.shortcuts.status import Status

import logging


class StatefulMemory(PyXavi, Command):

    _memory: Memory = None

    status_shortcuts: Status = None

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(StatefulMemory, self).init_pyxavi(config=config, params=params)

        self._memory = Memory(config=config, params=params)

        if self._xparams.key_exists("status_shortcuts"):
            self.status_shortcuts = self._xparams.get("status_shortcuts")
        else:
            raise ValueError("Missing 'status_shortcuts' parameter in StatefulMemory initialization.")

    def close(self):
        if self._memory is not None:
            self._memory.close()
        return super().close()

    def create_memory_entry(self, summary: str, content: str) -> dict | str:
        '''
        Create a new memory entry with the specified summary and content.

        Args:
            summary (str): The summary of the memory entry.
            content (str): The content of the memory entry.

        Returns:
            dict: The created memory entry or an error message.
        '''
        try:
            self._xlog.info(f"Ⓜ️ Request for Creating a new memory entry: {summary}")
            if self.status_shortcuts:
                self.status_shortcuts.add_new_status_line(f"🔧 Memory: New [{summary}]")
            created_entry = self._memory.create_short_memory_entry(summary, content)
            return created_entry

        except Exception as e:
            self._xlog.error(f"🛑 Error creating memory entry [{summary}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.memory.entry_creation_error." + self._xparams.get("language"))

    def get_memory_entries_by_summary(self, summary: str) -> list[dict] | str:
        '''
        Retrieve memory entries by summary.
    
        Args:
            summary (str): The summary of the memory entry to retrieve.

        Returns:
            list[dict] | str: If successful, returns a list of memory entries; otherwise, an error message.
        '''
        self._xlog.info(f"Ⓜ️ Request for Retrieving memory entries for [{summary}]")
        if self.status_shortcuts:
            self.status_shortcuts.add_new_status_line(f"🔧 Memory: Get all like [{summary}]")

        try:
            memory_entries = self._memory.get_short_memory_by_summary_like(summary)
            if memory_entries:
                return memory_entries
            else:
                return self._xconfig.get("language.memory.entries_not_found." + self._xparams.get("language")) % summary
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving memory entries for [{summary}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.memory.retrieval_error." + self._xparams.get("language"))
    
    def get_memory_entries_by_date(self, date: str) -> list[dict] | str:
        '''
        Retrieve all memory entries by date.

        Args:
            date (str): The date of the memory entries to retrieve in YYYY-MM-DD format.

        Returns:
            list[dict] | str: If successful, returns a list of memory entries; otherwise, an error message.
        '''
        self._xlog.info(f"Ⓜ️ Request for Retrieving memory entries for [{date}]")
        if self.status_shortcuts:
            self.status_shortcuts.add_new_status_line(f"🔧 Memory: Get all for [{date}]")

        try:
            memory_entries = self._memory.get_short_memory_by_date(date)
            if memory_entries:
                return memory_entries
            else:
                return self._xconfig.get("language.memory.entries_not_found." + self._xparams.get("language")) % date
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving memory entries for [{date}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.memory.retrieval_error." + self._xparams.get("language"))
    
    def get_memory_entry_by_id(self, entry_id: int) -> dict | str:
        '''
        Retrieve a memory entry by its ID.

        Args:
            entry_id (int): The ID of the memory entry to retrieve.

        Returns:
            dict | str: If successful, returns the memory entry; otherwise, an error message.
        '''
        self._xlog.info(f"Ⓜ️ Request for Retrieving memory entry with ID [{entry_id}]")
        if self.status_shortcuts:
            self.status_shortcuts.add_new_status_line(f"🔧 Memory: Get by ID [{entry_id}]")

        try:
            memory_entry = self._memory.get_short_memory_by_id(entry_id)
            if memory_entry:
                return memory_entry
            else:
                return self._xconfig.get("language.memory.entry_not_found." + self._xparams.get("language")) % entry_id
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving memory entry with ID [{entry_id}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.memory.retrieval_error." + self._xparams.get("language"))
    
    def get_last_five_memory_entries(self) -> list[dict] | str:
        '''
        Retrieve the last five memory entries.

        Returns:
            list[dict] | str: If successful, returns a list of the last five memory entries; otherwise, an error message.
        '''
        self._xlog.info(f"Ⓜ️ Request for Retrieving the last five memory entries")
        if self.status_shortcuts:
            self.status_shortcuts.add_new_status_line(f"🔧 Memory: Get last five entries")

        try:
            memory_entries = self._memory.get_last_short_memory_entries(limit=5)
            if memory_entries:
                return memory_entries
            else:
                return self._xconfig.get("language.memory.entries_not_found." + self._xparams.get("language")) % "last five entries"
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving the last five memory entries: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.memory.retrieval_error." + self._xparams.get("language"))
    
    def update_memory_entry_by_id(self, entry_id: int, summary: str = None, content: str = None) -> dict | str:
        '''
        Update a memory entry by its ID with the given summary and/or content.

        Args:
            entry_id (int): The ID of the memory entry to update.
            summary (str, optional): The new summary for the memory entry. Defaults to None.
            content (str, optional): The new content for the memory entry. Defaults to None.

        Returns:
            dict | str: The updated memory entry or an error message.
        '''
        self._xlog.info(f"Ⓜ️ Request for Updating memory entry with ID [{entry_id}] with summary [{summary}] and content [{content}]")
        if self.status_shortcuts:
            self.status_shortcuts.add_new_status_line(f"🔧 Memory: Update memory with ID [{entry_id}]")
        entry = self._memory.get_short_memory_by_id(entry_id)
        if entry is None:
            error = f"🛑 Memory entry with ID [{entry_id}] not found."
            self._xlog.error(error)
            return error
        
        if summary is None or content is None:
            error = f"⚠️ Memory entry with ID [{entry_id}] intended to be updated with summary [{summary}] and content [{content}]. One of the fields is None, so it will not be updated."
            self._xlog.warning(error)
            return error
        return self._memory.update_short_memory_entry_by_id(entry_id=entry_id, summary=summary, content=content)
    
    def update_last_memory_entry(self, summary: str = None, content: str = None) -> dict | None:
        '''
        Update the last memory entry with the given summary and/or content.
        It is useful when the user wants to correct or add information to the last memory entry created, which is usually the one related to the current chatbot conversation.

        Args:
            summary (str, optional): The new summary for the last memory entry. Defaults to None.
            content (str, optional): The new content for the last memory entry. Defaults to None.

        Returns:
            dict | None: The updated memory entry or None if there are no entries to update.
        '''
        self._xlog.info(f"Ⓜ️ Request for Updating the last memory entry with summary [{summary}] and content [{content}]")
        if self.status_shortcuts:
            self.status_shortcuts.add_new_status_line(f"🔧 Memory: Update last memory entry")
        try:
            updated_entry = self._memory.update_last_short_memory_entry(summary, content)
            if updated_entry:
                return updated_entry
            else:
                return None
        except Exception as e:
            self._xlog.error(f"🛑 Error updating the last memory entry: {e}")
            self._xlog.debug(full_stack())
            return None
    
    def remember_this_conversation(self) -> bool:
        '''
        Requests to remember the current conversation: it gets summarized and stored in the memory.
        Use it when the user asks to remember, save or keep what has been talked about in this conversation as a whole.
        Do not use it to remember one specific fact or piece of information: for that, create a memory entry.

        The application takes the conversation history by itself, there is nothing to pass.
        The summary is done in the background, so there is nothing to wait for nor to tell about its content.

        Returns:
            bool: True when the request was registered.
        '''
        self._xlog.info("Ⓜ️ Request for remembering the current conversation")
        if self.status_shortcuts:
            self.status_shortcuts.add_new_status_line("🔧 Memory: Remember this conversation")
        # The real work is done by the application when it reacts on this tool call (see Reactions),
        #   as it is the one that has the chatbot history.
        return True

    def callback_show_entry_on_foreground(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for functions that return entries, such as `get_memory_entry_by_summary` or `get_memory_entry_by_date`, that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `get_memory_entry_by_summary` or `get_memory_entry_by_date`.

        """
        try:
            summary = ""
            if isinstance(value, dict) and "summary" in value:
                summary = value["summary"]
            elif isinstance(value, list) and len(value) > 0:
                summary_pieces = []
                counter = 1
                for entry in value:
                    if isinstance(entry, dict) and "summary" in entry and "created_at" in entry:
                        date = entry.get("created_at", "").split("T")[0]  # Get only the date part
                        summary_pieces.append(f"{counter}. [{date}] {entry.get('summary', '')}")
                        counter += 1
                summary = "\n".join(summary_pieces)
            elif isinstance(value, str):
                log.error(f"🟠 Memory entry retrieval result is a string: {value}")
                interaction.show_error(text=value)
                return
            elif value is None:
                log.error(f"🟠 Memory entry retrieval result is None.")
                interaction.show_error(text="Memory entry not found")
                return
            else:
                dd(value)
                log.error(f"🛑 Memory entry retrieval result does not contain 'summary' to show on the Foreground.")
                interaction.show_error(text=value if isinstance(value, str) else "Unknown error")
                return

            interaction.show_text_block_on_foreground_while_speaking(text=summary)
            
        except Exception as e:
            log.error(f"🛑 Error showing the retrieved memory entry: {e}")
            log.error(full_stack())

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.create_memory_entry,
                self.get_memory_entries_by_summary,
                self.get_memory_entries_by_date,
                self.get_memory_entry_by_id,
                self.get_last_five_memory_entries,
                self.update_last_memory_entry,
                self.update_memory_entry_by_id,
                self.remember_this_conversation]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name in ["get_memory_entries_by_summary", "get_memory_entries_by_date", "create_memory_entry", "update_last_memory_entry", "update_memory_entry_by_id", "get_memory_entry_by_id", "get_last_five_memory_entries"]:
            return self.callback_show_entry_on_foreground
        return self.default_empty_callback