from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.abstract.pyxavi import PyXavi

import sqlite3
import os
import re
from datetime import datetime

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
    DEFAULT_DB_BACKUPS_PATH = "backups/"
    DEFAULT_DB_BACKUPS_KEEP = 5
    DEFAULT_BUSY_TIMEOUT_SECONDS = 30

    # The migration files are named `0001_something.sql`. Anything else in the folder is not a migration.
    MIGRATION_FILE_PATTERN = re.compile(r"^(\d+)_.*\.sql$")

    VERBOSE_DEBUG: bool = False

    _db_filepath: str = None

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
        self._db_filepath = db_filepath

        # Now initialize it: if the path or the file do not exist, create them.
        self._initialize_file(db_filepath)

        # Now place the connection and the cursor, and define the Row factory to have dict-like rows.
        # Several processes (Main, Support...) open this same file, so they wait for each other instead of failing at once.
        self.connection = sqlite3.connect(
            db_filepath,
            check_same_thread=False,
            timeout=float(self._xconfig.get("database.sqlite.busy_timeout_seconds", self.DEFAULT_BUSY_TIMEOUT_SECONDS)))
        self.connection.row_factory = sqlite3.Row
        # WAL lets one process read while another writes.
        if self._xconfig.get("database.sqlite.wal", True):
            self.connection.execute("PRAGMA journal_mode=WAL")
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

    def close(self):
        self._xlog.debug("🗄️ Closing SQLite database connection")

        try:

            if self.cursor is not None:
                self.cursor.close()
                self._xlog.debug("🗄️ SQLite database cursor closed")

            if self.connection is not None:
                self.connection.close()
                self._xlog.debug("🗄️ SQLite database connection closed")

        except Exception as e:
            self._xlog.error("🛑 Error while closing SQLite database connection: " + str(e))
            self._xlog.debug(full_stack())

    def protect_tables_from_writes(self, tables: list[str]):
        """
        Makes SQLite itself refuse to write (insert, update, delete, drop, alter) in the given tables
        through THIS connection. Reading is not affected.

        It is not a convention but a rule enforced by the database: the code that has no business writing
        there can't do it, even by mistake. A refused statement raises sqlite3.DatabaseError ("not authorized").
        """
        protected = {table.lower() for table in tables}
        write_actions = {
            sqlite3.SQLITE_INSERT,
            sqlite3.SQLITE_UPDATE,
            sqlite3.SQLITE_DELETE,
            sqlite3.SQLITE_DROP_TABLE,
            sqlite3.SQLITE_ALTER_TABLE,
        }

        def authorizer(action, arg1, arg2, database_name, source):
            if action in write_actions and arg1 is not None and arg1.lower() in protected:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        self.connection.set_authorizer(authorizer)
        self._log_debug(f"🗄️ Writes are not allowed from this connection in: {', '.join(sorted(protected))}")

    def backup_db(self, label: str) -> str | None:
        """
        Copies the database into the backups folder, using the SQLite backup API: the copy is consistent
        even if the database is in use. Keeps only the newest `database.sqlite.backups_keep` copies.

        Args:
            label (str): What the backup is for, part of the filename. For example "v1-to-v2".

        Returns:
            str | None: The path of the backup, or None if it could not be done.
        """
        try:
            backups_dir = os.path.join(
                os.path.dirname(self._db_filepath),
                self._xconfig.get("database.sqlite.backups_path", self.DEFAULT_DB_BACKUPS_PATH))
            os.makedirs(backups_dir, exist_ok=True)

            stem, extension = os.path.splitext(os.path.basename(self._db_filepath))
            backup_path = os.path.join(backups_dir, f"{stem}-{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}{extension}")

            destination = sqlite3.connect(backup_path)
            try:
                self.connection.backup(destination)
            finally:
                destination.close()
            self._xlog.info(f"🗄️ Database backup created at {backup_path}")

            # Don't fill the disk: keep the newest ones.
            keep = int(self._xconfig.get("database.sqlite.backups_keep", self.DEFAULT_DB_BACKUPS_KEEP))
            backups = sorted(
                (os.path.join(backups_dir, name) for name in os.listdir(backups_dir)
                    if name.startswith(stem + "-") and name.endswith(extension)),
                key=os.path.getmtime,
                reverse=True)
            for old_backup in backups[keep:]:
                os.remove(old_backup)
                self._xlog.debug(f"🗄️ Removed old database backup {old_backup}")

            return backup_path
        except Exception as e:
            self._xlog.error(f"🛑 Could not create the database backup: {e}")
            self._xlog.debug(full_stack())
            return None

    def _list_migrations(self) -> list[tuple[int, str]]:
        """ The migration scripts as (version, path), in order. Files that are not migrations are ignored. """
        migrations_path = os.path.join("", self._xconfig.get("database.sqlite.migrations_path", self.DEFAULT_DB_MIGRATIONS_PATH))
        migrations = []
        for filename in os.listdir(migrations_path):
            found = self.MIGRATION_FILE_PATTERN.match(filename)
            if found:
                migrations.append((int(found.group(1)), os.path.join(migrations_path, filename)))
        return sorted(migrations)

    def migrate_db(self) -> int:
        """
        Run database migrations.

        If there is any pending, the database is backed up first (unless it is brand new).
        A migration that fails is rolled back, and the error is raised.

        Returns:
            int: The number of migrations applied.
        """

        self._xlog.debug("🗄️ Running database migrations if needed")

        current_version = self.cursor.execute('pragma user_version').fetchone()[0]
        self._xlog.debug(f"🗄️ Current database version: {current_version}")

        pending = [(version, path) for version, path in self._list_migrations() if version > current_version]
        if not pending:
            self._xlog.debug("🗄️ No pending migrations.")
            return 0

        # An empty database has nothing to lose.
        if current_version > 0:
            self.backup_db(f"v{current_version}-to-v{pending[-1][0]}")

        for version, path in pending:
            self._xlog.info(f"🗄️ Applying migration {version}: {os.path.basename(path)}")
            try:
                with open(path, mode='r') as f:
                    self.connection.executescript(f.read())
            except Exception as e:
                self._xlog.error(f"🛑 Migration {version} failed, rolling it back: {e}")
                if self.connection.in_transaction:
                    self.connection.rollback()
                raise

            new_version = self.cursor.execute('pragma user_version').fetchone()[0]
            if new_version != version:
                self._xlog.warning(f"🟠 After the migration {version} the database is at version {new_version}. Does the script set `PRAGMA user_version`?")
            self._xlog.info(f"🗄️ Database now at version {new_version}")

        return len(pending)

# ISSUE:
#
# Apparently there is a memory leak when we interact with the STT and then close it.
# If we don't interact with the STT the leak is not present.
# It smells like when we plot the audio, some resources are not released. Also, interesting the name of the semaphore leaked:
#
# /Users/xarnaus/.pyenv/versions/3.13.11/lib/python3.13/multiprocessing/resource_tracker.py:400: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown: {'/mp-p4q984wz'}
#  warnings.warn(
