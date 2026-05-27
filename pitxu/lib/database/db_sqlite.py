from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

import sqlite3
import os

class DbSqlite(PyXavi):

    # Connection to the SQLite database.
    connection: sqlite3.Connection = None
    # Cursor for executing SQL commands. 
    # This is not thread-safe, so it should be created and used within the same thread.
    cursor: sqlite3.Cursor = None

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_DB_PATH = "db/"
    DEFAULT_DB_FILENAME = "pitxu.db"
    DEFAULT_DB_MIGRATIONS_PATH = "migrations/"

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(DbSqlite, self).init_pyxavi(config=config, params=params)

        self._xlog.debug("Initializing SQLite")

        # We should be able to initialize an arbitrary DB file.
        # Therefore, we accept receiving the DB filename via params, and use it instead of the one given by the config if provided. This allows us to have multiple DB files if needed, for example for testing purposes.
        db_filename = self._xconfig.get("database.sqlite.filename", self.DEFAULT_DB_FILENAME)
        if params is not None and params.key_exists("db_filename"):
            db_filename = params.get("db_filename")
            self._xlog.debug(f"Using DB filename from received params: {db_filename}")
            self._xconfig.set("database.sqlite.filename", db_filename)

        # Now build the full DB file path
        db_filepath = os.path.join(
            self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH),
            self._xconfig.get("database.sqlite.path", self.DEFAULT_DB_PATH), 
            db_filename)
        
        # Now initialize it: if the path or the file do not exist, create them.
        self._initialize_file(db_filepath)

        # Now place the connection and the cursor, and define the Row factory to have dict-like rows.
        self.connection = sqlite3.connect(db_filepath, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self._xlog.debug(f"🗄️ Connected to SQLite database at {db_filepath}, and ready to hold queries.")

        self._log_debug("🗄️ SQLite initialization complete")
    
    def _initialize_file(self, db_filepath: str):
        if not os.path.exists(db_filepath):
            self._xlog.debug(f"🗄️ Database file {db_filepath} does not exist. Creating it.")
            os.makedirs(os.path.dirname(db_filepath), exist_ok=True)
            open(db_filepath, 'a').close()
        else:
            self._xlog.debug(f"🗄️ Database file {db_filepath} already exists. Using it.")
    
    def migrate_db(self):
        """Run database migrations."""

        self._xlog.debug("🗄️ Running database migrations if needed")

        def get_script_version(path):
            return int(path.split('_')[0].split('/')[1])

        current_version = self.cursor.execute('pragma user_version').fetchone()[0]
        self._xlog.debug(f"🗄️ Current database version: {current_version}")

        migrations_path = os.path.join("", self._xconfig.get("database.sqlite.migrations_path", self.DEFAULT_DB_MIGRATIONS_PATH))
        migration_files = list(os.listdir(migrations_path))
        for migration in sorted(migration_files):
            path = os.path.join(migrations_path, migration)
            migration_version = get_script_version(path)

            if migration_version > current_version:
                self._xlog.debug("🗄️ Applying migration {0}".format(migration_version))
                with open(path, mode='r') as f:
                    self.cursor.executescript(f.read())
                    self._xlog.debug("🗄️ Database now at version {0}".format(migration_version))
            else:
                self._xlog.debug("🗄️ Migration {0} already applied. Skipped.".format(migration_version))