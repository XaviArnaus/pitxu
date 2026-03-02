from pyxavi import Config, Dictionary, Logger
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.xtime import Xtime

import json
import os
import time
import zlib

class JsonLogger(PyXavi):

    _name: str = "undefined_name"
    _filename: str = "log/%s.jsonl"
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
        
        with open(self._filename % self._name, "a") as f:
            for entry in data:
                entry = self.parse_data(entry)
                f.write(json.dumps(entry) + "\n")
    
    def rotate(self):
        """
        Compresses the current log file, deletes the original and starts a new one.
        """

        # File definitions
        current_log_file = self._filename % self._name
        target_compressed_log_file = self._filename % f"{self._name}_{Xtime.now_key()}{self._compressed_extension}"
        
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

        log_dir = os.path.dirname(self._filename)
        now = time.time()

        for filename in os.listdir(log_dir):
            if filename.startswith(self._name) and filename.endswith(self._compressed_extension):
                file_path = os.path.join(log_dir, filename)
                file_age_days = (now - os.path.getmtime(file_path)) / (24 * 3600)
                if file_age_days > self._days_to_keep:
                    os.remove(file_path)

        
    