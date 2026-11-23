from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.database.db_sqlite import DbSqlite
from pitxu.lib.utils.xtime import Xtime

from datetime import datetime  # Only for the type hints: the time is handled through Xtime.
import os
import sqlite3
import threading
import yaml


class Reminders(PyXavi, Command):
    """
    The reminders, in the `reminders` table of the database.

    A reminder is identified by its id (like the memory entries), so several can share the same date and time.
    Its date and time are stored together in `due_at` as local time ("YYYY-MM-DD HH:MM"), and what is pending is
    what has no `announced_at`. Whoever announces a reminder asks `get_due()` and tells `mark_announced()`, so a
    reminder is never lost because a tick was skipped, and never announced twice.

    Everything it gives is a dict: {"id", "date", "time", "text", "announced"}.
    """

    TABLE = "reminders"

    FORMAT_DATE = "%Y-%m-%d"  # E.g., 2023-12-25
    FORMAT_TIME = "%H:%M"     # E.g., 14:30
    FORMAT_DUE = "%Y-%m-%d %H:%M"

    # The file where the reminders were before they were in the database. See `import_legacy_yaml()`.
    LEGACY_FILENAME = "reminders.yaml"

    COLUMNS = "id, due_at, text, language, announced_at"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Reminders, self).init_pyxavi(config=config, params=params)

        # One thread at a time in the database connection of this object.
        self._lock = threading.RLock()
        self.db = DbSqlite(config=self._xconfig, params=self._xparams)

    def close(self):
        self.db.close()

    # ----- Writing -----

    def create_reminder(self, date: str, time: str, reminder_text: str, language: str = None) -> dict:
        '''
        Creates a reminder. There can be several for the same date and time.

        Args:
            date: The date for the reminder in Year-Month-Day format.
            time: The time for the reminder in HH:MM format.
            reminder_text: The text of the reminder.
            language: The language of the reminder. Default: the one of the session.

        Returns:
            The reminder created.
        '''
        due_at = f"{date} {time}"
        self._log_debug(f"📝 Creating a reminder for [{due_at}]: {reminder_text}")
        cursor = self._execute(
            f"INSERT INTO {self.TABLE} (due_at, text, language) VALUES (?, ?, ?)",
            (due_at, reminder_text, language or self._xparams.get("language")))
        reminder = self.get_reminder(int(cursor.lastrowid))
        self._xlog.info(f"📝 Reminder [{reminder['id']}] set for [{due_at}]: {reminder_text}")
        return reminder

    def update_reminder(self, reminder_id: int, new_text: str) -> dict | bool:
        '''
        Changes the text of a reminder.

        Returns:
            The reminder updated, or False if there is none with that id.
        '''
        self._log_debug(f"📝 Updating the reminder [{reminder_id}] to: {new_text}")
        cursor = self._execute(f"UPDATE {self.TABLE} SET text = ? WHERE id = ?", (new_text, reminder_id))
        if cursor.rowcount == 0:
            self._log_debug(f"📝 No reminder found with the id [{reminder_id}]")
            return False
        return self.get_reminder(reminder_id)

    def move_reminder(self, reminder_id: int, new_date: str, new_time: str) -> dict | bool:
        '''
        Moves a reminder to a new date and time. If it was already announced, it is pending again (a snooze).

        Returns:
            The reminder moved, with `previous_date` and `previous_time`, or False if there is none with that id.
        '''
        self._log_debug(f"📝 Moving the reminder [{reminder_id}] to [{new_date}] at [{new_time}]")
        with self._lock:
            before = self.get_reminder(reminder_id)
            if not before:
                self._log_debug(f"📝 No reminder found with the id [{reminder_id}]")
                return False
            self._execute(f"UPDATE {self.TABLE} SET due_at = ?, announced_at = NULL WHERE id = ?",
                          (f"{new_date} {new_time}", reminder_id))
            moved = self.get_reminder(reminder_id)
        moved["previous_date"] = before["date"]
        moved["previous_time"] = before["time"]
        self._xlog.info(f"📝 Reminder [{reminder_id}] moved from [{before['date']} {before['time']}] to [{new_date} {new_time}]")
        return moved

    def delete_reminder(self, reminder_id: int) -> dict | bool:
        '''
        Deletes a reminder.

        Returns:
            The reminder deleted, or False if there is none with that id.
        '''
        self._log_debug(f"📝 Deleting the reminder [{reminder_id}]")
        with self._lock:
            reminder = self.get_reminder(reminder_id)
            if not reminder:
                self._log_debug(f"📝 No reminder found with the id [{reminder_id}]")
                return False
            self._execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (reminder_id,))
        self._xlog.info(f"📝 Reminder [{reminder_id}] deleted")
        return reminder

    # ----- Reading -----

    def get_reminder(self, reminder_id: int) -> dict | bool:
        '''
        Gets a reminder, announced or not.

        Returns:
            The reminder, or False if there is none with that id.
        '''
        reminders = self._fetch(f"SELECT {self.COLUMNS} FROM {self.TABLE} WHERE id = ?", (reminder_id,))
        return reminders[0] if reminders else False

    def get_reminders_for_date(self, date: str) -> list[dict]:
        '''
        Gets the reminders still pending for a date, in time order.
        '''
        self._log_debug(f"📝 Retrieving the pending reminders for [{date}]")
        return self._fetch(
            f"SELECT {self.COLUMNS} FROM {self.TABLE} WHERE announced_at IS NULL AND due_at >= ? AND due_at < ? ORDER BY due_at, id",
            (f"{date} 00:00", f"{date} 99:99"))

    def get_due(self, now: datetime = None) -> list[dict]:
        '''
        Gets the pending reminders whose time has come, the oldest first. Includes the ones that should have been
        announced before (the application was off, busy...).

        Unlike the other methods, it never raises: a problem is logged and it gives an empty list. It is called by
        background jobs (the minute tasks) that have nobody to answer to, and a database problem must not stop them.
        The other methods raise, because the tools that call them catch it and answer the chatbot with an error message.
        The limit is that a problem with the database is only seen in the log.

        Args:
            now: The moment to compare with. Default: now.
        '''
        try:
            now = now or Xtime.now()
            return self._fetch(
                f"SELECT {self.COLUMNS} FROM {self.TABLE} WHERE announced_at IS NULL AND due_at <= ? ORDER BY due_at, id",
                (Xtime.datetime_to_str(now, self.FORMAT_DUE),))
        except Exception as e:
            self._xlog.error(f"🛑 Could not get the due reminders: {e}")
            return []

    # ----- Announcing and cleaning -----

    # Defaults of the announcement, overridable in `reminders.*` of the config.
    LATE_AFTER_MINUTES = 2
    VERY_OLD_AFTER_HOURS = 24

    # What starts the turn that the chatbot history gets when reminders are announced. It is not the user speaking:
    #   whoever reads the history (the conversation summary) recognizes it by this, in any language.
    HISTORY_NOTICE_MARKER = "[SYSTEM NOTICE]"

    def build_announcement(self, reminders: list[dict], now: datetime = None) -> dict:
        '''
        The words of the announcement of the reminders that are due, in the language of the session:
        the same text to speak and to show, for one or for several (a list).

        A reminder that is late (`reminders.late_after_minutes`) says when it was for, and one that is very old
        (`reminders.very_old_after_hours`) says it with the date and a warning that it could not be announced back then.

        Args:
            reminders: The reminders to announce, as `get_due()` gives them.
            now: The moment to compare with. Default: now.

        Returns:
            dict: {"spoken": str, "screen": str, "count": int, "ids": list[int], "texts": list[str]}
        '''
        now = now or Xtime.now()
        late_after = float(self._xconfig.get("reminders.late_after_minutes", self.LATE_AFTER_MINUTES)) * 60
        very_old_after = float(self._xconfig.get("reminders.very_old_after_hours", self.VERY_OLD_AFTER_HOURS)) * 3600

        shown, spoken = [], []
        for reminder in reminders:
            due = Xtime.str_to_datetime(f"{reminder['date']} {reminder['time']}", self.FORMAT_DUE)
            late_by = Xtime.seconds_between(due, now)
            if late_by > very_old_after:
                item = self._message("reminder_item_late_other_day") % (reminder["date"], reminder["time"], reminder["text"])
                shown.append(item)
                spoken.append(f"{self._sentence(item)} {self._message('reminder_very_old_warning')}")
            elif late_by > late_after:
                if due.date() == now.date():
                    item = self._message("reminder_item_late_today") % (reminder["time"], reminder["text"])
                else:
                    item = self._message("reminder_item_late_other_day") % (reminder["date"], reminder["time"], reminder["text"])
                shown.append(item)
                spoken.append(self._sentence(item))
            else:
                shown.append(reminder["text"])
                spoken.append(self._sentence(reminder["text"]))

        if len(reminders) == 1:
            return {"spoken": self._message("reminder_announcement") % spoken[0], "screen": shown[0],
                    "count": 1, "ids": [reminders[0]["id"]], "texts": [reminders[0]["text"]]}
        return {"spoken": self._message("reminder_announcement_multiple") % (len(reminders), " ".join(spoken)),
                "screen": "\n".join(f"• {item}" for item in shown),
                "count": len(reminders), "ids": [reminder["id"] for reminder in reminders],
                "texts": [reminder["text"] for reminder in reminders]}

    def build_history_notice(self, announcement: dict) -> str:
        '''
        The user turn that the chatbot history gets when the reminders are announced: a system notice, not the user.
        It tells the ids, so the chatbot can move or delete them if the user asks later. The spoken announcement
        is the model turn that follows.
        '''
        ids = ", ".join(str(reminder_id) for reminder_id in announcement["ids"])
        return f"{self.HISTORY_NOTICE_MARKER} " + self._message("reminder_history_notice") % ids

    def build_memory_entry(self, announcement: dict, announced_at: datetime = None) -> tuple[str, str]:
        '''
        The short term memory entry of an announcement, so Pitxu remembers that it reminded the user even if
        the user did not say anything afterwards: ("summary", "content"), in the language of the session.
        '''
        announced_at = Xtime.datetime_to_str(announced_at or Xtime.now(), self.FORMAT_DUE)
        if announcement["count"] == 1:
            summary = self._message("reminder_memory_summary_one") % announcement["texts"][0]
        else:
            summary = self._message("reminder_memory_summary_many") % announcement["count"]
        ids = ", ".join(str(reminder_id) for reminder_id in announcement["ids"])
        return summary, self._message("reminder_memory_content") % (announced_at, announcement["spoken"], ids)

    def _message(self, key: str) -> str:
        """ The message `language.reminders.<key>` in the current language. """
        return self._xconfig.get("language.reminders." + key + "." + self._xparams.get("language"))

    @staticmethod
    def _sentence(text: str) -> str:
        """ The text as a sentence, so several can be spoken one after the other. """
        text = text.strip()
        return text if text == "" or text[-1] in ".!?" else text + "."

    def mark_announced(self, reminder_ids: list[int], announced_at: datetime = None) -> int:
        '''
        Tells that these reminders were announced, so they are not pending anymore.

        Returns:
            How many reminders were marked.
        '''
        if not reminder_ids:
            return 0
        announced_at = Xtime.datetime_to_str(announced_at or Xtime.now())
        marked = 0
        with self._lock:
            for reminder_id in reminder_ids:
                cursor = self._execute(
                    f"UPDATE {self.TABLE} SET announced_at = ? WHERE id = ? AND announced_at IS NULL",
                    (announced_at, reminder_id))
                marked += cursor.rowcount
        return marked

    def prune_announced(self, older_than_days: int, now: datetime = None) -> int:
        '''
        Deletes the reminders that were announced more than the given days ago.

        Returns:
            How many reminders were deleted.
        '''
        limit = Xtime.datetime_to_str(Xtime.add_time(now or Xtime.now(), days=-older_than_days))
        cursor = self._execute(
            f"DELETE FROM {self.TABLE} WHERE announced_at IS NOT NULL AND announced_at < ?", (limit,))
        self._xlog.info(f"📝 Pruned {cursor.rowcount} reminders announced more than {older_than_days} days ago")
        return cursor.rowcount

    # ----- The file that was before the database -----

    def import_legacy_yaml(self, path: str = None) -> dict:
        '''
        Moves the reminders of the old `reminders.yaml` into the database, and deletes the file once ALL of them
        are there. If anything is wrong the file stays untouched and the next start tries again (what was already
        imported is not imported twice).

        The old file had `date: {HH-MM: text}`. Every entry is imported, also the ones in the past: they are
        announced as late reminders.

        Args:
            path: The file. Default: the one in the storage path.

        Returns:
            dict: {"found": bool, "entries": int, "imported": int, "already_there": int, "invalid": list, "file_deleted": bool}
        '''
        path = path or os.path.join(self._xconfig.get("storage.path"), self.LEGACY_FILENAME)
        stats = {"found": os.path.exists(path), "entries": 0, "imported": 0, "already_there": 0, "invalid": [], "file_deleted": False}
        if not stats["found"]:
            return stats

        with open(path, encoding="utf-8") as stream:
            content = yaml.safe_load(stream) or {}

        entries, stats["invalid"] = self._legacy_entries(content)
        stats["entries"] = len(entries)

        with self._lock:
            try:
                for due_at, text in entries:
                    already = self._fetch(f"SELECT id FROM {self.TABLE} WHERE due_at = ? AND text = ?", (due_at, text))
                    if already:
                        stats["already_there"] += 1
                        continue
                    self.db.connection.execute(
                        f"INSERT INTO {self.TABLE} (due_at, text, language) VALUES (?, ?, ?)", (due_at, text, None))
                    stats["imported"] += 1
                self.db.connection.commit()
            except Exception:
                self.db.connection.rollback()
                raise

            # Only now: is everything that the file had in the database?
            missing = [(due_at, text) for due_at, text in entries
                       if not self._fetch(f"SELECT id FROM {self.TABLE} WHERE due_at = ? AND text = ?", (due_at, text))]

        if missing or stats["invalid"]:
            self._xlog.error(f"🛑 The old reminders file [{path}] was NOT deleted: {len(missing)} entries are not in the database "
                             f"and {len(stats['invalid'])} could not be read: {stats['invalid']}")
            return stats

        os.remove(path)
        stats["file_deleted"] = True
        self._xlog.info(f"📝 The {stats['entries']} reminders of the old file were moved to the database "
                        f"({stats['imported']} imported, {stats['already_there']} were already there). The file is deleted.")
        return stats

    def _legacy_entries(self, content: dict) -> tuple[list[tuple[str, str]], list[str]]:
        """ The (due_at, text) of every entry of the old file, and the descriptions of the ones that can't be read. """
        entries, invalid = [], []
        if not isinstance(content, dict):
            return entries, [f"the file is not a dict of dates: {type(content).__name__}"]

        for raw_date, times in content.items():
            if times is None or times == {}:
                continue  # A date that was emptied.
            if not isinstance(times, dict):
                invalid.append(f"{raw_date}: {times!r}")
                continue
            for raw_time, text in times.items():
                try:
                    # A date written without quotes is read by YAML as a date, and its text is the ISO one.
                    date = str(raw_date)
                    if isinstance(raw_time, int):
                        # A time like 13:00 written without quotes is read by YAML as minutes (sexagesimal).
                        time = f"{raw_time // 60:02d}:{raw_time % 60:02d}"
                    else:
                        time = str(raw_time).replace("-", ":")
                    due_at = Xtime.datetime_to_str(Xtime.str_to_datetime(f"{date} {time}", self.FORMAT_DUE), self.FORMAT_DUE)
                    if text is None or str(text).strip() == "":
                        raise ValueError("no text")
                    entries.append((due_at, str(text)))
                except (ValueError, TypeError):
                    invalid.append(f"{raw_date} {raw_time}: {text!r}")
        return entries, invalid

    # ----- Internals -----

    def _to_dict(self, row: sqlite3.Row) -> dict:
        date, time = row["due_at"].split(" ")
        return {"id": row["id"], "date": date, "time": time, "text": row["text"],
                "announced": row["announced_at"] is not None}

    def _fetch(self, sql: str, args: tuple = ()) -> list[dict]:
        # A new cursor on every call: the shared one is not thread-safe.
        with self._lock:
            rows = self.db.connection.execute(sql, args).fetchall()
        return [self._to_dict(row) if "due_at" in row.keys() else {key: row[key] for key in row.keys()} for row in rows]

    def _execute(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self.db.connection.execute(sql, args)
            self.db.connection.commit()
        return cursor
