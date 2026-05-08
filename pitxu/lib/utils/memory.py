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
    # Not used, by now.
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
        entry["created_at"] = Xtime.current_time_str()

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
    
    def get_by_exact_summary(self, summary: str) -> dict | None:
        entries = list(self.state.get("entries"))
        for entry in entries:
            if entry["summary"].lower() == summary.lower():
                return entry
        return None
    
    def _match_bunch_of_words(self, summary: str, entries: list) -> list[dict]:
        requested_words = set(summary.lower().split())
        requested_words = requested_words - self.WORDS_TO_BAN_FROM_BUNCH_OF_WORDS_MATCHING
        found_fully = []
        found_partially = []
        for entry in entries:
            entry_words = set(entry["summary"].lower().split())
            entry_words = entry_words - self.WORDS_TO_BAN_FROM_BUNCH_OF_WORDS_MATCHING

            # First, check if all the words in the requested summary are present in the entry summary. No need to look further, then.
            if requested_words.issubset(entry_words):
                found_fully.append(entry)
                continue

            # Second, check if at least one of the words in the requested summary is present in the entry summary.
            if requested_words & entry_words:
                found_partially.append(entry)
        
        # Now return these lists, merging them discarding duplicated entries (those that are in found_fully should not be in found_partially, even if they match partially too).
        found_partially = [entry for entry in found_partially if entry not in found_fully]
        return found_fully + found_partially
    
    def get_by_summary_like(self, summary: str) -> list[dict] | None:
        entries = list(self.state.get("entries"))

        # 1st, get all summaries that contain the words in the requested summary, either fully (all the words) or partially (at least one of the words).
        # This is to reduce the number of comparisons we need to do with the string similarity, which is more expensive and also may not work well with long summaries.
        entries = self._match_bunch_of_words(summary, entries)
        self._log_debug(f"Found {len(entries)} entries that match the words in the requested summary '{summary}'.")

        # 2nd, rate the similarity of the summaries of these entries with the requested summary.
        rated_entries = StringSimilarity.compareAllAgainstOne(mainString=summary.lower(), targetStrings=[entry["summary"].lower() for entry in entries])
        self._log_debug(f"Rated the similarity of the summaries of the {len(entries)} entries with the requested summary '{summary}'. Ratings: {[f'{rated_entry.target}: {rated_entry.rating}' for rated_entry in rated_entries]}")

        # 3rd, sort the entries by similarity rating in descending order.
        rated_entries.sort(key=lambda x: x.rating, reverse=True)
        self._log_debug(f"Filtered and sorted the rated entries. Remaining entries: {[f'{rated_entry.target}: {rated_entry.rating}' for rated_entry in rated_entries]}")

        # 4th, Return the full entries that correspond to the rated entries already sorted by similarity.
        if rated_entries:
            return [self.get_by_exact_summary(rated_entry.target) for rated_entry in rated_entries]
        
        # Still here, no match found.
        self._log_debug(f"No memory entries found with summary similar to '{summary}' or that contains the words in '{summary}'. Returning None.")
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
