
from pyxavi import Storage, Config, Dictionary, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command

from datetime import datetime


class Lists(PyXavi, Command):

    LIST_FILENAME = "lists.yaml"

    FORMAT_DATE = "%Y-%m-%d"  # E.g., 2023-12-25
    FORMAT_TIME = "%H:%M"     # E.g., 14:30

    LIST_TEMPLATE = {
        "name": "",
        "description": "",
        "created_at": "",
        "entries": []
    }

    ENTRY_TEMPLATE = {
        "created at": "",
        "text": ""
    }

    state: Storage = None

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Lists, self).init_pyxavi(config=config, params=params)

        self.state = self._state = Storage(filename=self._xconfig.get("storage.path") + self.LIST_FILENAME)

    def create_list(self, list_name: str, list_description: str = None, list_datetime: str = None, list_entries: list = None) -> dict | bool:
        '''
        Creates a list with the given name and description.

        Args:
            list_name: The name of the list to create.
            list_description: The description of the list to create.
            list_datetime: Optional, internal use. The date and time of the list to create.Ignored for new lists.
            list_entries: Optional, internal use. The entries of the list to create. Ignored for new lists.

        Returns:
            The created list details as a JSON object or False if a list with the same name already exists.
        '''
        self._log_debug(f"📝 Creating a list for [{list_name}]")

        # First check if there are existing lists for that key
        if self.state.key_exists(list_name):
            self._xlog.debug(f"📝 List already exists for [{list_name}]")
            return False

        new_list = self._pack_list({
            "name": list_name.capitalize(),
            "description": list_description,
            "created_at": datetime.now().strftime(f"{self.FORMAT_DATE} {self.FORMAT_TIME}") if not list_datetime else list_datetime,
            "entries": list_entries if list_entries else []
        })
        self.state.set(list_name, new_list, slugify_param_name=True)
        self.state.write_file()
        self._xlog.info(f"📝 List created for [{list_name}]")

        return new_list
    
    def get_lists(self) -> dict:
        '''
        Retrieves all the lists.

        Returns:
            A dictionary containing all the lists.
        '''
        self._log_debug(f"📝 Retrieving all lists")
        self.state.read_file()
        all_lists = self.state.get_all()
        self._xlog.info(f"📝 All {len(all_lists)} lists retrieved")
        return all_lists

    def delete_list(self, list_name: str) -> dict | bool:
        '''
        Deletes a specific list.
        
        Args:
            list_name: The name of the list to delete.

        Returns:
            A dictionary with the deleted list details or False if not found.
        '''
        self._log_debug(f"📝 Deleting a list for [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            deleting_list_data = self.state.get(list_name, slugify_param_name=True)
            self.state.delete(list_name, slugify_param_name=True)
            self.state.write_file()
            self._xlog.info(f"📝 List deleted for [{list_name}]")
            return deleting_list_data
        else:
            self._xlog.error(f"🛑 No list found for [{list_name}]")
            return False

    def get_list(self, list_name: str) -> dict | bool:
        '''
        Retrieves a specific list by a given name.
        
        Args:
            list_name: The name of the list to retrieve.

        Returns:
            The list details as a JSON object or False if not found.
        '''
        self._log_debug(f"📝 Retrieving a list for [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            self._xlog.info(f"📝 List found for [{list_name}]")
            list_raw_data = self.state.get(list_name, slugify_param_name=True)
            return self._pack_list(list_raw_data)
        else:
            self._xlog.error(f"🛑 No list found for [{list_name}]")
            return False

    def update_list(self, current_name: str, new_name: str = None, new_description: str = None) -> dict | bool:
        '''
        Updates a specific list.

        Can be used to change the name and/or description of a list. Can not be used without at least
        one of the new_name or new_description parameters.

        Args:
            current_name: The current name of the list. It's also used as the key to find the list to update.
            new_name: The new name for the list.
            new_description: The new description for the list.

        Returns:
            The updated list details as a JSON object or False if not found.
        '''
        self._log_debug(f"📝 Updating a list for [{current_name}]")
        self.state.read_file()
        if self.state.key_exists(current_name, slugify_param_name=True):
            list_raw_data = dict(self.state.get(current_name, slugify_param_name=True))
            new_data = {
                ** list_raw_data,
                ** {
                    "name": new_name.capitalize() if new_name else list_raw_data.get("name", ""),
                    "description": new_description if new_description else list_raw_data.get("description", ""),
                    "created_at": list_raw_data.get("created_at", ""),
                    "entries": list_raw_data.get("entries", {}) # Entries are not updated in this method, only name and description
                }
            }

            if current_name != new_name and new_name:
                # Implies a key change
                if not self.state.key_exists(new_name, slugify_param_name=True):
                    self.state.set(new_name, self._pack_list(new_data), slugify_param_name=True)
                    self.state.delete(current_name, slugify_param_name=True)
                else:
                    self._xlog.error(f"🛑 Cannot update list name to [{new_name}] because the new name already exists")
                    return False
            # Does not imply a key change, just a name change in the content
            else:
                self.state.set(current_name, self._pack_list(new_data), slugify_param_name=True)

            self.state.write_file()
            self._xlog.info(f"📝 List updated for [{current_name}]: {new_name if current_name != new_name and new_name else ''}")
            return new_data
        else:
            self._xlog.error(f"🛑 No list found for [{current_name}]")
            return False
        
    # ---------- Managing entries in lists ----------

    def add_entry(self, list_name: str, entry_text: str) -> dict |bool:
        '''
        Adds an entry to a specific list.

        Args:
            list_name: The name of the list to add the entry to.
            entry_text: The text of the entry to add.

        Returns:
            A dictionary with the added entry or False if the list is not found or the entry already exists.
        '''
        self._log_debug(f"📝 Adding an entry to the list [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            list_raw_data = dict(self.state.get(list_name, slugify_param_name=True))
            entries = list_raw_data.get("entries", [])
            new_entry = self._pack_entry({
                "created_at": datetime.now().strftime(f"{self.FORMAT_DATE} {self.FORMAT_TIME}"),
                "text": entry_text
            }, list_name=list_name)
            if not new_entry in entries:
                entries.append(new_entry)
            else:
                self._xlog.error(f"🛑 Cannot add entry to the list [{list_name}] because it already exists")
                return False
            self.state.set(list_name, self._pack_list(list_data=list_raw_data, entries_data=entries), slugify_param_name=True)
            self.state.write_file()
            self._xlog.info(f"📝 Entry added to the list [{list_name}]")
            return new_entry
        else:
            self._xlog.error(f"🛑 No list found for [{list_name}]")
            return False
    
    def get_entries(self, list_name: str) -> list | bool:
        '''
        Retrieves the entries of a specific list.

        Args:
            list_name: The name of the list to retrieve the entries from.

        Returns:
            A list containing the entries of the list or False if the list is not found.
        '''
        self._log_debug(f"📝 Retrieving entries for the list [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            list_raw_data = dict(self.state.get(list_name, slugify_param_name=True))
            entries = list_raw_data.get("entries", [])
            self._xlog.info(f"📝 Entries retrieved for the list [{list_name}]")
            return self._pack_entries(entries_data=entries, list_name=list_name)
        else:
            self._xlog.error(f"🛑 No list found for [{list_name}]")
            return False

    def get_entry(self, list_name: str, position: int) -> dict | bool:
        '''
        Retrieves a specific entry from a list by its position in the list (starting from 1).

        Args:
            list_name: The name of the list to retrieve the entry from.
            position: The position of the entry in the list (starting from 1).
        Returns:
            A dictionary containing the entry data or False if the list or entry is not found.
        '''
        self._log_debug(f"📝 Retrieving entry at position [{position}] from the list [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):

            entries = self.state.get(list_name, slugify_param_name=True).get("entries", [])
            if entries and isinstance(entries, list) and position > 0 and position <= len(entries):
                entry_data = entries[position - 1]
                self._log_debug(f"📝 Entry retrieved for the list [{list_name}] at the natural position [{position}]")
                return entry_data
            else:
                self._xlog.error(f"🛑 The list [{list_name}] is empty or the position [{position}] is out of range")
                return False
        else:
            self._xlog.error(f"🛑 No list found for [{list_name}]")
            return False

    def delete_entry(self, list_name: str, position: int) -> dict | bool:
        '''
        Deletes an entry from a specific list by its position in it.

        Args:
            list_name: The name of the list to delete the entry from.
            position: The position of the entry in the list (starting from 1).
        Returns:
            A dictionary with the deleted entry details or False if not found.
        '''
        self._log_debug(f"📝 Deleting an entry at position [{position}] from the list [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            
            entries = self.state.get(list_name, slugify_param_name=True).get("entries", [])
            if entries and isinstance(entries, list) and position > 0 and position <= len(entries):
                entry_data = entries.pop(position - 1)
                self.state.set(list_name, self._pack_list(list_data=self.state.get(list_name, slugify_param_name=True), entries_data=entries), slugify_param_name=True)
                self.state.write_file()
                self._log_debug(f"📝 Entry deleted for the list [{list_name}] at the natural position [{position}]")
                return entry_data
            else:
                self._xlog.error(f"🛑 The list [{list_name}] is empty or the position [{position}] is out of range")
                return False
        else:
            self._xlog.error(f"🛑 No list found for [{list_name}]")
            return False
    
    def update_entry(self, list_name: str, new_text: str, position: int) -> dict | bool:
        '''
        Updates an entry in a specific list by its position.

        Args:
            list_name: The name of the list to update the entry in.
            entry_text: The new text for the entry.
            position: The position of the entry in the list (starting from 1).
        Returns:
            The updated entry data or False if the update failed.
        '''
        self._log_debug(f"📝 Updating entry [{position}] in the list [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            
            entries = self.state.get(list_name, slugify_param_name=True).get("entries", [])
            if entries and isinstance(entries, list) and position > 0 and position <= len(entries):
                entry_data = entries[position - 1]
                entry_data["text"] = new_text
                entries[position - 1] = entry_data
                self.state.set(list_name, self._pack_list(list_data=self.state.get(list_name, slugify_param_name=True), entries_data=entries), slugify_param_name=True)
                self.state.write_file()
                self._log_debug(f"📝 Entry updated for the list [{list_name}] at the natural position [{position}]")
                return entry_data
            else:
                self._xlog.error(f"🛑 The list [{list_name}] is empty or the position [{position}] is out of range")
                return False
        else:
            self._xlog.error(f"🛑 No list found for [{list_name}]")
            return False

    def _pack_list(self, list_data: dict, entries_data: list = None) -> dict:
        return {
            ** self.LIST_TEMPLATE,
            ** {
                "name": list_data.get("name", ""),
                "description": list_data.get("description", ""),
                "created_at": list_data.get("created_at", ""),
                "entries": self._pack_entries(entries_data=entries_data, list_name=list_data.get("name", "")) if entries_data else []
            }
        }

    def _pack_entries(self, entries_data: list, list_name: str) -> list:
        packed_entries = []
        for entry_data in entries_data:
            packed_entries.append(self._pack_entry(data=entry_data, list_name=list_name))
        return packed_entries

    def _pack_entry(self, data: dict, list_name: str) -> dict:
        data["list_name"] = list_name
        return {
            ** self.ENTRY_TEMPLATE,
            ** data
        }
    
    def _remove_list_name_from_entry(self, entry_data: dict) -> dict:
        entry_data.pop("list_name", None)
        return entry_data
    
    def _remove_list_name_from_entries(self, entries_data: list) -> list:
        cleaned_entries = []
        for entry_data in entries_data:
            cleaned_entries.append(self._remove_list_name_from_entry(entry_data))
        return cleaned_entries

    def _build_list_entry_key(self, entry_created_at: str) -> str:
        # assuming that entry_created_at is in the format "YYYY-MM-DD HH:MM" (or f"{self.FORMAT_DATE} {self.FORMAT_TIME}")
        return entry_created_at.replace(" ", "_").replace(":", "-")
