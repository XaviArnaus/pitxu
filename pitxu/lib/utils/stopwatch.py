import time
import uuid
import logging

class Stopwatch():

    _logger: logging
    _stopwatches_running: dict = {}
    _stopwatches_stopped: dict = {}

    FLOAT_ROUND_DECIMALS = 4

    def __init__(self):
        self._logger = logging.getLogger()

    def start(self, name: str = None) -> str:
        if name is None:
            name = uuid.UUID(uuid.uuid4)

        self.reset(name)
        
        self._stopwatches_running[name] = time.perf_counter()

        return name
    
    def continue_or_start(self, name: str) -> str:
        if name not in self._stopwatches_running:
            self._stopwatches_running[name] = time.perf_counter()

        return name

    def stop(self, name: str) -> float:
        if name in self._stopwatches_running:
            self._stopwatches_stopped[name] = time.perf_counter() - self._stopwatches_running[name]
            del self._stopwatches_running[name]
            return self.get(name)
        else:
            self._logger.warning("[Stopwatch] No stopwatch named [" + name + "] to stop.")
            return None
    
    def stop_all(self):
        for name in self._stopwatches_running.keys():
            self.stop(name)
        
    def get(self, name: str) -> float:
        if name in self._stopwatches_stopped:
            return round(self._stopwatches_stopped[name], self.FLOAT_ROUND_DECIMALS)
        else:
            self._logger.warning("[Stopwatch] No stopwatch named [" + name + "] to get.")
            return None
    
    def reset(self, name: str):
        if name in self._stopwatches_running:
            del self._stopwatches_running
        
        if name in self._stopwatches_stopped:
            del self._stopwatches_stopped[name]
    
    def clean(self):
        self._stopwatches_running = {}
        self._stopwatches_stopped = {}
    
    def stop_and_report(self) -> str:
        self.stop_all()

        max_name_width = 0
        for name in self._stopwatches_stopped.keys():
            if len(name) > max_name_width:
                max_name_width = len(name)

        output = []
        for name, diff in self._stopwatches_stopped.items():
            output.append(name.rjust(max_name_width, " ") + ": " + str(round(self._stopwatches_stopped[name], self.FLOAT_ROUND_DECIMALS)))
        
        return "\n".join(output)
