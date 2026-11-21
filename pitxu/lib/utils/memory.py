from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.database.db_sqlite import DbSqlite

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

import json
import logging
import re
import time

class Memory(PyXavi):

    db: DbSqlite = None

    TABLE_SHORT_TIME_MEMORY = "short_time_memory"
    TABLE_LONG_TIME_MEMORY = "long_time_memory"
    TABLE_KNOWLEDGE_BASE = "knowledge_base"

    # Defaults of the summarization, overridable in `memory.summarization.*` of the config.
    SUMMARIZATION_RETRIES = 3
    SUMMARIZATION_BACKOFF_SECONDS = 2
    SUMMARIZATION_REQUEST_TIMEOUT_SECONDS = 20
    SUMMARIZATION_MAX_TOTAL_SECONDS = 40
    # The column is VARCHAR(255), that SQLite does not enforce.
    SUMMARY_MAX_LENGTH = 255

    GENAI_LIB_LOG_LEVEL: int = logging.INFO
    HTTPCORE_LIB_LOG_LEVEL: int = logging.INFO

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config, params: Dictionary):
        super().init_pyxavi(config=config, params=params)

        if not params.key_exists("api_key"):
            raise ValueError("No API KEY received from params")

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
        return self.get_last_entries(table_name=self.TABLE_SHORT_TIME_MEMORY, limit=1)[0]
    
    def get_last_short_memory_entries(self, limit: int = 5) -> list[dict] | None:
        return self.get_last_entries(table_name=self.TABLE_SHORT_TIME_MEMORY, limit=limit)
    
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
    
    def get_last_entries(self, table_name: str, limit: int = 1) -> list[dict] | None:
        self.db.cursor.execute(f"SELECT id, summary, content, created_at FROM {table_name} ORDER BY created_at DESC LIMIT ?", (limit,))
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
        last_entries = self.get_last_entries(table_name, limit=1)
        if not last_entries:
            return None
        
        last_entry = last_entries[0]
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
        Summarizes the given chatbot history into a memory entry, using an external LLM.

        Args:
            chatbot_history (list[dict]): The history of the chatbot conversation, as a list of dictionaries.

        Returns:
            dict | None:
                - `{"significant": True, "summary": str, "content": str}` when there is something worth remembering.
                - `{"significant": False}` when the conversation has nothing worth storing. It is not an error.
                - `None` when the summarization failed (no key, LLM error, unusable answer).
        '''
        try:
            api_key = self._xparams.get("api_key")
            if not api_key:
                self._xlog.error("🛑 Cannot summarize the chatbot history: there is no API key.")
                return None

            prompt = self._build_summarization_prompt(chatbot_history)

            response_text = self._request_summarization(prompt=prompt, api_key=api_key)
            if response_text is None:
                return None
            self._xlog.debug(f"Summarization response: \n{response_text}")

            return self._parse_summarization_response(response_text)

        except Exception as e:
            self._xlog.error(f"🛑 Error summarizing chatbot history as a memory entry: {e}")
            self._xlog.debug(full_stack())
            return None

    def _build_summarization_prompt(self, chatbot_history: list[dict]) -> str:
        """
        The prompt of the configured language, with the history in it and (if configured) the current date,
        needed to turn "tomorrow" or "next Monday" into absolute dates.
        """
        language = self._xparams.get("language")
        template = self._xconfig.get("memory.summary_prompt." + str(language))
        if not template:
            raise ValueError(f"There is no summary prompt for the language [{language}] in memory.summary_prompt")

        # ensure_ascii=False: keep the accents as they are. default=str: whatever is not serializable (function args).
        chatbot_history_str = json.dumps(chatbot_history, ensure_ascii=False, default=str)
        # A plain replace instead of `%`: a % in the template or in the history can't break it.
        prompt = template.replace("%s", chatbot_history_str, 1)

        if self._xconfig.get("memory.summarization.include_current_date", True):
            now = Xtime.now()
            prompt = f"Current date and time: {now.strftime('%A %Y-%m-%d %H:%M')} ({now.astimezone().tzname()})\n\n" + prompt

        return prompt

    def _request_summarization(self, prompt: str, api_key: str) -> str | None:
        """
        Asks the LLM for the summary, as JSON. Retries (with exponential backoff, within an overall time budget)
        when the problem may be temporary: server errors, quota (429) and network errors.
        Returns the text of the answer, or None if it failed.
        """
        retries = int(self._xconfig.get("memory.summarization.retries", self.SUMMARIZATION_RETRIES))
        backoff_seconds = float(self._xconfig.get("memory.summarization.backoff_seconds", self.SUMMARIZATION_BACKOFF_SECONDS))
        request_timeout = float(self._xconfig.get("memory.summarization.request_timeout_seconds", self.SUMMARIZATION_REQUEST_TIMEOUT_SECONDS))
        max_total_seconds = float(self._xconfig.get("memory.summarization.max_total_seconds", self.SUMMARIZATION_MAX_TOTAL_SECONDS))
        model = self._xconfig.get("memory.summarization_model", "gemini-2.5-flash")

        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(request_timeout * 1000)))
        generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=self._summarization_response_schema())

        started_at = time.monotonic()
        for attempt in range(1, retries + 1):
            self._xlog.debug(f"Summarizing. Try #{attempt} / {retries}")

            # Only the request is inside the try: a bug in our own code must not look like a network problem to retry.
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=generation_config)
            except ServerError as e:
                problem = f"Server error [{e.code}] {e.message}"
            except ClientError as e:
                if e.code != 429:
                    # Bad key, bad request...: it will not get better by trying again.
                    self._xlog.error(f"🛑 Client error using [{model}] during summarization, not retrying: [{e.code}] {e.message}")
                    return None
                problem = f"Quota exceeded [{e.code}] {e.message}"
            except Exception as e:
                # Network errors and timeouts.
                problem = f"{type(e).__name__}: {e}"
            else:
                if response.text:
                    self._log_debug("Summarization successful.")
                    return response.text
                # Nothing to read: blocked or empty. Asking again would give the same.
                finish_reason = response.candidates[0].finish_reason if response.candidates else "no candidates"
                self._xlog.error(f"🛑 The summarization of [{model}] has no text. Finish reason: {finish_reason}")
                return None

            self._xlog.warning(f"🟠 Summarization try #{attempt} / {retries} failed using [{model}]: {problem}")

            if attempt >= retries:
                break
            wait_seconds = backoff_seconds * (2 ** (attempt - 1))
            if time.monotonic() - started_at + wait_seconds >= max_total_seconds:
                self._xlog.warning(f"🟠 Not retrying the summarization: the {max_total_seconds}s budget would be exceeded.")
                break
            time.sleep(wait_seconds)

        self._xlog.error(f"🛑 Summarization failed after {attempt} tries.")
        return None

    @staticmethod
    def _summarization_response_schema() -> types.Schema:
        """ `significant` is optional on purpose: a missing one counts as significant. """
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "significant": types.Schema(type=types.Type.BOOLEAN),
                "summary": types.Schema(type=types.Type.STRING),
                "content": types.Schema(type=types.Type.STRING),
            })

    def _parse_summarization_response(self, response_text: str) -> dict | None:
        """
        Turns the answer of the LLM into the result described in summarize_chatbot_history_as_memory_entry().
        It is tolerant: the JSON mode should give plain JSON, but if there are fences or text around it, it is extracted.
        """
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response_text.strip())

        data = None
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            found = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if found:
                try:
                    data = json.loads(found.group(0))
                except json.JSONDecodeError:
                    pass

        if not isinstance(data, dict):
            self._xlog.error(f"🛑 The summarization response is not a valid JSON object: {response_text[:500]!r}")
            return None

        summary = data.get("summary")
        content = data.get("content")
        summary = summary.strip() if isinstance(summary, str) else ""
        content = content.strip() if isinstance(content, str) else ""

        # Explicitly not significant, or nothing produced at all: there is nothing to store, and that's fine.
        if str(data.get("significant", True)).lower() == "false" or (summary == "" and content == ""):
            self._xlog.info("🧠 The conversation has nothing significant to store in the memory.")
            return {"significant": False}

        if summary == "" or content == "":
            self._xlog.error(f"🛑 The summarization response misses the summary or the content: {response_text[:500]!r}")
            return None

        return {"significant": True, "summary": summary[:self.SUMMARY_MAX_LENGTH], "content": content}

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
