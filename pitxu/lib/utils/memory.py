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
import sqlite3
import threading
import time

class Memory(PyXavi):

    db: DbSqlite = None
    _long_term_writer: bool = False

    TABLE_SHORT_TIME_MEMORY = "short_time_memory"
    TABLE_LONG_TIME_MEMORY = "long_time_memory"
    TABLE_KNOWLEDGE_BASE = "knowledge_base"
    TABLE_PENDING_CONVERSATIONS = "pending_conversations"

    # What of an entry is returned to whoever asks for it.
    ENTRY_COLUMNS = "id, summary, content, created_at, language"
    ENTRY_COLUMNS_WITHOUT_LANGUAGE = "id, summary, content, created_at"

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

        # One thread at a time in the database connection of this object.
        self._lock = threading.RLock()

        # Only the nightly consolidation (and the preload) writes in the long term memory. Whoever asks for it
        #   says so with `long_term_writer`. Everyone else is refused by the database itself.
        self._long_term_writer = params.key_exists("long_term_writer") and bool(params.get("long_term_writer"))

        self.db = DbSqlite(config=self._xconfig, params=self._xparams)
        if not self._long_term_writer:
            self.db.protect_tables_from_writes([self.TABLE_LONG_TIME_MEMORY])
    
    # def reload_state(self):
    #     self.state = Storage(filename=self.filename)
    #     if not self.state.key_exists("entries"):
    #         self.state.set("entries", {})
    #         self.state.write_file()

    # ----- Short Term Memory API -----

    def create_short_memory_entry(self, summary: str, content: str, created_at: str = None, language: str = None, preload_key: str = None) -> dict:
        return self.create_memory_entry(table_name=self.TABLE_SHORT_TIME_MEMORY, summary=summary, content=content, created_at=created_at, language=language, preload_key=preload_key)

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
        entries = self.get_last_entries(table_name=self.TABLE_SHORT_TIME_MEMORY, limit=1)
        return entries[0] if entries else None

    def get_last_short_memory_entries(self, limit: int = 5) -> list[dict] | None:
        return self.get_last_entries(table_name=self.TABLE_SHORT_TIME_MEMORY, limit=limit)

    def update_short_memory_entry_by_id(self, entry_id: int, summary: str = None, content: str = None) -> dict | None:
        return self.update_by_id(table_name=self.TABLE_SHORT_TIME_MEMORY, entry_id=entry_id, summary=summary, content=content)

    def update_last_short_memory_entry(self, summary: str = None, content: str = None) -> dict | None:
        return self.update_last_entry(table_name=self.TABLE_SHORT_TIME_MEMORY, summary=summary, content=content)

    # ----- Long Term Memory API -----
    # Reading is the same generic API than the rest, with the long table.
    # Writing is only for the code that created this Memory with `long_term_writer` (the nightly consolidation,
    #   and the preload), as the database refuses it to any other (see __init__).

    def get_long_memory_by_preload_key(self, preload_key: str) -> list[dict]:
        """ The entries (one per language) that came from the preload entry with this key. """
        return self._fetch_entries(
            f"SELECT {self.ENTRY_COLUMNS}, topic_id FROM {self.TABLE_LONG_TIME_MEMORY} WHERE preload_key = ? ORDER BY id",
            (preload_key,))

    def create_long_memory_entry(self, summary: str, content: str, language: str, topic_id: int = None,
                                 source_short_ids: list[int] = None, preload_key: str = None, created_at: str = None) -> dict:
        """
        Creates the version in one language of a long term memory topic.
        Without topic_id it starts a new topic, whose id is the one of this first row.
        The rows of the other languages of the same topic go with the same topic_id.
        """
        if summary is None or content is None or not language:
            raise ValueError("Summary, content and language cannot be empty")

        now = Xtime.now().isoformat()
        with self._lock:
            cursor = self.db.connection.execute(
                f"INSERT INTO {self.TABLE_LONG_TIME_MEMORY} "
                "(summary, content, created_at, updated_at, language, topic_id, source_short_ids, preload_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (summary, content, created_at or now, now, language, topic_id,
                 json.dumps(source_short_ids) if source_short_ids is not None else None, preload_key))
            entry_id = int(cursor.lastrowid)
            if topic_id is None:
                topic_id = entry_id
                self.db.connection.execute(f"UPDATE {self.TABLE_LONG_TIME_MEMORY} SET topic_id = ? WHERE id = ?", (topic_id, entry_id))
            self.db.connection.commit()

        entry = self.get_by_id(self.TABLE_LONG_TIME_MEMORY, entry_id)
        entry["topic_id"] = topic_id
        return entry

    # ----- Pending conversations: raw histories that could not be summarized yet -----

    def create_pending_conversation(self, history: list[dict], language: str = None) -> int:
        """ Keeps the raw chat history, to be summarized later. Returns its id. """
        cursor = self._execute(
            f"INSERT INTO {self.TABLE_PENDING_CONVERSATIONS} (language, history_json, created_at) VALUES (?, ?, ?)",
            (language or self._session_language(), json.dumps(history, ensure_ascii=False, default=str), Xtime.now().isoformat()))
        return int(cursor.lastrowid)

    def get_pending_conversations(self) -> list[dict]:
        """ The pending conversations, oldest first, each one with its `history` already decoded. """
        pending = []
        for row in self._fetch_entries(f"SELECT id, language, history_json, attempts, created_at FROM {self.TABLE_PENDING_CONVERSATIONS} ORDER BY id"):
            row["history"] = json.loads(row.pop("history_json"))
            pending.append(row)
        return pending

    def increment_pending_conversation_attempts(self, pending_id: int):
        self._execute(f"UPDATE {self.TABLE_PENDING_CONVERSATIONS} SET attempts = attempts + 1 WHERE id = ?", (pending_id,))

    def delete_pending_conversation(self, pending_id: int):
        self._execute(f"DELETE FROM {self.TABLE_PENDING_CONVERSATIONS} WHERE id = ?", (pending_id,))

    # ----- Real Memory API, requires to specify the table -----

    def create_memory_entry(self, table_name: str, summary: str, content: str, created_at: str = None, language: str = None, preload_key: str = None) -> dict:

        if summary is None or content is None:
            raise ValueError("Summary and content cannot be None")

        if created_at is None:
            created_at = Xtime.now().isoformat()

        if table_name in (self.TABLE_SHORT_TIME_MEMORY, self.TABLE_LONG_TIME_MEMORY):
            # These carry the language of the entry: the one of the session, unless told otherwise.
            cursor = self._execute(
                f"INSERT INTO {table_name} (summary, content, created_at, language, preload_key) VALUES (?, ?, ?, ?, ?)",
                (summary, content, created_at, language or self._session_language(), preload_key))
        else:
            cursor = self._execute(f"INSERT INTO {table_name} (summary, content, created_at) VALUES (?, ?, ?)",
                (summary, content, created_at))

        return self.get_by_id(table_name, int(cursor.lastrowid))

    def get_by_date(self, table_name: str, date_str: str) -> list:
        # Convert the date string into a datetime in isoformat, that is what SQLite wants.
        date = Xtime.str_to_datetime(date_str, "%Y-%m-%d").date().isoformat()
        return self._fetch_entries(f"SELECT {self._columns_of(table_name)} FROM {table_name} WHERE DATE(created_at) = ? ORDER BY id", (date,))

    def get_by_datetime(self, table_name: str, datetime_str: str) -> list:
        target_datetime = Xtime.str_to_datetime(datetime_str).isoformat()
        return self._fetch_entries(f"SELECT {self._columns_of(table_name)} FROM {table_name} WHERE created_at = ?", (target_datetime,))

    def get_by_id(self, table_name: str, entry_id: int) -> dict | None:
        entries = self._fetch_entries(f"SELECT {self._columns_of(table_name)} FROM {table_name} WHERE id = ?", (entry_id,))
        return entries[0] if entries else None

    def get_by_exact_summary(self, table_name: str, summary: str) -> list[dict] | None:
        entries = self._fetch_entries(f"SELECT {self._columns_of(table_name)} FROM {table_name} WHERE LOWER(summary) = ?", (summary.lower(),))
        return entries if entries else None

    def get_by_summary_like(self, table_name: str, summary: str) -> list[dict] | None:
        entries = self._fetch_entries(f"SELECT {self._columns_of(table_name)} FROM {table_name} WHERE LOWER(summary) LIKE ?", ('%' + summary.lower() + '%',))
        return entries if entries else None

    def get_last_entries(self, table_name: str, limit: int = 1) -> list[dict] | None:
        # By id: the creation time is a string and it is not a safe way to order.
        entries = self._fetch_entries(f"SELECT {self._columns_of(table_name)} FROM {table_name} ORDER BY id DESC LIMIT ?", (limit,))
        return entries if entries else None

    def update_by_id(self, table_name: str, entry_id: int, summary: str = None, content: str = None) -> dict | None:
        entry = self.get_by_id(table_name, entry_id)
        if not entry:
            return None

        if summary is not None:
            entry["summary"] = summary
        if content is not None:
            entry["content"] = content

        self._execute(f"UPDATE {table_name} SET summary = ?, content = ? WHERE id = ?",
            (entry["summary"], entry["content"], entry_id))

        return self.get_by_id(table_name, entry_id)

    def update_last_entry(self, table_name: str, summary: str = None, content: str = None) -> dict | None:
        last_entries = self.get_last_entries(table_name, limit=1)
        if not last_entries:
            return None

        return self.update_by_id(table_name, last_entries[0]["id"], summary=summary, content=content)

    # ----- Database access: one place that serializes it and returns plain dicts -----

    def _session_language(self) -> str:
        """ The language of the current session. Without one (Maintenance) it is the default language of the app. """
        return self._xparams.get("language") or self._xconfig.get("app.default_language", "en")

    def _columns_of(self, table_name: str) -> str:
        """ What of an entry is returned. The language only exists in the short and long term tables. """
        if table_name in (self.TABLE_SHORT_TIME_MEMORY, self.TABLE_LONG_TIME_MEMORY):
            return self.ENTRY_COLUMNS
        return self.ENTRY_COLUMNS_WITHOUT_LANGUAGE

    def _fetch_entries(self, sql: str, args: tuple = ()) -> list[dict]:
        # A new cursor on every call: the shared one is not thread-safe.
        with self._lock:
            rows = self.db.connection.execute(sql, args).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def _execute(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self.db.connection.execute(sql, args)
            self.db.connection.commit()
        return cursor

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

    def backfill_legacy_language(self) -> int:
        """
        The entries from before the languages existed have none. They get the one in `memory.legacy_entries_language`.
        Run at startup, right after the migrations. Idempotent: only the entries without language are touched.

        The long term table is updated only if this Memory is a long term writer.

        Returns:
            int: The number of entries updated.
        """
        language = self._xconfig.get("memory.legacy_entries_language", "en")
        supported_languages = self._xconfig.get("app.supported_languages", [])
        if supported_languages and language not in supported_languages:
            self._xlog.error(f"🛑 memory.legacy_entries_language [{language}] is not one of the supported languages {supported_languages}.")
            return 0

        tables = [self.TABLE_SHORT_TIME_MEMORY] + ([self.TABLE_LONG_TIME_MEMORY] if self._long_term_writer else [])
        updated = 0
        for table in tables:
            updated += self._execute(f"UPDATE {table} SET language = ? WHERE language IS NULL", (language,)).rowcount
        if updated:
            self._xlog.info(f"🗄️ {updated} memory entries without language were set to [{language}].")
        return updated

    @staticmethod
    def _localized(value, default_language: str) -> dict[str, str]:
        """
        A preload field per language: `{en: "...", es: "..."}`.
        A plain string (the format before the languages) is taken as the default language.
        """
        if isinstance(value, dict):
            return {str(language): str(text) for language, text in value.items() if text}
        if isinstance(value, str) and value:
            return {default_language: value}
        return {}

    def preload_memory(self):
        """
        Preloads the long term memory with the entries in the `memory_preload.yaml` config file.
        This is useful to have some initial memory entries that can be used as context for the chatbot, without overloading the
        input prompt of the chatbot and keep some tokens.

        It is static configuration, not chat content, so it is written straight into the long term memory,
          in every language that the entry provides (the nightly consolidation completes the ones that are missing).
        Every entry has a `key`: an entry that is already there (by key and language) is not written again,
          so it is safe to leave the preload enabled.
        """
        if not self._xconfig.get("memory_preload.enabled", False):
            self._xlog.info("Memory preloading is disabled. Skipping preload.")
            return

        if not self._long_term_writer:
            raise PermissionError("Only a Memory created with long_term_writer can preload the long term memory")

        supported_languages = self._xconfig.get("app.supported_languages", [])
        legacy_language = self._xconfig.get("memory.legacy_entries_language", "en")

        for entry in self._xconfig.get("memory_preload.entries", []):
            key = entry.get("key")
            if not key:
                self._xlog.warning(f"🟠 Memory preload entry without `key` skipped: {entry.get('title')!r}")
                continue

            titles = self._localized(entry.get("title"), legacy_language)
            contents = self._localized(entry.get("content"), legacy_language)

            existing = self.get_long_memory_by_preload_key(key)
            existing_languages = {existing_entry["language"] for existing_entry in existing}
            topic_id = existing[0]["topic_id"] if existing else None

            for language, title in titles.items():
                if supported_languages and language not in supported_languages:
                    self._xlog.warning(f"🟠 Memory preload entry [{key}]: language [{language}] is not supported, skipping it.")
                    continue
                if language not in contents:
                    self._xlog.warning(f"🟠 Memory preload entry [{key}]: it has a title but no content in [{language}], skipping it.")
                    continue
                if language in existing_languages:
                    self._log_debug(f"Memory preload entry [{key}] in [{language}] already exists. Skipping.")
                    continue

                created = self.create_long_memory_entry(
                    summary=title, content=contents[language], language=language, topic_id=topic_id, preload_key=key)
                topic_id = created["topic_id"]
                self._xlog.info(f"Preloaded memory entry [{key}] in [{language}] with title '{title}'.")

    def close(self):
        self._xlog.info("Closing Memory")
        if self.db is not None:
            self.db.close()
        self._xlog.info("Memory closed")
