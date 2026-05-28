from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.memory import Memory


class Summarizer(PyXavi):

    memory: Memory = None

    def __init__(self, config: Config, params: Dictionary):
        super(Summarizer, self).init_pyxavi(config=config, params=params)

        self._xlog.info("🎤 Initializing Audio Summarizer for Chatbot Memory")

        self.memory = Memory(config=self._xconfig, params=self._xparams)
        
        self._log_debug("🎤 Done Initializing Audio Summarizer for Chatbot Memory")
    
    def summarize_and_store_in_memory(self, chatbot_history: list[dict]) -> None:

        self._log_debug(f"Chatbot history at exit has: {len(chatbot_history)} entries. Summarizing it using LLM...")
        # Summarize the chatbot history into a memory entry, and write it into the memory if the summarization was successful.
        memory_entry = self.memory.summarize_chatbot_history_as_memory_entry(chatbot_history=chatbot_history)
        self._log_debug(f"Memory entry generated from chatbot history summary: {memory_entry}")
        if memory_entry is not None and "summary" in memory_entry and "content" in memory_entry:
            self.memory.create_short_memory_entry(summary=memory_entry["summary"], content=memory_entry["content"])
            self._xlog.info("Chatbot history summarized and written into memory at exit.")
        else:
            self._xlog.warning("Chatbot history could not be summarized into a valid memory entry at exit.")
            # do you get the reference to the movie "Blade Runner"?
            # https://en.wikipedia.org/wiki/Tears_in_rain_monologue
            self._xlog.debug("... all those moments will be lost in time, like tears in rain.")