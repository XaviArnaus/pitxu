from pyxavi import Config, Dictionary, Storage, full_stack, dd
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.utils.string_similarity import StringSimilarity

import os

from google import genai
from google.genai import types
import json
import logging

class Memory(PyXavi):

    filename = "memory.yaml"
    summary_similarity_threshold = 0.8

    ENTRY_TEMPLATE = {
        "summary": "",
        "content": "",
        "created_at": ""
    }

    WORDS_TO_BAN_FROM_BUNCH_OF_WORDS_MATCHING = {"the", "a", "an", "this", "that", "these", "those", "it", "he", "she", "they", "we", "you"}

    state: Storage = None

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config, params: Dictionary):
        super().init_pyxavi(config=config, params=params)

        self.filename = os.path.join(
            self._xconfig.get("storage.path"),
            self._xconfig.get("memory.filename", self.filename)
        )
        self.summary_similarity_threshold = self._xconfig.get("memory.summary_similarity_threshold", self.summary_similarity_threshold) 

        self.state = self._state = Storage(filename=self.filename)
        if not self.state.key_exists("entries"):
            self.state.set("entries", [])
            self.state.write_file()
        
    def write_entry(self, summary: str, content: str) -> dict:

        if summary is None or content is None:
            raise ValueError("Summary and content cannot be None")

        entry = self.ENTRY_TEMPLATE.copy()
        entry["summary"] = summary
        entry["content"] = content
        entry["created_at"] = Xtime.now_str()

        entries = list(self.state.get("entries"))
        entries.append(entry)
        self.state.set("entries", entries)

        self.state.write_file()

        return entry
    
    def get_by_date(self, date_str: str) -> list:
        entries = list(self.state.get("entries"))
        date = Xtime.str_to_datetime(date_str).date()
        return [entry for entry in entries if Xtime.str_to_datetime(entry["created_at"]).date() == date]
    
    def get_by_datetime(self, datetime_str: str) -> list:
        entries = list(self.state.get("entries"))
        target_datetime = Xtime.str_to_datetime(datetime_str)
        return [entry for entry in entries if Xtime.str_to_datetime(entry["created_at"]) == target_datetime]
    
    def _match_bunch_of_words(self, summary: str, entries: list) -> list:
        requested_words = set(summary.lower().split())
        requested_words = requested_words - self.WORDS_TO_BAN_FROM_BUNCH_OF_WORDS_MATCHING
        found = []
        for entry in entries:
            entry_words = set(entry["summary"].lower().split())
            if requested_words.issubset(entry_words):
                found.append(entry)
        return found
    
    def get_by_summary_like(self, summary: str) -> dict | None:
        entries = list(self.state.get("entries"))

        # First approach: use string similarity to find the best match
        best_match = StringSimilarity.findBestMatch(summary.lower(), [entry["summary"].lower() for entry in entries])
        if best_match.bestMatch.rating >= self.summary_similarity_threshold:
            self._log_debug(f"Found a memory entry with summary similar enough to '{summary}'. Returning this entry as a match. Entry summary: '{best_match.bestMatch.target}', similarity: {best_match.bestMatch.rating:.2f}")
            return entries[best_match.bestMatchIndex]
        
        # Second approach: check if there is an entry that contains the words in the requestedsummary (ignoring common words), and if so, return that entry as a match, since it might be relevant even if the overall similarity is low.
        matches = self._match_bunch_of_words(summary, entries)
        if len(matches) == 1:
            # Only one match found, return it.
            self._log_debug(f"Found a memory entry with summary that contains all the words in '{summary}', even though the overall similarity is below the threshold. Returning this entry as a match. Entry summary: '{matches[0]['summary']}'")
            return matches[0]
        elif len(matches) > 1:
            # More than one, just get the best match, regardless of the similarity score, since they all contain the words in the requested summary.
            best_match = StringSimilarity.findBestMatch(summary.lower(), [entry["summary"].lower() for entry in matches])
            self._log_debug(f"Found multiple memory entries with summary that contains all the words in '{summary}'. Returning the best match. Entry summary: '{best_match.bestMatch.target}', similarity: {best_match.bestMatch.rating:.2f}")
            return matches[best_match.bestMatchIndex]
        
        # Still here, no match found.
        self._log_debug(f"No memory entry found with summary similar to '{summary}' or that contains all the words in '{summary}'. Returning None.")
        return None
    
    def get_last_entry(self) -> dict | None:
        entries = list(self.state.get("entries"))
        if entries:
            return entries[-1]
        else:
            return None
    
    def update_last_entry(self, summary: str = None, content: str = None) -> dict | None:
        entries = list(self.state.get("entries"))
        if not entries:
            return None
        
        last_entry = entries[-1]
        if summary is not None:
            last_entry["summary"] = summary
        if content is not None:
            last_entry["content"] = content
        
        self.state.set("entries", entries)
        self.state.write_file()

        return last_entry
    
    def summarize_chatbot_history_as_memory_entry(self, chatbot_history: list[dict]) -> dict | None:
        '''
        Summarizes the given chatbot history and returns a memory entry with the summary as the content.

        Args:
            chatbot_history (list[dict]): The history of the chatbot conversation, where each entry is a dictionary with "role" and "content".

        Returns:
            dict | None: The summarized memory entry or None if summarization fails.
        '''
        try:
            chatbot_history_str = json.dumps(chatbot_history)
            prompt = self._xconfig.get("memory.summary_prompt." + self._xparams.get("language")) % chatbot_history_str

            client = genai.Client(api_key=self._xparams.get("api_key"))
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                # config=types.GenerateContentConfig(
                #     system_instruction=instructions[self._xparams.get('language')],
                #     # system_instruction=instructions["en-us"],
                #     tools=tools
                # )
            )

            response_as_dict = None
            response_as_str = response.text.replace("```json", "").replace("```", "")
            self._xlog.debug(f"Summarization response: \n{response_as_str}")
            try:
                response_as_dict = json.loads(response_as_str)
            except json.JSONDecodeError:
                pass

            return response_as_dict

        except Exception as e:
            self._xlog.error(f"🛑 Error summarizing chatbot history as a memory entry: {e}")
            self._xlog.debug(full_stack())
            return None
