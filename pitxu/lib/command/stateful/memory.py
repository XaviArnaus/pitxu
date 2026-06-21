from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.utils.memory import Memory

import logging


class StatefulMemory(PyXavi, Command):

    _memory: Memory = None

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(StatefulMemory, self).init_pyxavi(config=config, params=params)

        self._memory = Memory(config=config, params=params)
    
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
    
    def summarize_chatbot_history_into_new_memory_entry(self, chatbot_history: list[dict]) -> dict | str:
        '''
        Summarizes the chatbot history and creates a memory entry with the summary as the content.

        Args:
            chatbot_history (list[dict]): The history of the chatbot conversation, where each entry is a dictionary with "role" and "content".

        Returns:
            dict | str: The created memory entry or an error message.
        '''
        # Apparently the prompt always comes in English, so no need to translate it.
        # Still, looking at the logs, it's not always the case.
        self._xlog.debug(f"Ⓜ️ Summarizing the current Chatbot history into a memory entry using language [{self._xparams.get('language')}]")

        try:
            response_as_dict = self._memory.summarize_chatbot_history_as_memory_entry(chatbot_history=chatbot_history)

            if response_as_dict is not None:
                summary = response_as_dict.get("summary", None)
                content = response_as_dict.get("content", None)

                if summary is not None and content is not None:
                    created_entry = self._memory.create_short_memory_entry(summary, content)
                    return created_entry
                else:
                    self._xlog.error(f"🛑 Error summarizing chatbot history into memory entry: The response JSON does not contain 'summary' or 'content' fields.")
                    return self._xconfig.get("language.memory.summarization_error_no_summary_fields." + self._xparams.get("language"))
            else:
                return self._xconfig.get("language.memory.summarization_error_invalid_json." + self._xparams.get("language"))
        except Exception as e:
            self._xlog.error(f"🛑 Error summarizing chatbot history into memory entry: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.memory.summarization_error." + self._xparams.get("language"))
    
    def callback_summarize_chatbot_history_into_new_memory_entry(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        Callback for `summarize_chatbot_history_into_new_memory_entry` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `summarize_chatbot_history_into_new_memory_entry`.

        """
        try:
            summary = "unknown"
            error = None
            if isinstance(value, dict):
                summary = value.get("summary", "unknown")
            elif isinstance(value, str):
                error = value

            if error is None:
                interaction.add_new_status_line("🔧 Tool: Chat history summarized into new Memory entry")
                interaction.show_arbitrary_text_on_foreground_while_speaking(
                            icon="Ⓜ️ ",
                            text=summary,
                            font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
            else:
                log.error(f"🛑 Summarization result does not contain a summary to show on the Foreground.")
                interaction.show_error(text=error)
        except Exception as e:
            log.error(f"🛑 Error showing the Chatbot summarization result: {e}")
            log.error(full_stack())
    
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
                        summary_pieces.append(f"{counter}. [{date}] {entry.get("summary", "")}")
                        counter += 1
                summary = "\n".join(summary_pieces)
            elif value is None:
                log.error(f"🟠 Memory entry retrieval result is None.")
                interaction.show_error(text="Memory entry not found")
                return
            else:
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
                self.summarize_chatbot_history_into_new_memory_entry]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "summarize_chatbot_history_into_new_memory_entry":
            return self.callback_summarize_chatbot_history_into_new_memory_entry
        elif function_name in ["get_memory_entries_by_summary", "get_memory_entries_by_date", "create_memory_entry", "update_last_memory_entry", "update_memory_entry_by_id", "get_memory_entry_by_id", "get_last_five_memory_entries"]:
            return self.callback_show_entry_on_foreground
        return self.default_empty_callback