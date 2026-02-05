
from pyxavi import Storage, Config, Dictionary, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command

from datetime import datetime


class Lists(PyXavi, Command):

    LIST_FILENAME = "lists.yaml"

    FORMAT_DATE = "%Y-%m-%d"  # E.g., 2023-12-25
    FORMAT_TIME = "%H:%M"     # E.g., 14:30
    DATETIME_KEY_FORMAT = f"{FORMAT_DATE}_{FORMAT_TIME.replace(':', '-')}"  # E.g., 2023-12-25_14-30

    LIST_TEMPLATE = {
        "name": "",
        "description": "",
        "created_at": "",
    }

    ENTRY_TEMPLATE = {
        "created at": "",
        "text": ""
    }

    state: Storage = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Lists, self).init_pyxavi(config=config, params=params)

        self.state = self._state = Storage(filename=self._xconfig.get("storage.path") + self.LIST_FILENAME)

    def create_list(self, list_name: str, list_description: str = None, list_datetime: str = None, list_entries: dict = None) -> bool:
        '''
        Creates a list with the given name and description.

        Args:
            list_name: The name of the list to create.
            list_description: The description of the list to create.
            list_datetime: Optional, internal use. The date and time of the list to create.Ignored for new lists.
            list_entries: Optional, internal use. The entries of the list to create. Ignored for new lists.

        Returns:
            A boolean indicating success or failure.
        '''
        self._log_debug(f"📝 Creating a list for [{list_name}]")

        # First check if there are existing lists for that key
        if self.state.key_exists(list_name):
            self._xlog.debug(f"📝 List already exists for [{list_name}]")
            return False

        self.state.set(list_name, self._pack_list({
            "name": list_name.capitalize(),
            "description": list_description,
            "created_at": datetime.now().strftime(self.FORMAT_DATE) if not list_datetime else list_datetime,
            "entries": list_entries if list_entries else {}
        }), slugify_param_name=True)
        self.state.write_file()
        self._xlog.info(f"📝 List created for [{list_name}]")

        return True

    def delete_list(self, list_name: str) -> bool:
        '''
        Deletes a specific list.
        
        Args:
            list_name: The name of the list to delete.

        Returns:
            A boolean indicating success or failure.
        '''
        self._log_debug(f"📝 Deleting a list for [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            self.state.delete(list_name, slugify_param_name=True)
            self.state.write_file()
            self._xlog.info(f"📝 List deleted for [{list_name}]")
            return True
        else:
            self._log_debug(f"📝 No list found for [{list_name}]")
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
            self._log_debug(f"📝 No list found for [{list_name}]")
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
                    self._log_debug(f"📝 Cannot update list name to [{new_name}] because the new name already exists")
                    return False
            # Does not imply a key change, just a name change in the content
            else:
                self.state.set(current_name, self._pack_list(new_data), slugify_param_name=True)

            self.state.write_file()
            self._xlog.info(f"📝 List updated for [{current_name}]: {new_name if current_name != new_name and new_name else ''}")
            return new_data
        else:
            self._log_debug(f"📝 No list found for [{current_name}]")
            return False
        
    # ---------- Managing entries in lists ----------

    def add_entry(self, list_name: str, entry_text: str) -> bool:
        '''
        Adds an entry to a specific list.

        Args:
            list_name: The name of the list to add the entry to.
            entry_text: The text of the entry to add.

        Returns:
            A boolean indicating success or failure.
        '''
        self._log_debug(f"📝 Adding an entry to the list [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            list_raw_data = dict(self.state.get(list_name, slugify_param_name=True))
            entries = list_raw_data.get("entries", {})
            new_entry_key = self._build_list_entry_key(list_name)
            if not new_entry_key in entries:
                entries[new_entry_key] = {
                    "created at": datetime.now().strftime(f"{self.FORMAT_DATE} {self.FORMAT_TIME}"),
                    "text": entry_text
                }
            else:
                self._log_debug(f"📝 Cannot add entry to the list [{list_name}] because the entry key [{new_entry_key}] already exists")
                return False
            self.state.set(list_name, self._pack_list(list_data=list_raw_data, entries_data=entries), slugify_param_name=True)
            self.state.write_file()
            self._xlog.info(f"📝 Entry added to the list [{list_name}]")
            return True
        else:
            self._log_debug(f"📝 No list found for [{list_name}]")
            return False
    
    def get_entries(self, list_name: str) -> dict | bool:
        '''
        Retrieves the entries of a specific list.

        Args:
            list_name: The name of the list to retrieve the entries from.

        Returns:
            A dictionary containing the entries of the list or False if the list is not found.
        '''
        self._log_debug(f"📝 Retrieving entries for the list [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            list_raw_data = dict(self.state.get(list_name, slugify_param_name=True))
            entries = list_raw_data.get("entries", {})
            self._xlog.info(f"📝 Entries retrieved for the list [{list_name}]")
            return self._pack_entries(entries)
        else:
            self._log_debug(f"📝 No list found for [{list_name}]")
            return False

    def get_entry(self, list_name: str, by_position: int | None = None, by_datetime: str | None = None) -> dict | bool:
        '''
        Retrieves a specific entry from a list by its position or creation date and time.

        Can be used to retrieve an entry by its position in the list (starting from 1) 
        or by its creation date and time in the format "YYYY-MM-DD HH:MM".
        At least one of the by_position or by_datetime parameters must be provided, but not both.

        Args:
            list_name: The name of the list to retrieve the entry from.
            by_position: The position of the entry in the list (starting from 1).
            by_datetime: The creation date and time of the entry in the format "YYYY-MM-DD HH:MM".

        Returns:
            A dictionary containing the entry data or False if the list or entry is not found.
        '''
        self._log_debug(f"📝 Retrieving entry for the list [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):

            entry_key = None
            if by_position is not None:
                entry_key = self._get_entry_key_by_position(list_name, by_position)
            elif by_datetime is not None:
                entry_key = self._get_entry_key_by_datetime(list_name, by_datetime)

            if entry_key is not None:
                entry_data = self.state.get(entry_key, slugify_param_name=True)
                self._xlog.info(f"📝 Entry retrieved for the list [{list_name}] by [{'Time' if by_datetime else 'Position'}]")
                return entry_data
            else:
                self._log_debug(f"📝 You must specify either 'by_position' or 'by_datetime', but not either of them.")
                return False
        else:
            self._log_debug(f"📝 No entry found for the list [{list_name}]")
            return False

    def delete_entry(self, list_name: str, by_position: int | None = None, by_datetime: str | None = None) -> bool:
        '''
        Deletes an entry from a specific list.

        Args:
            list_name: The name of the list to delete the entry from.
            by_position: The position of the entry in the list (starting from 1).
            by_datetime: The creation date and time of the entry in the format "YYYY-MM-DD HH:MM".
        Returns:
            A boolean indicating success or failure.
        '''
        self._log_debug(f"📝 Deleting an entry from the list [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            entry_key = None
            if by_position is not None:
                entry_key = self._get_entry_key_by_position(list_name, by_position)
            elif by_datetime is not None:
                entry_key = self._get_entry_key_by_datetime(list_name, by_datetime)

            if entry_key is not None:
                self.state.delete(entry_key, slugify_param_name=True)
            else:
                self._log_debug(f"📝 You must specify either 'by_position' or 'by_datetime', but not either of them.")
                return False
        else:
            self._log_debug(f"📝 No list found for [{list_name}]")
            return False
    
    def update_entry(self, list_name: str, entry_text: str, by_position: int | None = None, by_datetime: str | None = None) -> dict | bool:
        '''
        Updates an entry in a specific list.

        Args:
            list_name: The name of the list to update the entry in.
            entry_text: The new text for the entry.
            by_position: The position of the entry in the list (starting from 1).
            by_datetime: The creation date and time of the entry in the format "YYYY-MM-DD HH:MM".

        Returns:
            The updated entry data or False if the update failed.
        '''
        self._log_debug(f"📝 Updating an entry in the list [{list_name}]")
        self.state.read_file()
        if self.state.key_exists(list_name, slugify_param_name=True):
            entry_key = None
            if by_position is not None:
                entry_key = self._get_entry_key_by_position(list_name, by_position)
            elif by_datetime is not None:
                entry_key = self._get_entry_key_by_datetime(list_name, by_datetime)

            if entry_key is not None:
                if self.state.key_exists(entry_key, slugify_param_name=True):
                    entry_data = self.state.get(entry_key, slugify_param_name=True)
                    entry_data["text"] = entry_text
                    self.state.set(entry_key, entry_data, slugify_param_name=True)
                    self.state.write_file()
                    self._xlog.info(f"📝 Entry updated for the list [{list_name}] by [{'Time' if by_datetime else 'Position'}]")
                    return entry_data
                else:
                    self._log_debug(f"📝 No entry found with key [{entry_key}] in the list [{list_name}]")
                    return False
            else:
                self._log_debug(f"📝 You must specify either 'by_position' or 'by_datetime', but not either of them.")
                return False
        else:
            self._log_debug(f"📝 No list found for [{list_name}]")
            return False

    def _pack_list(self, list_data: dict, entries_data: dict = None) -> dict:
        return {
            ** self.LIST_TEMPLATE,
            ** {
                "name": list_data.get("name", ""),
                "description": list_data.get("description", ""),
                "created_at": list_data.get("created_at", ""),
                "entries": self._pack_entries(entries_data) if entries_data else {}
            }
        }
    
    def _pack_entries(self, entries_data: dict) -> dict:
        packed_entries = {}
        for entry_key, entry_data in entries_data.items():
            packed_entries[entry_key] = self._pack_entry(entry_data)
        return packed_entries

    def _pack_entry(self, data: dict) -> dict:
        return {
            ** self.ENTRY_TEMPLATE,
            ** data
        }

    def _build_list_entry_key(self, list_name: str, entry_created_at: str = None) -> str:
        if entry_created_at:
            # assuming that entry_created_at is in the format "YYYY-MM-DD HH:MM" (or f"{self.FORMAT_DATE} {self.FORMAT_TIME}")
            datetime_str = entry_created_at.replace(" ", "_").replace(":", "-")
            return f"{list_name}-entry-{datetime_str}"
        return f"{list_name}-entry-{datetime.now().strftime(f'{self.DATETIME_KEY_FORMAT}')}"
    
    def _get_entry_key_by_position(self, list_name: str, position: int) -> str | None:
        '''
        Retrieves the entry key of a specific entry in a list by its position.

        Args:
            list_name: The name of the list to retrieve the entry key from.
            position: The position of the entry in the list (starting from 1).
        Returns:
            The entry key of the entry at the specified position or None if not found.
        '''
        entries = self.get_entries(list_name)
        if entries and isinstance(entries, dict):
            entry_keys = list(entries.keys())
            if position > 0 and position <= len(entry_keys):
                return entry_keys[position - 1]
        return None
    
    def _get_entry_key_by_datetime(self, list_name: str, entry_datetime: str) -> str | None:
        '''
        Retrieves the entry key of a specific entry in a list by its creation date and time.

        Args:
            list_name: The name of the list to retrieve the entry key from.
            entry_datetime: The creation date and time of the entry in the format "YYYY-MM-DD HH:MM".

        Returns:
            The entry key of the entry with the specified creation date and time or None if not found.
        '''
        entries = self.get_entries(list_name)
        if entries and isinstance(entries, dict):
            for entry_key, entry_data in entries.items():
                if dict(entry_data).get("created_at") == entry_datetime:
                    return entry_key
        return None