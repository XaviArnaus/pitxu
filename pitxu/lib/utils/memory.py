from pyxavi import Config, Dictionary, dd, full_stack
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.database.db_sqlite import DbSqlite

from google import genai
from google.genai.errors import ServerError

import os
import json
import logging

class Memory(PyXavi):

    db: DbSqlite = None

    TABLE_SHORT_TIME_MEMORY = "short_time_memory"
    TABLE_LONG_TIME_MEMORY = "long_time_memory"
    TABLE_KNOWLEDGE_BASE = "knowledge_base"

    RETRIES_ON_SUMMARIZATION_FAILURE = 3

    GENAI_LIB_LOG_LEVEL: int = logging.INFO
    HTTPCORE_LIB_LOG_LEVEL: int = logging.INFO

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config, params: Dictionary):
        super().init_pyxavi(config=config, params=params)

        # Set the log levels for the Gemini API client and httpcore libraries based on the configuration
        self.GENAI_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.gemini_chatbot.loglevel", self.GENAI_LIB_LOG_LEVEL)
        self.HTTPCORE_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.httpcore.loglevel", self.HTTPCORE_LIB_LOG_LEVEL)
        self._log_debug("Setting Gemini API client log level to: " + str(self.GENAI_LIB_LOG_LEVEL))
        logging.getLogger("google_genai").setLevel(self.GENAI_LIB_LOG_LEVEL)
        self._log_debug("Setting Httpcore client log level to: " + str(self.HTTPCORE_LIB_LOG_LEVEL))
        logging.getLogger("httpcore").setLevel(self.HTTPCORE_LIB_LOG_LEVEL)

        self.db = DbSqlite(config=self._xconfig, params=self._xparams)
    
    # def reload_state(self):
    #     self.state = Storage(filename=self.filename)
    #     if not self.state.key_exists("entries"):
    #         self.state.set("entries", {})
    #         self.state.write_file()

    # ----- Short Term Memory API -----

    def create_short_memory_entry(self, summary: str, content: str, created_at: str = None) -> dict:
        return self.create_memory_entry(table_name=self.TABLE_SHORT_TIME_MEMORY, summary=summary, content=content, created_at=created_at)
    
    def get_short_memory_by_date(self, date_str: str) -> list:
        return self.get_by_date(table_name=self.TABLE_SHORT_TIME_MEMORY, date_str=date_str)
    
    def get_short_memory_by_datetime(self, datetime_str: str) -> list:
        return self.get_by_datetime(table_name=self.TABLE_SHORT_TIME_MEMORY, datetime_str=datetime_str)
    
    def get_short_memory_by_id(self, entry_id: int) -> dict | None:
        return self.get_by_id(table_name=self.TABLE_SHORT_TIME_MEMORY, entry_id=entry_id)
    
    def get_short_memory_by_exact_summary(self, summary: str) -> list[dict] | None:
        return self.get_by_exact_summary(table_name=self.TABLE_SHORT_TIME_MEMORY, summary=summary)
    
    def get_short_memory_by_summary_like(self, summary: str) -> list[dict] | None:
        return self.get_by_summary_like(table_name=self.TABLE_SHORT_TIME_MEMORY, summary=summary)
    
    def get_last_short_memory_entry(self) -> dict | None:
        return self.get_last_entry(table_name=self.TABLE_SHORT_TIME_MEMORY)
    
    def update_short_memory_entry_by_id(self, entry_id: int, summary: str = None, content: str = None) -> dict | None:
        return self.update_by_id(table_name=self.TABLE_SHORT_TIME_MEMORY, entry_id=entry_id, summary=summary, content=content)
        
    def update_last_short_memory_entry(self, summary: str = None, content: str = None) -> dict | None:
        return self.update_last_entry(table_name=self.TABLE_SHORT_TIME_MEMORY, summary=summary, content=content)
    
    # ----- Real Memory API, requires to specify the table -----

    def create_memory_entry(self, table_name: str, summary: str, content: str, created_at: str = None) -> dict:

        if summary is None or content is None:
            raise ValueError("Summary and content cannot be None")
        
        if created_at is None:
            created_at = Xtime.now().isoformat()
        
        self.db.cursor.execute(f"INSERT INTO {table_name} (summary, content, created_at) VALUES (?, ?, ?)", 
            (summary, content, created_at))
        self.db.connection.commit()

        id = int(self.db.cursor.lastrowid)
        return self.get_by_id(table_name, id)
    
    def get_by_date(self, table_name: str, date_str: str) -> list:
        # Convert the date string into a datetime in isoformat, that is what SQLite wants.
        date = Xtime.str_to_datetime(date_str, "%Y-%m-%d").date().isoformat()
        self.db.cursor.execute(f"SELECT id, summary, content, created_at FROM {table_name} WHERE DATE(created_at) = ?", (date,))
        rows = self.db.cursor.fetchall()
        entries = []
        for row in rows:
            entry = {
                "id": row["id"],
                "summary": row["summary"],
                "content": row["content"],
                "created_at": row["created_at"]
            }
            entries.append(entry)
        return entries
    
    def get_by_datetime(self, table_name: str, datetime_str: str) -> list:
        target_datetime = Xtime.str_to_datetime(datetime_str).isoformat()
        self.db.cursor.execute(f"SELECT id, summary, content, created_at FROM {table_name} WHERE created_at = ?", (target_datetime,))
        rows = self.db.cursor.fetchall()
        entries = []
        for row in rows:
            entry = {
                "id": row["id"],
                "summary": row["summary"],
                "content": row["content"],
                "created_at": row["created_at"]
            }
            entries.append(entry)
        return entries
    
    def get_by_id(self, table_name: str, entry_id: int) -> dict | None:
        
        self.db.cursor.execute(f"SELECT id, summary, content, created_at FROM {table_name} WHERE id = ?", (entry_id,))
        row = self.db.cursor.fetchone()
        if row:
            entry = {
                "id": row["id"],
                "summary": row["summary"],
                "content": row["content"],
                "created_at": row["created_at"]
            }
            return entry
        return None
    
    def get_by_exact_summary(self, table_name: str, summary: str) -> list[dict] | None:
        self.db.cursor.execute(f"SELECT id, summary, content, created_at FROM {table_name} WHERE LOWER(summary) = ?", (summary.lower(),))
        rows = self.db.cursor.fetchall()
        entries = []
        for row in rows:
            entry = {
                "id": row["id"],
                "summary": row["summary"],
                "content": row["content"],
                "created_at": row["created_at"]
            }
            entries.append(entry)
        if entries:
            return entries
        return None
    
    def get_by_summary_like(self, table_name: str, summary: str) -> list[dict] | None:
        self.db.cursor.execute(f"SELECT id, summary, content, created_at FROM {table_name} WHERE LOWER(summary) LIKE ?", ('%' + summary.lower() + '%',))
        rows = self.db.cursor.fetchall()
        entries = []
        for row in rows:
            entry = {
                "id": row["id"],
                "summary": row["summary"],
                "content": row["content"],
                "created_at": row["created_at"]
            }
            entries.append(entry)
        if entries:
            return entries
        return None
    
    def get_last_entry(self, table_name: str) -> dict | None:
        self.db.cursor.execute(f"SELECT id, summary, content, created_at FROM {table_name} ORDER BY created_at DESC LIMIT 1")
        row = self.db.cursor.fetchone()
        if row:
            entry = {
                "id": row["id"],
                "summary": row["summary"],
                "content": row["content"],
                "created_at": row["created_at"]
            }
            return entry
        return None
    
    def update_by_id(self, table_name: str, entry_id: int, summary: str = None, content: str = None) -> dict | None:
        entry = self.get_by_id(table_name, entry_id)
        if not entry:
            return None
        
        if summary is not None:
            entry["summary"] = summary
        if content is not None:
            entry["content"] = content
        
        self.db.cursor.execute(f"UPDATE {table_name} SET summary = ?, content = ? WHERE id = ?", 
            (entry["summary"], entry["content"], entry_id))
        self.db.connection.commit()

        return self.get_by_id(table_name, entry_id)
    
    def update_last_entry(self, table_name: str, summary: str = None, content: str = None) -> dict | None:
        last_entry = self.get_last_entry(table_name)
        if not last_entry:
            return None
        
        if summary is not None:
            last_entry["summary"] = summary
        if content is not None:
            last_entry["content"] = content
        
        self.db.cursor.execute(f"UPDATE {table_name} SET summary = ?, content = ? WHERE id = ?", 
            (last_entry["summary"], last_entry["content"], last_entry["id"]))
        self.db.connection.commit()

        return self.get_by_id(table_name, last_entry["id"])

    def summarize_chatbot_history_as_memory_entry(self, chatbot_history: list[dict]) -> dict | None:
        '''
        Summarizes the given chatbot history and returns a memory entry with the summary as the content.

        Args:
            chatbot_history (list[dict]): The history of the chatbot conversation, where each entry is a dictionary with "role" and "content".

        Returns:
            dict | None: The summarized memory entry or None if summarization fails.
        '''
        original_retries = retries = self.RETRIES_ON_SUMMARIZATION_FAILURE
        try:
            chatbot_history_str = json.dumps(chatbot_history)
            prompt = self._xconfig.get("memory.summary_prompt." + self._xparams.get("language")) % chatbot_history_str

            retries = 1
            while retries <= original_retries:
                self._xlog.debug(f"Summarizing. Try #{retries} / {original_retries}")
                retries += 1

                try:
                    client = genai.Client(api_key=self._xparams.get("api_key"))
                    model = self._xconfig.get("memory.summarization_model", "gemini-2.5-flash")
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        # config=types.GenerateContentConfig(
                        #     system_instruction=instructions[self._xparams.get('language')],
                        #     # system_instruction=instructions["en-us"],
                        #     tools=tools
                        # )
                    )
                except ServerError as e:
                    self._xlog.error(f"🛑 Gemini Server error using [{model}] during summarization: [{e.code}] {e.message}")
                    response = None

                if response is not None:
                    self._log_debug("Summarization successful.")
                    break

            response_as_dict = None
            if response is not None:
                response_as_str = response.text.replace("```json", "").replace("```", "")
                self._xlog.debug(f"Summarization response: \n{response_as_str}")
            else:
                self._xlog.error("🛑 Summarization failed after " + str(original_retries) + " retries.")
                return None

            try:
                response_as_dict = json.loads(response_as_str)
            except json.JSONDecodeError:
                pass

            return response_as_dict

        except Exception as e:
            self._xlog.error(f"🛑 Error summarizing chatbot history as a memory entry: {e}")
            self._xlog.debug(full_stack())
            return None

    def preload_memory(self):
        """
        Preloads the memory persistance based on the entries in the `memory_preload.yaml` config file.
        This is useful to have some initial memory entries that can be used as context for the chatbot, without overloading the 
        input prompt of the chatbot and keep some tokens.
        """
        if not self._xconfig.get("memory_preload.enabled", False):
            self._xlog.info("Memory preloading is disabled. Skipping preload.")
            return

        preload_entries = self._xconfig.get("memory_preload.entries", [])
        for entry in preload_entries:
            # Avoid duplicates: if we already have an entry with the same title, we consider that we have already preloaded this entry, so we skip it. Otherwise, we write it in the memory.
            if self.get_short_memory_by_exact_summary(entry["title"]) is None:
                self.create_short_memory_entry(summary=entry["title"], content=entry["content"])
                self._xlog.info(f"Preloaded memory entry with title '{entry['title']}'.")
            else:
                self._xlog.warning(f"Memory entry with title '{entry['title']}' already exists. Skipping preload of this entry.")
    
    def close(self):
        self._xlog.info("Closing Memory")
        if self.db is not None:
            self.db.close()
        self._xlog.info("Memory closed")
