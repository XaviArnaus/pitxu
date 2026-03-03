from pyxavi import Config, Dictionary, Logger
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.xtime import Xtime

import json
import os
import time
import zlib
from datetime import datetime

class JsonLogger(PyXavi):

    _name: str = "undefined_name"
    _directory: str = "log"
    _filename: str = "%s.jsonl"
    _compressed_extension: str = ".gz"
    _days_to_keep: int = 7

    def __init__(self, config: Config = None, params: Dictionary = None, **kwargs):
        super(JsonLogger, self).init_pyxavi(config=config, params=params)

        self._xlog.debug("Initializing JsonLogger")

        if self._xparams.key_exists("maintenance_logger_name"):
            self._name = self._xparams.get("maintenance_logger_name")
        elif kwargs.get("name") is not None:
            self._name = kwargs.get("name")

        self._initialize()
    
    def _initialize(self):
        pass

    def parse_data(self, data: dict) -> dict:
        return data

    def log(self, data: dict | list[dict]):

        if isinstance(data, dict):
            data = [data]
        
        with open(os.path.join(self._directory, self._filename % self._name), "a") as f:
            for entry in data:
                entry = self.parse_data(entry)
                f.write(json.dumps(entry) + "\n")
    
    def rotate(self):
        """
        Compresses the current log file, deletes the original and starts a new one.
        """

        # File definitions
        current_log_file = os.path.join(self._directory, self._filename % self._name)
        target_compressed_log_file = os.path.join(self._directory, self._filename % f"{self._name}_{Xtime.now_key()}{self._compressed_extension}")
        
        # Compress the current log file
        self._compress_and_delete(current_log_file, target_compressed_log_file)

        # Start a new log file
        with open(current_log_file, "w") as f:
            f.write("")
        
        # Cleanup old logs
        self._cleanup_old_logs()
    
    def _compress_and_delete(self, source, dest):
        """
        Read the data from source, compress it, write it to dest and delete source
        """
        with open(source, "rb") as sf:
            data = sf.read()
            compressed = zlib.compress(data, 9)
            with open(dest, "wb") as df:
                df.write(compressed)
        os.remove(source)
        
    def _cleanup_old_logs(self):
        """
        Deletes log files older than the defined retention period.
        """

        log_dir = self._directory
        now = time.time()

        for filename in os.listdir(log_dir):
            if filename.startswith(self._name) and filename.endswith(self._compressed_extension):
                file_path = os.path.join(log_dir, filename)
                file_age_days = (now - os.path.getmtime(file_path)) / (24 * 3600)
                if file_age_days > self._days_to_keep:
                    os.remove(file_path)

    def get_logs(self, start_time: datetime, end_time: datetime) -> list[dict]:
        """
        Retrieves log entries between the specified start and end times.
        """
        logs = self._load_log_files_within_time_range(start_time, end_time)

        # Sort logs by timestamp
        logs.sort(key=lambda x: x.get("timestamp", ""))

        return logs
    
    def _load_log_files_within_time_range(self, start_time: datetime, end_time: datetime) -> list[dict]:
        """
        Loads all log entries from the log files.
        """
        logs = []
        related_files = self._get_related_files(start_time, end_time)

        for file_path in related_files:

            if file_path.endswith(self._compressed_extension):
                with open(file_path, "rb") as f:
                    compressed_data = f.read()
                    data = zlib.decompress(compressed_data).decode("utf-8")
            else:
                with open(file_path, "r") as f:
                    data = f.read()

            for line in data.splitlines():
                entry = json.loads(line)
                entry_time = entry.get("timestamp", None)
                if entry_time is not None:
                    entry_time = datetime.fromisoformat(entry_time)
                    if start_time <= entry_time <= end_time:
                        logs.append(entry)
        return logs

    def _get_related_files(self, start_date: datetime, end_date: datetime) -> list[str]:
        """
        Returns the list of log files that may contain entries between the specified start and end dates.
        """
        related_files = []
        log_dir = self._directory

        for filename in os.listdir(log_dir):
            if filename.startswith(self._name) and filename.endswith(self._compressed_extension):
                file_path = os.path.join(log_dir, filename)
                file_date_str = filename[len(self._name)+1:-len(self._compressed_extension)]
                try:
                    file_date = datetime.strptime(file_date_str, "%Y-%m-%d_%H-%M-%S-%f")
                    if start_date <= file_date <= end_date:
                        related_files.append(file_path)
                except ValueError:
                    continue
        
        # If the end date is today, we also need to include the current log file
        if end_date.date() == datetime.now().date():
            current_log_file = os.path.join(self._directory, self._filename % self._name)
            if os.path.exists(current_log_file):
                related_files.append(current_log_file)

        return related_files
        
    