from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.database.db_sqlite import DbSqlite
from pitxu.lib.utils.string_similarity import StringSimilarity
from pitxu.lib.utils.text import Text
from pitxu.lib.utils.xtime import Xtime

from contextlib import contextmanager
import os
import re
import sqlite3
import threading
import yaml


class Lists(PyXavi, Command):
    """
    The lists, in the `list` and `list_item` tables of the database (and their translations).

    Lists are found by their name (`resolve_list()`), but their items are always handled by id, like the
    reminders and the memory entries.

    - A name or an item text can't be twice among what is not deleted. They are compared without accents, capitals
      nor extra spaces (`normalize()`), in every language that they are stored in. For an item, whether it is done
      or not does not matter: it is the same item.
    - A delete is soft (`deleted_at`): the item or list can be restored until the night cleanup purges it.
    - Items are always given open ones first, then the done ones, each group by creation order.

    Everything it gives is a dict, or False when what was asked for does not exist. A problem with the database is
    raised: the tools that call it catch it and answer the chatbot with an error message.
    """

    # What a name must look like to be taken for a list's name. The delete asks for more, as it is the one that hurts.
    SIMILARITY_THRESHOLD = 0.7
    SIMILARITY_THRESHOLD_STRICT = 0.9
    # Two lists this close to each other are an ambiguity, not a winner.
    SIMILARITY_AMBIGUITY_MARGIN = 0.05

    # The two ways of telling a list, with the number of items by status.
    LIST_COLUMNS = "id, name, language, description, favourite"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Lists, self).init_pyxavi(config=config, params=params)

        # One thread at a time in the database connection of this object.
        self._lock = threading.RLock()
        self.db = DbSqlite(config=self._xconfig, params=self._xparams)
        # SQLite asks for it on every connection to cascade the deletes to the translations and items.
        self.db.connection.execute("PRAGMA foreign_keys=ON")

    def close(self):
        self.db.close()

    # ----- Names -----

    @staticmethod
    def normalize(text: str) -> str:
        """ What names and texts are compared by: no accents, no capitals, single spaces. """
        return re.sub(r"\s+", " ", Text.remove_accents(str(text)).lower()).strip()

    def resolve_list(self, name: str, strict: bool = False, deleted: bool = False) -> dict:
        '''
        Finds a list by the name that the user said (it comes from a transcription, so it can be a bit different).

        In this order: the exact name (in any language), a unique partial one (all the words of one are in the
        other), and the most similar one. With `strict` (for a delete) only the exact name and a really similar
        one are taken. If several are equally good it is an ambiguity, and none is chosen.

        Args:
            name: What the user said.
            strict: True to be demanding, because acting on the wrong list would hurt.
            deleted: True to look among the deleted lists (to restore one) instead of the active ones.

        Returns:
            dict: {"list": dict | None, "ambiguous": bool, "candidates": list[str]}.
            `candidates` are the names of the lists that were ambiguous, or of all the lists when there is none.
        '''
        key = self.normalize(name or "")
        names = self._names(deleted)
        all_names = [entry["name"] for entry in names.values()]
        if not key or not names:
            return {"list": None, "ambiguous": False, "candidates": all_names}

        # 1. Exact, in any language.
        for list_id, entry in names.items():
            if key in entry["keys"]:
                return {"list": self.get_list_row(list_id, deleted), "ambiguous": False, "candidates": []}

        # 2. Partial: every word of one is in the other.
        if not strict:
            words = set(key.split())
            partial = [list_id for list_id, entry in names.items()
                       if any(words <= set(k.split()) or set(k.split()) <= words for k in entry["keys"])]
            if len(partial) == 1:
                return {"list": self.get_list_row(partial[0], deleted), "ambiguous": False, "candidates": []}
            if len(partial) > 1:
                return {"list": None, "ambiguous": True, "candidates": [names[i]["name"] for i in partial]}

        # 3. Similar.
        threshold = self.SIMILARITY_THRESHOLD_STRICT if strict else self.SIMILARITY_THRESHOLD
        ratings = {list_id: max(StringSimilarity.compareTwoStrings(key, k) for k in entry["keys"])
                   for list_id, entry in names.items()}
        best = max(ratings.values())
        if best >= threshold:
            winners = [list_id for list_id, rating in ratings.items() if best - rating <= self.SIMILARITY_AMBIGUITY_MARGIN]
            if len(winners) == 1:
                return {"list": self.get_list_row(winners[0], deleted), "ambiguous": False, "candidates": []}
            return {"list": None, "ambiguous": True, "candidates": [names[i]["name"] for i in winners]}

        return {"list": None, "ambiguous": False, "candidates": all_names}

    # ----- Lists -----

    def create_list(self, name: str, language: str = None, description: str = None,
                    copy_from_id: int = None, items: list[str] = None) -> dict:
        '''
        Creates a list. If there is already one with that name (in any language) nothing is created and that one
        is given back.

        With `copy_from_id` the new list gets the description (unless one is given) and the items of that one, not
        deleted and all open, with their translations. The translations of the description are not copied: the
        night translation makes them for the new name.

        Args:
            name: The name of the list, as it is to be shown.
            language: The language of the name. Default: the one of the session.
            description: Optional description.
            copy_from_id: Optional id of a list to copy the items of.
            items: Optional texts to add to the new list.

        Returns:
            dict: {"list": dict, "created": bool, "copied": int, "added": list, "duplicates": list}.
            `added` and `duplicates` are as `add_items()` gives them. "copied" is the number of copied items.
        '''
        name = (name or "").strip()
        if not name:
            raise ValueError("A list needs a name")
        language = language or self._xparams.get("language")
        key = self.normalize(name)

        existing = self._find_by_key(key)
        if existing:
            self._log_debug(f"📝 The list [{name}] already exists with the id [{existing['id']}]")
            return {"list": existing, "created": False, "copied": 0, "added": [], "duplicates": []}

        source = None
        if copy_from_id is not None:
            source = self.get_list_row(copy_from_id)
            if not source:
                raise ValueError(f"There is no list [{copy_from_id}] to copy")

        now = self._now()
        copied = 0
        with self._tx() as connection:
            cursor = connection.execute(
                "INSERT INTO list (name, name_key, language, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, key, language, description if description is not None else (source or {}).get("description"), now, now))
            list_id = int(cursor.lastrowid)
            if source:
                copied = self._copy_items(connection, source["id"], list_id, now)
        result = self.add_items(list_id, items or [], language=language) if items else {"added": [], "duplicates": []}
        created = self.get_list_row(list_id)
        self._xlog.info(f"📝 List [{list_id}] created: {name}" + (f" (copy of [{source['id']}], {copied} items)" if source else ""))
        return {"list": created, "created": True, "copied": copied,
                "added": result["added"], "duplicates": result["duplicates"]}

    def get_list_row(self, list_id: int, include_deleted: bool = False) -> dict | bool:
        '''
        The list as it is stored, without its items. False if there is none (or it is deleted).
        '''
        rows = self._fetch(f"SELECT {self.LIST_COLUMNS}, deleted_at FROM list WHERE id = ?", (list_id,))
        if not rows or (rows[0]["deleted_at"] and not include_deleted):
            return False
        row = rows[0]
        row.pop("deleted_at")
        row["favourite"] = bool(row["favourite"])
        return row

    def get_lists(self, language: str = None) -> list[dict]:
        '''
        All the lists, the favourites first and then by name, with how many items are open and done.

        Args:
            language: The language to give the names in. Default: the stored ones. The ones that do not have a
                translation yet come in the stored language, and are counted in the `untranslated` of the list.

        Returns:
            list[dict]: [{"id", "name", "description", "favourite", "open", "done", "untranslated"}]
        '''
        rows = self._fetch(
            "SELECT l.id, l.name, l.name_key, l.language, l.description, l.favourite, "
            "       t.name AS t_name, t.description AS t_description, "
            "       (SELECT COUNT(*) FROM list_item i WHERE i.list_id = l.id AND i.deleted_at IS NULL AND i.done = 0) AS open, "
            "       (SELECT COUNT(*) FROM list_item i WHERE i.list_id = l.id AND i.deleted_at IS NULL AND i.done = 1) AS done "
            "FROM list l LEFT JOIN list_translation t ON t.list_id = l.id AND t.language = ? "
            "WHERE l.deleted_at IS NULL ORDER BY l.favourite DESC, l.name_key, l.id", (language or "",))
        lists = []
        for row in rows:
            translated = bool(language) and row["language"] != language
            missing = translated and row["t_name"] is None
            lists.append({
                "id": row["id"],
                "name": row["t_name"] if translated and row["t_name"] else row["name"],
                "description": (row["t_description"] if translated and row["t_name"] else row["description"]),
                "favourite": bool(row["favourite"]),
                "open": row["open"],
                "done": row["done"],
                "untranslated": 1 if missing else 0})
        return lists

    def get_list(self, list_id: int, language: str = None, include_deleted_items: bool = False) -> dict | bool:
        '''
        A list with its items: the open ones first, then the done ones, each by creation order.

        Args:
            list_id: The id of the list.
            language: The language to give the texts in. Default: the stored ones. What does not have a translation
                yet comes in the stored language, and is counted in `untranslated`.
            include_deleted_items: True to also give the items in the trash (marked as `"deleted": True`).

        Returns:
            dict: {"id", "name", "description", "favourite", "open", "done", "untranslated", "items": [{"id", "text",
            "done", "deleted"}]}, or False if there is no such list (or it is deleted).
        '''
        listed = [entry for entry in self.get_lists(language) if entry["id"] == list_id]
        if not listed:
            return False
        result = listed[0]
        items = self._items(list_id, language, include_deleted_items)
        result["items"] = items["items"]
        result["untranslated"] += items["untranslated"]
        return result

    def update_list(self, list_id: int, new_name: str = None, new_description: str = None,
                    favourite: bool = None, language: str = None) -> dict | bool:
        '''
        Changes the name, the description and/or the favourite mark of a list. The items are not touched. Changing
        the name or the description makes its translations obsolete: they are deleted, the night translation makes
        them again.

        Args:
            list_id: The id of the list.
            new_name: The new name. If another list already has it, nothing is changed.
            new_description: The new description.
            favourite: True to mark it as a favourite (its done items are not cleaned up), False to unmark it.
            language: The language of the new texts. Default: the one of the session.

        Returns:
            dict: {"updated": bool, "list": dict, "changed": list[str], "conflict": dict | None}, or False if there
            is no such list. `conflict` is the list that already has the new name.
        '''
        current = self.get_list_row(list_id)
        if not current:
            return False
        language = language or self._xparams.get("language")

        sets, args, changed = [], [], []
        if new_name is not None and new_name.strip() and new_name.strip() != current["name"]:
            new_name = new_name.strip()
            other = self._find_by_key(self.normalize(new_name))
            if other and other["id"] != list_id:
                return {"updated": False, "list": current, "changed": [], "conflict": other}
            sets += ["name = ?", "name_key = ?"]
            args += [new_name, self.normalize(new_name)]
            changed.append("name")
        if new_description is not None and new_description != (current["description"] or ""):
            sets.append("description = ?")
            args.append(new_description)
            changed.append("description")
        if favourite is not None and bool(favourite) != current["favourite"]:
            sets.append("favourite = ?")
            args.append(1 if favourite else 0)
            changed.append("favourite")
        if not changed:
            return {"updated": False, "list": current, "changed": [], "conflict": None}

        with self._tx() as connection:
            if "name" in changed or "description" in changed:
                sets.append("language = ?")
                args.append(language)
                connection.execute("DELETE FROM list_translation WHERE list_id = ?", (list_id,))
            sets.append("updated_at = ?")
            args += [self._now(), list_id]
            connection.execute(f"UPDATE list SET {', '.join(sets)} WHERE id = ?", args)
        self._xlog.info(f"📝 List [{list_id}] updated: {', '.join(changed)}")
        return {"updated": True, "list": self.get_list_row(list_id), "changed": changed, "conflict": None}

    def delete_list(self, list_id: int) -> dict | bool:
        '''
        Deletes a list (soft: it can be restored). Its items are not touched, they are just not seen.

        Returns:
            The list deleted, with how many items it had, or False if there is no such list.
        '''
        current = self.get_list(list_id)
        if not current:
            return False
        with self._tx() as connection:
            connection.execute("UPDATE list SET deleted_at = ? WHERE id = ?", (self._now(), list_id))
        self._xlog.info(f"📝 List [{list_id}] deleted: {current['name']}")
        return {"id": list_id, "name": current["name"], "items": current["open"] + current["done"]}

    def restore_list(self, list_id: int) -> dict | bool:
        '''
        Brings back a deleted list, with its items.

        Returns:
            dict: {"restored": bool, "list": dict, "conflict": dict | None}, or False if there is no deleted list
            with that id. `conflict` is the list that took its name in the meantime (then it is not restored).
        '''
        row = self.get_list_row(list_id, include_deleted=True)
        deleted = self._fetch("SELECT deleted_at, name_key FROM list WHERE id = ?", (list_id,))
        if not row or not deleted or not deleted[0]["deleted_at"]:
            return False
        other = self._find_by_key(deleted[0]["name_key"])
        if other:
            return {"restored": False, "list": row, "conflict": other}
        with self._tx() as connection:
            connection.execute("UPDATE list SET deleted_at = NULL, updated_at = ? WHERE id = ?", (self._now(), list_id))
        self._xlog.info(f"📝 List [{list_id}] restored: {row['name']}")
        return {"restored": True, "list": self.get_list_row(list_id), "conflict": None}

    # ----- Items -----

    def get_item(self, item_id: int, include_deleted: bool = False) -> dict | bool:
        '''
        An item as it is stored: {"id", "list_id", "text", "done", "deleted"}. False if there is none.
        '''
        rows = self._fetch("SELECT id, list_id, text, done, deleted_at FROM list_item WHERE id = ?", (item_id,))
        if not rows or (rows[0]["deleted_at"] and not include_deleted):
            return False
        return self._item_dict(rows[0])

    def add_items(self, list_id: int, texts: list[str], language: str = None) -> dict | bool:
        '''
        Adds items to a list. An item that is already in the list is not added again, whether it is done or not:
        it is given back in `duplicates`, so the caller can tell the user (and decide to reopen it).

        Args:
            list_id: The id of the list.
            texts: The texts of the items.
            language: The language of the texts. Default: the one of the session.

        Returns:
            dict: {"list_id", "added": [{"id", "text"}], "duplicates": [{"id", "text", "done"}], "count": int},
            or False if there is no such list. `count` is how many items it has now.
        '''
        if not self.get_list_row(list_id):
            return False
        language = language or self._xparams.get("language")
        added, duplicates, seen = [], [], set()
        now = self._now()
        with self._tx() as connection:
            for text in texts or []:
                text = (str(text) if text is not None else "").strip()
                key = self.normalize(text)
                if not key or key in seen:
                    continue
                seen.add(key)
                duplicate = self._find_item_by_key(connection, list_id, key)
                if duplicate:
                    duplicates.append({"id": duplicate["id"], "text": duplicate["text"], "done": bool(duplicate["done"])})
                    continue
                cursor = connection.execute(
                    "INSERT INTO list_item (list_id, text, text_key, language, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (list_id, text, key, language, now, now))
                added.append({"id": int(cursor.lastrowid), "text": text})
        count = self._fetch("SELECT COUNT(*) AS n FROM list_item WHERE list_id = ? AND deleted_at IS NULL", (list_id,))[0]["n"]
        self._xlog.info(f"📝 List [{list_id}]: {len(added)} items added, {len(duplicates)} already there")
        return {"list_id": list_id, "added": added, "duplicates": duplicates, "count": count}

    def update_item(self, item_id: int, new_text: str, language: str = None) -> dict | bool:
        '''
        Changes the text of an item, and drops its translations (the night translation makes them again). If another
        item of the list already has that text, nothing is changed.

        Returns:
            dict: {"updated": bool, "item": dict, "duplicate": dict | None}, or False if there is no such item.
            `duplicate` is the item that already has the text, as `add_items()` gives the duplicates.
        '''
        item = self.get_item(item_id)
        if not item:
            return False
        new_text = (new_text or "").strip()
        key = self.normalize(new_text)
        if not key:
            raise ValueError("An item needs a text")
        language = language or self._xparams.get("language")
        with self._tx() as connection:
            duplicate = self._find_item_by_key(connection, item["list_id"], key)
            if duplicate and duplicate["id"] != item_id:
                return {"updated": False, "item": item, "duplicate":
                        {"id": duplicate["id"], "text": duplicate["text"], "done": bool(duplicate["done"])}}
            connection.execute("DELETE FROM list_item_translation WHERE item_id = ?", (item_id,))
            connection.execute("UPDATE list_item SET text = ?, text_key = ?, language = ?, updated_at = ? WHERE id = ?",
                               (new_text, key, language, self._now(), item_id))
        self._xlog.info(f"📝 Item [{item_id}] updated")
        return {"updated": True, "item": self.get_item(item_id), "duplicate": None}

    def check_items(self, done: bool, item_ids: list[int] = None, list_id: int = None) -> dict | bool:
        '''
        Marks items as done, or back to open. Either some items by id, or all the items of a list: not both.

        Returns:
            dict: {"list_ids": list[int], "changed": list[int], "unchanged": list[int], "missing": list[int]},
            or False when a list is given and it does not exist. `unchanged` already had that status.
        '''
        if (item_ids is None) == (list_id is None):
            raise ValueError("Give either the items or the list, not both and not none")
        if list_id is not None:
            if not self.get_list_row(list_id):
                return False
            item_ids = [row["id"] for row in self._fetch(
                "SELECT id FROM list_item WHERE list_id = ? AND deleted_at IS NULL ORDER BY id", (list_id,))]
        done = 1 if done else 0
        changed, unchanged, missing, list_ids = [], [], [], set()
        now = self._now()
        with self._tx() as connection:
            for item_id in item_ids:
                row = connection.execute("SELECT list_id, done FROM list_item WHERE id = ? AND deleted_at IS NULL",
                                         (item_id,)).fetchone()
                if row is None:
                    missing.append(item_id)
                    continue
                list_ids.add(row["list_id"])
                if row["done"] == done:
                    unchanged.append(item_id)
                    continue
                connection.execute("UPDATE list_item SET done = ?, done_at = ?, updated_at = ? WHERE id = ?",
                                   (done, now if done else None, now, item_id))
                changed.append(item_id)
        self._xlog.info(f"📝 {len(changed)} items marked as {'done' if done else 'open'} ({len(unchanged)} already were)")
        return {"list_ids": sorted(list_ids), "changed": changed, "unchanged": unchanged, "missing": missing}

    def remove_items(self, item_ids: list[int]) -> dict:
        '''
        Removes items (soft: they go to the trash and can be restored).

        Returns:
            dict: {"removed": [{"id", "list_id", "text", "done", "deleted"}], "missing": list[int]}
        '''
        removed, missing = [], []
        now = self._now()
        with self._tx() as connection:
            for item_id in item_ids:
                row = connection.execute("SELECT id, list_id, text, done FROM list_item WHERE id = ? AND deleted_at IS NULL",
                                         (item_id,)).fetchone()
                if row is None:
                    missing.append(item_id)
                    continue
                connection.execute("UPDATE list_item SET deleted_at = ? WHERE id = ?", (now, item_id))
                removed.append(self._item_dict({**dict(row), "deleted_at": now}))
        self._xlog.info(f"📝 {len(removed)} items removed ({len(missing)} not found)")
        return {"removed": removed, "missing": missing}

    def restore_items(self, item_ids: list[int]) -> dict:
        '''
        Brings back removed items. One whose list was deleted, or that is not in the trash, is `missing`; one whose
        text was added again in the meantime is a duplicate and is not restored.

        Returns:
            dict: {"restored": [{"id", "list_id", "text", "done", "deleted"}], "duplicates": [...], "missing": list[int]}
        '''
        restored, duplicates, missing = [], [], []
        now = self._now()
        with self._tx() as connection:
            for item_id in item_ids:
                row = connection.execute(
                    "SELECT i.id, i.list_id, i.text, i.text_key, i.done FROM list_item i JOIN list l ON l.id = i.list_id "
                    "WHERE i.id = ? AND i.deleted_at IS NOT NULL AND l.deleted_at IS NULL", (item_id,)).fetchone()
                if row is None:
                    missing.append(item_id)
                    continue
                duplicate = self._find_item_by_key(connection, row["list_id"], row["text_key"])
                if duplicate:
                    duplicates.append({"id": duplicate["id"], "text": duplicate["text"], "done": bool(duplicate["done"])})
                    continue
                connection.execute("UPDATE list_item SET deleted_at = NULL, updated_at = ? WHERE id = ?", (now, item_id))
                restored.append(self._item_dict({**dict(row), "deleted_at": None}))
        self._xlog.info(f"📝 {len(restored)} items restored ({len(duplicates)} already there, {len(missing)} not found)")
        return {"restored": restored, "duplicates": duplicates, "missing": missing}

    def get_removed_items(self, list_id: int) -> list[dict]:
        '''
        The items of a list that are in the trash, the last removed first, so the user can say which one to bring back.
        '''
        return [self._item_dict(row) for row in self._fetch(
            "SELECT id, list_id, text, done, deleted_at FROM list_item WHERE list_id = ? AND deleted_at IS NOT NULL "
            "ORDER BY deleted_at DESC, id DESC", (list_id,))]

    # ----- The night cleanup -----

    def cleanup(self, done_after_days: int, trash_after_days: int, now=None) -> dict:
        '''
        The two stages of the night cleanup:

        1. The items marked as done more than `done_after_days` days ago go to the trash (they can be restored), unless
           their list is a favourite. A favourite list keeps its done items.
        2. What is in the trash for more than `trash_after_days` days is deleted for good: the items removed (by the
           user or by the stage 1) and the lists deleted (with their items and translations).

        An item in the trash for the first stage is in it from now, so it has the whole period to be restored.

        Args:
            done_after_days: Days that a done item stays in its list.
            trash_after_days: Days that the trash keeps what is in it.
            now: The moment to count from. Default: now.

        Returns:
            dict: {"trashed": int, "purged_items": int, "purged_lists": int}
        '''
        now = now or Xtime.now()
        stamp = Xtime.datetime_to_str(now)
        done_limit = Xtime.datetime_to_str(Xtime.add_time(now, days=-done_after_days))
        trash_limit = Xtime.datetime_to_str(Xtime.add_time(now, days=-trash_after_days))
        with self._tx() as connection:
            # Stage 1. The items of a deleted list are hidden already: they go with the list.
            trashed = connection.execute(
                "UPDATE list_item SET deleted_at = ? WHERE deleted_at IS NULL AND done = 1 AND done_at IS NOT NULL AND done_at < ? "
                "AND list_id IN (SELECT id FROM list WHERE favourite = 0 AND deleted_at IS NULL)", (stamp, done_limit)).rowcount
            # Stage 2. The items of the lists that go are deleted with them (the cascade): they are counted before.
            purged_items = connection.execute(
                "SELECT COUNT(*) FROM list_item WHERE list_id IN (SELECT id FROM list WHERE deleted_at IS NOT NULL AND deleted_at < ?) "
                "OR (deleted_at IS NOT NULL AND deleted_at < ?)", (trash_limit, trash_limit)).fetchone()[0]
            connection.execute("DELETE FROM list_item WHERE deleted_at IS NOT NULL AND deleted_at < ?", (trash_limit,))
            purged_lists = connection.execute("DELETE FROM list WHERE deleted_at IS NOT NULL AND deleted_at < ?", (trash_limit,)).rowcount
        self._xlog.info(f"📝 Lists cleanup: {trashed} done items to the trash (more than {done_after_days} days done), "
                        f"{purged_items} items and {purged_lists} lists deleted for good (more than {trash_after_days} days in the trash)")
        return {"trashed": trashed, "purged_items": purged_items, "purged_lists": purged_lists}

    # ----- Translations (made by the night translation, see ListTranslator) -----

    def get_untranslated(self, languages: list[str]) -> list[dict]:
        '''
        What still has to be translated: the names (and descriptions) of the active lists, and the items of the
        active lists that are not removed, each with the languages that it misses. A text is not translated into the
        language that it was written in. Lists first, then items, both in id order.

        Args:
            languages: The languages that everything must be in (the supported ones).

        Returns:
            list[dict]: [{"kind": "list" | "item", "id", "source_language", "text", "description", "key", "targets"}].
            `key` is the key of the text now: the translation is only stored if it is still the same text (see `set_*_translation()`).
            `source_language` is None when it is not known. `description` is for lists only.
        '''
        have = {}
        for row in self._fetch("SELECT list_id AS id, language FROM list_translation"):
            have.setdefault(("list", row["id"]), set()).add(row["language"])
        for row in self._fetch("SELECT item_id AS id, language FROM list_item_translation"):
            have.setdefault(("item", row["id"]), set()).add(row["language"])

        elements = []
        for row in self._fetch("SELECT id, name AS text, name_key AS key, language, description FROM list "
                               "WHERE deleted_at IS NULL ORDER BY id"):
            elements.append({"kind": "list", "source_language": row["language"], **{k: row[k] for k in ("id", "text", "key", "description")}})
        for row in self._fetch("SELECT i.id, i.text, i.text_key AS key, i.language FROM list_item i JOIN list l ON l.id = i.list_id "
                               "WHERE i.deleted_at IS NULL AND l.deleted_at IS NULL ORDER BY i.id"):
            elements.append({"kind": "item", "source_language": row["language"], "description": None,
                             **{k: row[k] for k in ("id", "text", "key")}})

        pending = []
        for element in elements:
            skip = {element["source_language"]} | have.get((element["kind"], element["id"]), set())
            element["targets"] = [language for language in languages if language not in skip]
            if element["targets"]:
                pending.append(element)
        return pending

    def set_list_translation(self, list_id: int, language: str, name: str, description: str, source_key: str) -> str:
        '''
        Stores the name and the description of a list in a language.

        Args:
            source_key: The key of the name that was translated. If the name changed meanwhile, the translation is stale.

        Returns:
            str: "stored", "stale" (the list is gone or its name changed), or "collision" (the name is already the
            one of another list: it would hide it, so it is not stored).
        '''
        key = self.normalize(name)
        with self._tx() as connection:
            row = connection.execute("SELECT name_key FROM list WHERE id = ? AND deleted_at IS NULL", (list_id,)).fetchone()
            if row is None or row["name_key"] != source_key:
                return "stale"
            clash = connection.execute(
                "SELECT id FROM list WHERE deleted_at IS NULL AND id != ? AND (name_key = ? OR id IN "
                "(SELECT list_id FROM list_translation WHERE name_key = ? AND list_id != ?))", (list_id, key, key, list_id)).fetchone()
            if clash:
                return "collision"
            connection.execute(
                "INSERT OR REPLACE INTO list_translation (list_id, language, name, name_key, description) VALUES (?, ?, ?, ?, ?)",
                (list_id, language, name.strip(), key, (description or "").strip() or None))
        return "stored"

    def set_item_translation(self, item_id: int, language: str, text: str, source_key: str) -> str:
        '''
        Stores the text of an item in a language.

        Args:
            source_key: The key of the text that was translated. If the text changed meanwhile, the translation is stale.

        Returns:
            str: "stored", or "stale" (the item is gone, in the trash, or its text changed).
        '''
        with self._tx() as connection:
            row = connection.execute("SELECT text_key FROM list_item WHERE id = ? AND deleted_at IS NULL", (item_id,)).fetchone()
            if row is None or row["text_key"] != source_key:
                return "stale"
            connection.execute("INSERT OR REPLACE INTO list_item_translation (item_id, language, text, text_key) VALUES (?, ?, ?, ?)",
                               (item_id, language, text.strip(), self.normalize(text)))
        return "stored"

    # ----- The file that was before the database -----

    # The file where the lists were before they were in the database. See `import_legacy_yaml()`.
    LEGACY_FILENAME = "lists.yaml"
    LEGACY_FORMAT = "%Y-%m-%d %H:%M"

    def import_legacy_yaml(self, path: str = None, language: str = None) -> dict:
        '''
        Moves the lists of the old `lists.yaml` into the database, and deletes the file once ALL of them are there.
        If anything is wrong the file stays untouched and the next start tries again (what was already imported is
        not imported twice).

        The old file had `slug: {name, description, created_at, entries: [{text, created_at, ...}]}`. Lists and items
        keep their creation date, and get the given language (they were written in the one of the application).
        An item that is twice in a list is imported once: the repeated ones are in `duplicates`, and do not stop the
        file from being deleted.

        Args:
            path: The file. Default: the one in the storage path.
            language: The language of the lists and items. Default: the one of the session, or the default one.

        Returns:
            dict: {"found": bool, "lists": int, "items": int, "imported_lists": int, "imported_items": int,
            "already_there": int, "duplicates": list, "invalid": list, "file_deleted": bool}
        '''
        path = path or os.path.join(self._xconfig.get("storage.path"), self.LEGACY_FILENAME)
        stats = {"found": os.path.exists(path), "lists": 0, "items": 0, "imported_lists": 0, "imported_items": 0,
                 "already_there": 0, "duplicates": [], "invalid": [], "file_deleted": False}
        if not stats["found"]:
            return stats
        language = language or self._xparams.get("language") or self._xconfig.get("app.default_language")

        with open(path, encoding="utf-8") as stream:
            content = yaml.safe_load(stream) or {}
        lists, stats["invalid"] = self._legacy_lists(content)
        stats["lists"] = len(lists)
        stats["items"] = sum(len(entry["items"]) for entry in lists)

        with self._tx() as connection:
            for entry in lists:
                row = connection.execute("SELECT id FROM list WHERE name_key = ? AND deleted_at IS NULL", (entry["key"],)).fetchone()
                if row:
                    list_id = row["id"]
                else:
                    list_id = int(connection.execute(
                        "INSERT INTO list (name, name_key, language, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (entry["name"], entry["key"], language, entry["description"], entry["created_at"], entry["created_at"])).lastrowid)
                    stats["imported_lists"] += 1
                for item in entry["items"]:
                    if self._find_item_by_key(connection, list_id, item["key"]):
                        # Already in the database: from an earlier start, or a repeated one of the same file.
                        if item["key"] in entry["seen"]:
                            stats["duplicates"].append(f"{entry['name']}: {item['text']}")
                        else:
                            stats["already_there"] += 1
                    else:
                        connection.execute(
                            "INSERT INTO list_item (list_id, text, text_key, language, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (list_id, item["text"], item["key"], language, item["created_at"], item["created_at"]))
                        stats["imported_items"] += 1
                    entry["seen"].add(item["key"])

        # Only now: is everything that the file had in the database?
        missing = []
        for entry in lists:
            found = self._fetch("SELECT id FROM list WHERE name_key = ? AND deleted_at IS NULL", (entry["key"],))
            if not found:
                missing.append(entry["name"])
                continue
            missing += [f"{entry['name']}: {item['text']}" for item in entry["items"]
                        if not self._fetch("SELECT id FROM list_item WHERE list_id = ? AND text_key = ? AND deleted_at IS NULL",
                                           (found[0]["id"], item["key"]))]

        if missing or stats["invalid"]:
            self._xlog.error(f"🛑 The old lists file [{path}] was NOT deleted: {len(missing)} entries are not in the database "
                             f"and {len(stats['invalid'])} could not be read: {stats['invalid']}")
            return stats

        os.remove(path)
        stats["file_deleted"] = True
        self._xlog.info(f"📝 The {stats['lists']} lists ({stats['items']} items) of the old file were moved to the database "
                        f"({stats['imported_lists']} lists and {stats['imported_items']} items imported, "
                        f"{stats['already_there']} items were already there, {len(stats['duplicates'])} repeated ones kept once: "
                        f"{stats['duplicates']}). The file is deleted.")
        return stats

    def _legacy_lists(self, content: dict) -> tuple[list[dict], list[str]]:
        """ The lists of the old file as {"name", "key", "description", "created_at", "items", "seen"}, and what can't be read. """
        lists, invalid, by_key = [], [], {}
        if not isinstance(content, dict):
            return lists, [f"the file is not a dict of lists: {type(content).__name__}"]

        for slug, raw in content.items():
            if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
                invalid.append(f"{slug}: {raw!r}")
                continue
            name = str(raw["name"]).strip()
            key = self.normalize(name)
            created_at = self._legacy_date(raw.get("created_at"))
            entries = raw.get("entries")
            if entries is None:
                entries = []
            if not isinstance(entries, list):
                invalid.append(f"{slug}: the entries are not a list: {entries!r}")
                continue
            # Two slugs that are the same name: one list.
            current = by_key.get(key)
            if current is None:
                current = by_key[key] = {"name": name, "key": key, "created_at": created_at, "seen": set(), "items": [],
                                         "description": raw.get("description") if raw.get("description") not in (None, "") else None}
                lists.append(current)
            for entry in entries:
                text = str(entry.get("text") or "").strip() if isinstance(entry, dict) else ""
                if not text:
                    invalid.append(f"{slug}: {entry!r}")
                    continue
                current["items"].append({"text": text, "key": self.normalize(text),
                                         "created_at": self._legacy_date(entry.get("created_at")) or current["created_at"]})
        return lists, invalid

    def _legacy_date(self, value) -> str:
        """ The creation date of the old file as text. YAML reads an unquoted date as a datetime. Unknown: now. """
        if value in (None, ""):
            return self._now()
        if hasattr(value, "strftime"):
            return value.strftime(self.LEGACY_FORMAT)
        return str(value)

    # ----- Internals -----

    @staticmethod
    def _now() -> str:
        return Xtime.datetime_to_str(Xtime.now())

    @staticmethod
    def _item_dict(row: dict) -> dict:
        return {"id": row["id"], "list_id": row["list_id"], "text": row["text"], "done": bool(row["done"]),
                "deleted": bool(row.get("deleted_at"))}

    def _names(self, deleted: bool = False) -> dict:
        """ {list_id: {"name", "keys": set of the name keys in every language}} of the active (or deleted) lists. """
        rows = self._fetch(f"SELECT id, name, name_key FROM list WHERE deleted_at IS {'NOT ' if deleted else ''}NULL ORDER BY id")
        names = {row["id"]: {"name": row["name"], "keys": {row["name_key"]}} for row in rows}
        for row in self._fetch("SELECT list_id, name_key FROM list_translation"):
            if row["list_id"] in names:
                names[row["list_id"]]["keys"].add(row["name_key"])
        return names

    def _find_by_key(self, key: str) -> dict | None:
        """ The active list that has this name key, in its name or in any translation. """
        rows = self._fetch(
            "SELECT l.id FROM list l WHERE l.deleted_at IS NULL AND (l.name_key = ? "
            "OR l.id IN (SELECT list_id FROM list_translation WHERE name_key = ?)) ORDER BY l.id", (key, key))
        return self.get_list_row(rows[0]["id"]) if rows else None

    @staticmethod
    def _find_item_by_key(connection: sqlite3.Connection, list_id: int, key: str) -> sqlite3.Row | None:
        """ The item of the list (not deleted) whose text key is this one, in its text or in any translation. """
        return connection.execute(
            "SELECT id, text, done FROM list_item WHERE list_id = ? AND deleted_at IS NULL AND (text_key = ? "
            "OR id IN (SELECT item_id FROM list_item_translation WHERE text_key = ?)) ORDER BY id LIMIT 1",
            (list_id, key, key)).fetchone()

    def _items(self, list_id: int, language: str = None, include_deleted: bool = False) -> dict:
        rows = self._fetch(
            "SELECT i.id, i.list_id, i.text, i.language, i.done, i.deleted_at, t.text AS t_text "
            "FROM list_item i LEFT JOIN list_item_translation t ON t.item_id = i.id AND t.language = ? "
            f"WHERE i.list_id = ?{'' if include_deleted else ' AND i.deleted_at IS NULL'} "
            "ORDER BY (i.deleted_at IS NOT NULL), i.done, i.created_at, i.id", (language or "", list_id))
        items, untranslated = [], 0
        for row in rows:
            translated = bool(language) and row["language"] != language
            if translated and row["t_text"] is None:
                untranslated += 1
            items.append({"id": row["id"], "text": row["t_text"] if translated and row["t_text"] else row["text"],
                          "done": bool(row["done"]), "deleted": bool(row["deleted_at"])})
        return {"items": items, "untranslated": untranslated}

    def _copy_items(self, connection: sqlite3.Connection, source_id: int, target_id: int, now: str) -> int:
        """ The items of a list into another, open, with their translations. """
        copied = 0
        for row in connection.execute(
                "SELECT id, text, text_key, language FROM list_item WHERE list_id = ? AND deleted_at IS NULL "
                "ORDER BY created_at, id", (source_id,)).fetchall():
            cursor = connection.execute(
                "INSERT INTO list_item (list_id, text, text_key, language, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (target_id, row["text"], row["text_key"], row["language"], now, now))
            connection.execute(
                "INSERT INTO list_item_translation (item_id, language, text, text_key) "
                "SELECT ?, language, text, text_key FROM list_item_translation WHERE item_id = ?",
                (cursor.lastrowid, row["id"]))
            copied += 1
        return copied

    def _fetch(self, sql: str, args: tuple = ()) -> list[dict]:
        # A new cursor on every call: the shared one is not thread-safe.
        with self._lock:
            rows = self.db.connection.execute(sql, args).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    @contextmanager
    def _tx(self):
        """ One transaction with the lock: everything inside is saved together, or nothing is. """
        with self._lock:
            try:
                yield self.db.connection
                self.db.connection.commit()
            except Exception:
                self.db.connection.rollback()
                raise
