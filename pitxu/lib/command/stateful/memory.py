from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.utils.memory import Memory

from google import genai
from google.genai import types
import json
import logging


class StatefulMemory(PyXavi, Command):

    _memory: Memory = None

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(StatefulMemory, self).init_pyxavi(config=config, params=params)

        self._memory = Memory(config=config, params=params)

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
            created_entry = self._memory.write_entry(summary, content)
            return created_entry

        except Exception as e:
            self._xlog.error(f"🛑 Error creating memory entry [{summary}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.memory.entry_creation_error." + self._xparams.get("language"))

    def get_memory_entry_by_summary(self, summary: str) -> dict | str:
        '''
        Retrieve a specific memory entry by summary.

        Args:
            summary (str): The summary of the memory entry to retrieve.

        Returns:
            dict | str: If successful, returns a JSON with the memory entry details; otherwise, an error message.
        '''
        self._xlog.info(f"Ⓜ️ Request for Retrieving a memory entry for [{summary}]")

        try:
            memory_entry = self._memory.get_by_summary_like(summary)
            if memory_entry:
                return memory_entry
            else:
                return self._xconfig.get("language.memory.entry_not_found." + self._xparams.get("language")) % summary
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving memory entry for [{summary}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.memory.retrieval_error." + self._xparams.get("language"))
    
    def get_memory_entry_by_date(self, date: str) -> dict | str:
        '''
        Retrieve all memory entries by date.

        Args:
            date (str): The date of the memory entries to retrieve in YYYY-MM-DD format.

        Returns:
            dict | str: If successful, returns a JSON with the memory entry details; otherwise, an error message.
        '''
        self._xlog.info(f"Ⓜ️ Request for Retrieving memory entries for [{date}]")

        try:
            memory_entry = self._memory.get_by_date(date)
            if memory_entry:
                return memory_entry
            else:
                return self._xconfig.get("language.memory.entries_not_found." + self._xparams.get("language")) % date
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving memory entries for [{date}]: {e}")
            self._xlog.debug(full_stack())
            return self._xconfig.get("language.memory.retrieval_error." + self._xparams.get("language"))
    
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
            updated_entry = self._memory.update_last_entry(summary, content)
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
                    created_entry = self._memory.write_entry(summary, content)
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
                summary = "\n".join([entry.get("summary", "") for entry in value if isinstance(entry, dict) and "summary" in entry])
            elif value is None:
                log.error(f"🛑 Memory entry retrieval result is None.")
                interaction.show_error(text="Memory entry not found")
                return
            else:
                log.error(f"🛑 Memory entry retrieval result does not contain 'summary' to show on the Foreground.")
                interaction.show_error(text=value if isinstance(value, str) else "Unknown error")
                return

            interaction.show_arbitrary_text_on_foreground_while_speaking(
                        icon="Ⓜ️ ",
                        text=summary,
                        font_size=interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG)
            
        except Exception as e:
            log.error(f"🛑 Error showing the retrieved memory entry: {e}")
            log.error(full_stack())

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.create_memory_entry,
                self.get_memory_entry_by_summary,
                self.get_memory_entry_by_date,
                self.update_last_memory_entry,
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
        elif function_name in ["get_memory_entry_by_summary", "get_memory_entry_by_date", "create_memory_entry", "update_last_memory_entry"]:
            return self.callback_show_entry_on_foreground
        return self.default_empty_callback