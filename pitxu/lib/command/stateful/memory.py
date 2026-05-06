from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.utils.memory import Memory


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
            self._xlog.info(f"📝 Request for Creating a new memory entry: {summary}")
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
        self._xlog.info(f"📝 Request for Retrieving a memory entry for [{summary}]")

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
        self._xlog.info(f"📝 Request for Retrieving memory entries for [{date}]")

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

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.create_memory_entry,
                self.get_memory_entry_by_summary,
                self.get_memory_entry_by_date]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        return self.default_empty_callback