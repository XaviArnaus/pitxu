from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.utils.memory import Memory


class Summarizer(PyXavi):

    memory: Memory = None

    def __init__(self, config: Config, params: Dictionary):
        super(Summarizer, self).init_pyxavi(config=config, params=params)

        self._xlog.info("🎤 Initializing Audio Summarizer for Chatbot Memory")

        self.memory = Memory(config=self._xconfig, params=self._xparams)
        
        self._log_debug("🎤 Done Initializing Audio Summarizer for Chatbot Memory")
    
    def close(self):
        self._xlog.info("🎤 Closing Audio Summarizer for Chatbot Memory")
        if self.memory is not None:
            self.memory.close()
        self._xlog.info("🎤 Audio Summarizer for Chatbot Memory closed")
    
    def summarize_and_store_in_memory(self, chatbot_history: list[dict], pending_id: int = None) -> None:
        """
        Args:
            chatbot_history (list[dict]): The conversation to summarize.
            pending_id (int): The in-flight pending conversation that the closing of the application wrote
                as a write-ahead copy of this same history. It is deleted when the summary is stored (or when there
                was nothing to remember), and released to the nightly consolidation when it could not be done.
        """
        try:
            self._summarize_and_store(chatbot_history, pending_id)
        except Exception:
            self._release_in_flight(pending_id)
            raise

    def _release_in_flight(self, pending_id: int = None):
        if pending_id is not None:
            self.memory.release_pending_conversation(pending_id)

    def _summarize_and_store(self, chatbot_history: list[dict], pending_id: int = None) -> None:

        self._log_debug(f"Chatbot history has: {len(chatbot_history)} entries. Summarizing it using LLM...")
        # Summarize the chatbot history into a memory entry, and write it into the memory if the summarization was successful.
        memory_entry = self.memory.summarize_chatbot_history_as_memory_entry(chatbot_history=chatbot_history)
        self._log_debug(f"Memory entry generated from chatbot history summary: {memory_entry}")

        if memory_entry is not None and memory_entry.get("significant") is False:
            # Not a failure: the conversation had nothing worth remembering.
            self._xlog.info("Chatbot history has nothing significant to remember, nothing written into memory.")
            if pending_id is not None:
                self.memory.delete_pending_conversation(pending_id)
        elif memory_entry is not None and memory_entry.get("summary") and memory_entry.get("content"):
            self.memory.create_short_memory_entry(summary=memory_entry["summary"], content=memory_entry["content"])
            self._xlog.info("Chatbot history summarized and written into memory.")
            if pending_id is not None:
                self.memory.delete_pending_conversation(pending_id)
        else:
            self._xlog.warning("Chatbot history could not be summarized into a valid memory entry.")
            if pending_id is not None:
                # The raw copy is already kept: it only has to be released, so the nightly consolidation takes it.
                self._release_in_flight(pending_id)
                self._xlog.info(f"The raw chatbot history stays as pending conversation #{pending_id} to be summarized later.")
                return
            if self._xconfig.get("memory.summarization.fallback_save_raw", True):
                # Don't lose it: the raw conversation is kept to be summarized later.
                try:
                    pending_id = self.memory.create_pending_conversation(history=chatbot_history, language=self._xparams.get("language"))
                    self._xlog.info(f"The raw chatbot history was kept as pending conversation #{pending_id} to be summarized later.")
                    return
                except Exception as e:
                    self._xlog.error(f"🛑 Could not keep the raw chatbot history: {e}")
            # do you get the reference to the movie "Blade Runner"?
            # https://en.wikipedia.org/wiki/Tears_in_rain_monologue
            self._xlog.debug("... all those moments will be lost in time, like tears in rain.")