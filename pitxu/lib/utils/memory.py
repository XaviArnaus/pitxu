from pyxavi import Config, Dictionary, Storage
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.utils.string_similarity import StringSimilarity

import os

class Memory(PyXavi):

    filename = "memory.yaml"
    summary_similarity_threshold = 0.8

    ENTRY_TEMPLATE = {
        "summary": "",
        "content": "",
        "created_at": ""
    }

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
    
    def get_by_summary_like(self, summary: str) -> dict | None:
        entries = list(self.state.get("entries"))
        best_match = StringSimilarity.findBestMatch(summary.lower(), [entry["summary"].lower() for entry in entries])
        if best_match.bestMatch.rating >= self.summary_similarity_threshold:
            return entries[best_match.bestMatchIndex]
        else:
            return None
