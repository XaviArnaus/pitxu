from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.utils.lists import Lists
from pitxu.lib.interaction.interaction import Interaction

import logging


class StatefulLists(PyXavi, Command):
    """
    The tools of the chatbot to handle lists.

    Lists are told by their name, items by their id (like the reminders and the memory entries). The answers are
    compact, to cost few tokens: an item is `[id, text, done]` (`[id, text]` when it was just added), and a list
    that was changed is not read back: what the screen shows is read from the database by the callbacks.
    A problem is answered with a message (a string) in the language of the session.
    """

    _lists: Lists = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(StatefulLists, self).init_pyxavi(config=config, params=params)

        # The application shares one Lists (one connection to the database) with the tools, through the params.
        self._lists = self._xparams.get("lists") if self._xparams.key_exists("lists") \
            else Lists(config=config, params=params)

    # ----- Helpers -----

    def _message(self, key: str) -> str:
        """ The message `language.lists.<key>` in the current language. """
        return self._xconfig.get("language.lists." + key + "." + self._xparams.get("language"))

    def _resolve(self, list_name: str, strict: bool = False, deleted: bool = False) -> dict | str:
        """
        The list that the user meant, or the message that tells the chatbot what to do: the lists that exist
        (so it can ask or create it), or the ones that could be it.
        """
        found = self._lists.resolve_list(list_name, strict=strict, deleted=deleted)
        if found["list"]:
            return found["list"]
        if found["ambiguous"]:
            return self._message("list_ambiguous") % (list_name, ", ".join(found["candidates"]))
        if found["candidates"]:
            return self._message("list_not_found") % (list_name, ", ".join(found["candidates"]))
        return self._message("list_not_found_empty") % list_name

    @staticmethod
    def _as_ids(item_ids) -> list[int]:
        """ The ids as integers. The chatbot may send one, or text: what is not a number is left out. """
        if item_ids is None:
            return []
        if not isinstance(item_ids, (list, tuple, set)):
            item_ids = [item_ids]
        ids = []
        for item_id in item_ids:
            try:
                ids.append(int(item_id))
            except (TypeError, ValueError):
                continue
        return ids

    @staticmethod
    def _as_texts(items) -> list[str]:
        """ The texts as a list of strings (the chatbot may send just one). """
        if items is None:
            return []
        if not isinstance(items, (list, tuple, set)):
            items = [items]
        return [str(item) for item in items if item is not None]

    @staticmethod
    def _pairs(items: list[dict]) -> list[list]:
        return [[item["id"], item["text"]] for item in items]

    @staticmethod
    def _triples(items: list[dict]) -> list[list]:
        return [[item["id"], item["text"], bool(item["done"])] for item in items]

    # ----- Tools -----

    def get_lists(self, list_name: str = None, language: str = None) -> dict | list | str:
        '''
        Get the lists (id, name, open and done counts), or with list_name that list with its items as [id, text, done].
        With a language code (e.g. "de") names and texts come in that language; `untranslated` counts the ones you must translate yourself.

        Args:
            list_name (str): Optional. The list to get the items of.
            language (str): Optional. The language code to get the texts in.
        '''
        self._xlog.info(f"📝 Request for Retrieving the lists. List [{list_name}], language [{language}]")
        try:
            language = language.strip().lower() if language else None
            if list_name:
                found = self._resolve(list_name)
                if isinstance(found, str):
                    return found
                full = self._lists.get_list(found["id"], language)
                result = {"id": full["id"], "name": full["name"], "open": full["open"], "done": full["done"],
                          "items": self._triples(full["items"])}
                if full["description"]:
                    result["description"] = full["description"]
                if full["favourite"]:
                    result["favourite"] = True
                if full["untranslated"]:
                    result["untranslated"] = full["untranslated"]
                return result

            overview = []
            for entry in self._lists.get_lists(language):
                line = {"id": entry["id"], "name": entry["name"], "open": entry["open"], "done": entry["done"]}
                if entry["favourite"]:
                    line["favourite"] = True
                if entry["untranslated"]:
                    line["untranslated"] = True
                overview.append(line)
            return overview
        except Exception as e:
            self._xlog.error(f"🛑 Error retrieving the lists [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("list_retrieval_error")

    def create_list(self, name: str, copy_from: str = None, items: list[str] = None) -> dict | str:
        '''
        Create a list, optionally with items. If it already exists nothing is created (`created` false).
        With copy_from (another list's name) it gets that list's items, all open again.

        Args:
            name (str): The name of the list.
            copy_from (str): Optional. The list to copy the items from.
            items (list[str]): Optional. The items to add.
        '''
        self._xlog.info(f"📝 Request for Creating the list [{name}]. Copy from [{copy_from}]")
        try:
            if not name or not str(name).strip():
                return self._message("list_name_missing")
            source_id = None
            if copy_from:
                source = self._resolve(copy_from)
                if isinstance(source, str):
                    return source
                source_id = source["id"]

            created = self._lists.create_list(str(name), copy_from_id=source_id, items=self._as_texts(items))
            result = {"id": created["list"]["id"], "name": created["list"]["name"], "created": created["created"]}
            if not created["created"]:
                full = self._lists.get_list(created["list"]["id"])
                result.update({"open": full["open"], "done": full["done"]})
                return result
            if created["copied"]:
                result["copied"] = created["copied"]
            if created["added"]:
                result["added"] = self._pairs(created["added"])
            if created["duplicates"]:
                result["duplicates"] = [[d["id"], d["text"], d["done"]] for d in created["duplicates"]]
            return result
        except Exception as e:
            self._xlog.error(f"🛑 Error creating the list [{name}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("list_creation_error")

    def update_list(self, list_name: str, new_name: str = None, new_description: str = None, favourite: bool = None) -> dict | str:
        '''
        Rename a list, change its description, or mark it as favourite (its done items are kept). Items are not touched.

        Args:
            list_name (str): The name of the list.
            new_name (str): Optional. The new name.
            new_description (str): Optional. The new description.
            favourite (bool): Optional. True or False to mark or unmark it.
        '''
        self._xlog.info(f"📝 Request for Updating the list [{list_name}]")
        try:
            found = self._resolve(list_name)
            if isinstance(found, str):
                return found
            updated = self._lists.update_list(found["id"], new_name=new_name, new_description=new_description, favourite=favourite)
            if updated["conflict"]:
                return self._message("list_name_taken") % updated["conflict"]["name"]
            return {"id": found["id"], "name": updated["list"]["name"], "changed": updated["changed"]}
        except Exception as e:
            self._xlog.error(f"🛑 Error updating the list [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("list_update_error")

    def delete_list(self, list_name: str) -> dict | str:
        '''
        Delete a list (it can be brought back with `restore`).

        Args:
            list_name (str): The exact name of the list.
        '''
        self._xlog.info(f"📝 Request for Deleting the list [{list_name}]")
        try:
            found = self._resolve(list_name, strict=True)
            if isinstance(found, str):
                return found
            return self._lists.delete_list(found["id"])
        except Exception as e:
            self._xlog.error(f"🛑 Error deleting the list [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("list_deletion_error")

    def add_items(self, list_name: str, items: list[str]) -> dict | str:
        '''
        Add several items to a list at once. Items already there, done or not, are not added: they come in `duplicates` as
        [id, text, done], so tell the user and, if done, offer to reopen them. If the list does not exist, use `create_list`.

        Args:
            list_name (str): The name of the list.
            items (list[str]): The items to add.
        '''
        self._xlog.info(f"📝 Request for Adding {len(self._as_texts(items))} items to the list [{list_name}]")
        try:
            found = self._resolve(list_name)
            if isinstance(found, str):
                return found
            added = self._lists.add_items(found["id"], self._as_texts(items))
            result = {"list": found["name"], "list_id": found["id"], "added": self._pairs(added["added"]), "count": added["count"]}
            if added["duplicates"]:
                result["duplicates"] = [[d["id"], d["text"], d["done"]] for d in added["duplicates"]]
            return result
        except Exception as e:
            self._xlog.error(f"🛑 Error adding items to the list [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("list_items_error")

    def update_item(self, item_id: int, new_text: str) -> dict | str:
        '''
        Change the text of an item by its id.

        Args:
            item_id (int): The id of the item.
            new_text (str): The new text.
        '''
        self._xlog.info(f"📝 Request for Updating the item [{item_id}] to: {new_text}")
        try:
            ids = self._as_ids(item_id)
            updated = self._lists.update_item(ids[0], new_text) if ids else False
            if not updated:
                return self._message("item_not_found") % item_id
            if updated["duplicate"]:
                d = updated["duplicate"]
                return {"updated": False, "duplicate": [d["id"], d["text"], d["done"]]}
            return {"id": updated["item"]["id"], "text": updated["item"]["text"], "list_id": updated["item"]["list_id"]}
        except Exception as e:
            self._xlog.error(f"🛑 Error updating the item [{item_id}] to [{new_text}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("list_items_error")

    def check_items(self, done: bool, item_ids: list[int] = None, list_name: str = None) -> dict | str:
        '''
        Mark items as done, or open again with done=false. Give item ids, or a list name for ALL its items (to reset a list). Not both.

        Args:
            done (bool): True for done, False for open.
            item_ids (list[int]): Optional. The ids of the items.
            list_name (str): Optional. The list whose items are all marked.
        '''
        self._xlog.info(f"📝 Request for Marking as {'done' if done else 'open'}: items [{item_ids}] list [{list_name}]")
        try:
            ids = self._as_ids(item_ids)
            if bool(ids) == bool(list_name):
                return self._message("list_check_needs_target")
            if list_name:
                found = self._resolve(list_name)
                if isinstance(found, str):
                    return found
                checked = self._lists.check_items(bool(done), list_id=found["id"])
            else:
                checked = self._lists.check_items(bool(done), item_ids=ids)
            result = {"done": bool(done), "changed": checked["changed"]}
            for key in ("unchanged", "missing"):
                if checked[key]:
                    result[key] = checked[key]
            if checked["list_ids"]:
                result["list_id"] = checked["list_ids"][0]
            return result
        except Exception as e:
            self._xlog.error(f"🛑 Error marking items [{item_ids}] [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("list_items_error")

    def remove_items(self, item_ids: list[int]) -> dict | str:
        '''
        Remove items by id (they can be brought back with `restore`).

        Args:
            item_ids (list[int]): The ids of the items.
        '''
        self._xlog.info(f"📝 Request for Removing the items [{item_ids}]")
        try:
            removed = self._lists.remove_items(self._as_ids(item_ids))
            result = {"removed": self._pairs(removed["removed"])}
            if removed["missing"]:
                result["missing"] = removed["missing"]
            if removed["removed"]:
                result["list_id"] = removed["removed"][0]["list_id"]
            return result
        except Exception as e:
            self._xlog.error(f"🛑 Error removing the items [{item_ids}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("list_items_error")

    def restore(self, item_ids: list[int] = None, list_name: str = None) -> dict | str:
        '''
        Bring back removed items by id, or a deleted list by name. With the name of an existing list and no ids it only
        gives its `removed` items as [id, text], to ask which one.

        Args:
            item_ids (list[int]): Optional. The ids of removed items.
            list_name (str): Optional. A deleted list to bring back, or a list to see its removed items.
        '''
        self._xlog.info(f"📝 Request for Restoring items [{item_ids}] or list [{list_name}]")
        try:
            ids = self._as_ids(item_ids)
            if ids:
                restored = self._lists.restore_items(ids)
                result = {"restored": self._pairs(restored["restored"])}
                if restored["duplicates"]:
                    result["duplicates"] = [[d["id"], d["text"], d["done"]] for d in restored["duplicates"]]
                if restored["missing"]:
                    result["missing"] = restored["missing"]
                if restored["restored"]:
                    result["list_id"] = restored["restored"][0]["list_id"]
                return result

            if not list_name:
                return self._message("list_restore_needs_target")

            # A list that exists: its trash, to choose from. Otherwise a deleted one: it comes back.
            active = self._lists.resolve_list(list_name)
            if active["list"]:
                return {"list": active["list"]["name"], "removed": self._pairs(self._lists.get_removed_items(active["list"]["id"]))}
            deleted = self._lists.resolve_list(list_name, deleted=True)
            if deleted["ambiguous"]:
                return self._message("list_ambiguous") % (list_name, ", ".join(deleted["candidates"]))
            if not deleted["list"]:
                return self._resolve(list_name)  # It is not among the deleted ones either: say what lists exist.
            restored = self._lists.restore_list(deleted["list"]["id"])
            if not restored["restored"]:
                return self._message("list_name_taken") % restored["conflict"]["name"]
            return {"restored": restored["list"]["name"], "id": restored["list"]["id"], "list_id": restored["list"]["id"]}
        except Exception as e:
            self._xlog.error(f"🛑 Error restoring [{item_ids}] [{list_name}]: {e}")
            self._xlog.debug(full_stack())
            return self._message("list_items_error")

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_lists,
                self.create_list,
                self.update_list,
                self.delete_list,
                self.add_items,
                self.update_item,
                self.check_items,
                self.remove_items,
                self.restore]

    # ----- The screen -----

    # The list is drawn as plain text (the foreground does not read Markdown), so the status and the change are
    #   told with emoji: a box for each item, and a marker at the end of what the last action touched.
    OPEN = "⬜"
    DONE = "✅"
    MARK = "👈"
    ICON = "📝"
    ICON_FAVOURITE = "⭐"
    # The most items on the screen. A longer list is shown as a window around the change, with how many are hidden.
    SCREEN_MAX_ITEMS = 8

    def _line(self, item: dict, marked: bool) -> str:
        return f"{self.DONE if item['done'] else self.OPEN} {item['text']}{' ' + self.MARK if marked else ''}"

    def _window(self, items: list[dict], marked: set) -> list[str]:
        """ The lines of the items. If they are too many: the window around the first one marked, and `… +n` for the hidden. """
        lines = [self._line(item, item["id"] in marked) for item in items]
        if len(lines) <= self.SCREEN_MAX_ITEMS:
            return lines
        first = next((index for index, item in enumerate(items) if item["id"] in marked), 0)
        start = min(max(first - self.SCREEN_MAX_ITEMS // 2, 0), len(lines) - self.SCREEN_MAX_ITEMS)
        end = start + self.SCREEN_MAX_ITEMS
        return ([f"… +{start}"] if start else []) + lines[start:end] + ([f"… +{len(lines) - end}"] if end < len(lines) else [])

    @staticmethod
    def _ids(entries) -> list[int]:
        """ The ids of what the tools answer: [[id, text, ...], ...]. """
        return [entry[0] for entry in entries or [] if isinstance(entry, (list, tuple)) and entry]

    def _show_text(self, log: logging, interaction: Interaction, text: str, header: str = None, icon: str = None, as_list: bool = False) -> None:
        canvas = interaction.get_canvas_from_foreground_display()
        interaction.show_arbitrary_text_on_foreground_while_speaking(
            icon=icon or self.ICON,
            text=text,
            font_size=canvas.FONT_SIZE_MEDIUM if as_list else canvas.FONT_SIZE_BIG,
            header=header,
            font_header_size=canvas.FONT_SIZE_HUGE,
            align="left" if as_list else "center",
            valign="top" if as_list else "center")

    def _show_list(self, log: logging, interaction: Interaction, list_id: int, marked: set = None, removed: list = None) -> None:
        """ A list, read from the database now: the items touched are marked, and what was removed comes in a last line. """
        full = self._lists.get_list(list_id, self._xparams.get("language"))
        if not full:
            log.debug(f"📝 The list [{list_id}] is not there to be shown")
            return
        lines = self._window(full["items"], marked or set())
        if removed:
            lines.append("🗑 " + self._message("list_removed_screen") % ", ".join(removed))
        text = "\n".join(lines) if lines else self._message("list_items_empty")
        log.debug(f"📝 Showing the list [{full['name']}] on the foreground display")
        self._show_text(log, interaction, text, header=full["name"], as_list=bool(lines),
                        icon=self.ICON_FAVOURITE if full["favourite"] else self.ICON)

    def show_lists(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """ `get_lists`: the names of the lists (the favourite ones with a star) and how many items are open in each. """
        try:
            if isinstance(value, dict):
                return self.show_list(log, interaction, value, args)  # It was asked for one list.
            if not isinstance(value, list):
                return self._show_text(log, interaction, str(value))  # A message (an error): as it is.
            lines = [f"{self.ICON_FAVOURITE + ' ' if entry.get('favourite') else ''}{entry['name']} ({entry['open']})" for entry in value]
            self._show_text(log, interaction, "\n".join(lines) if lines else self._message("list_lists_empty"),
                            header=self._message("lists_header"), as_list=bool(lines))
        except Exception as e:
            log.error(f"🛑 Error showing the lists on the foreground display: {e}")

    def show_list(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        """
        What was done to a list or to its items: the list as it is now, with the items that were touched marked
        (added, changed, marked as done or open, brought back, or the one that was already there), and what was removed.
        Also for a list that was only read. A message (an error) is shown as it is.
        """
        try:
            if not isinstance(value, dict):
                return self._show_text(log, interaction, str(value))

            # The removed items of a list, to choose from (`restore` with a name): they are what is shown.
            if "removed" in value and "list" in value and "list_id" not in value:
                lines = [f"🗑 {text}" for _, text in value["removed"]]
                return self._show_text(log, interaction, "\n".join(lines) if lines else self._message("list_trash_empty"),
                                       header=value["list"], as_list=bool(lines))

            list_id = value.get("list_id") or value.get("id")
            marked = set(self._ids(value.get("added")) + self._ids(value.get("duplicates")) + self._ids(value.get("restored"))
                         + [i for i in value.get("changed", []) if isinstance(i, int)])
            if "duplicate" in value:  # An item that could not be changed because its text was already there.
                marked.add(value["duplicate"][0])
                list_id = list_id or self._lists.get_item(value["duplicate"][0])["list_id"]
            elif "text" in value and "list_id" in value:  # An item that was changed.
                marked.add(value["id"])
            self._show_list(log, interaction, list_id, marked, removed=[text for _, text in value.get("removed", [])])
        except Exception as e:
            log.error(f"🛑 Error showing the list on the foreground display: {e}")

    def show_deleted_list(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        try:
            text = self._message("list_deleted_screen") % value["name"] if isinstance(value, dict) else str(value)
            self._show_text(log, interaction, text, icon="🗑")
        except Exception as e:
            log.error(f"🛑 Error showing the deleted list on the foreground display: {e}")

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_lists":
            return self.show_lists
        elif function_name == "delete_list":
            return self.show_deleted_list
        elif function_name in ("create_list", "update_list", "add_items", "update_item", "check_items", "remove_items", "restore"):
            return self.show_list
        return self.default_empty_callback
