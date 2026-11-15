import logging
import os
import platform
import re
import time
from subprocess import run

import psutil

logger = logging.getLogger(__name__)


class SystemReader:
    """
    Reads the state of the host: uptime, load, memory, disk and the usage of processes.

    Works on Linux and, where it makes sense, on macOS. What can't be read returns None.
    The only state it keeps is the cache of psutil processes, needed to measure CPU usage between calls.
    """

    BYTES: int = 1
    KILOBYTES: int = 1024
    MEGABYTES: int = 1024 * 1024
    GIGABYTES: int = 1024 * 1024 * 1024

    COMMAND_TIMEOUT_SECONDS: int = 5

    # The fields of /proc/meminfo that we want (values in kilobytes).
    MEMINFO_FIELDS = ["MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached", "SwapTotal", "SwapFree"]

    # psutil.Process objects by pid, kept between calls because cpu_percent() measures since the previous call on the same object.
    _process_cache: dict = {}

    # ---- Platform ----

    @staticmethod
    def is_linux() -> bool:
        return platform.system() == "Linux"

    @staticmethod
    def is_macos() -> bool:
        return platform.system() == "Darwin"

    @staticmethod
    def is_windows() -> bool:
        return platform.system() == "Windows"

    # ---- Host ----

    @staticmethod
    def uptime_seconds() -> float | None:
        """
        Seconds since the host booted. Linux and macOS.
        """
        try:
            if SystemReader.is_linux():
                with open("/proc/uptime", "r") as file:
                    return float(file.read().split()[0])
            if SystemReader.is_macos():
                # "{ sec = 1710000000, usec = 123456 } Mon Mar  9 ..."
                output = SystemReader._run(["sysctl", "-n", "kern.boottime"])
                match = re.search(r"sec\s*=\s*(\d+)", output or "")
                return time.time() - int(match.group(1)) if match else None
        except Exception as e:
            logger.debug(f"Could not read the uptime: {e}")
        return None

    @staticmethod
    def load_average() -> list[float] | None:
        """
        The load averages of the past 1, 5, and 15 minutes.
        """
        try:
            return [float(value) for value in os.getloadavg()]
        except Exception as e:
            logger.debug(f"Could not read the load average: {e}")
            return None

    @staticmethod
    def memory_info() -> dict | None:
        """
        System memory in kilobytes, from /proc/meminfo. Linux only.
        """
        try:
            with open("/proc/meminfo", "r") as file:
                lines = file.read().splitlines()
        except Exception as e:
            logger.debug(f"Could not read /proc/meminfo: {e}")
            return None

        info = {}
        for line in lines:
            parts = line.split(":")
            if len(parts) == 2 and parts[0].strip() in SystemReader.MEMINFO_FIELDS:
                info[parts[0].strip()] = int(parts[1].strip().split()[0])  # Numeric value, ignoring units
        return info

    @staticmethod
    def disk_usage(path: str = "/") -> dict | None:
        """
        Usage of the partition of the given path, as `df -h` shows it (human readable strings).
        """
        output = SystemReader._run(["df", "-h", path])
        if output is None:
            return None
        lines = output.splitlines()
        if len(lines) < 2:
            logger.debug("Unexpected output from df command")
            return None
        # The second line contains the data we need
        parts = lines[1].split()
        if len(parts) < 6:
            logger.debug("Unexpected output format from df command")
            return None
        return {
            "filesystem": parts[0],
            "size": parts[1],
            "used": parts[2],
            "available": parts[3],
            "use_percent": parts[4],
            "mounted_on": parts[5]
        }

    # ---- Processes ----

    @staticmethod
    def process_memory(pid: int = None) -> dict | None:
        """
        Memory of a process (the current one by default), in bytes.
        """
        try:
            mem_info = psutil.Process(pid).memory_info()
            return {
                "resident_set_size": mem_info.rss,  # Resident Set Size: the non-swapped physical memory the process is using.
                "virtual_memory_size": mem_info.vms,  # Virtual Memory Size: the total amount of virtual memory used by the process.
            }
        except Exception as e:
            logger.debug(f"Could not read the memory of the process [{pid}]: {e}")
            return None

    @staticmethod
    def process_rss(pid: int = None, scale: int = MEGABYTES) -> float | None:
        """
        Resident memory of a process (the current one by default), in the given scale (megabytes by default).
        """
        memory = SystemReader.process_memory(pid)
        return None if memory is None else float(memory["resident_set_size"] / scale)

    @staticmethod
    def processes_usage(pids_by_name: dict[str, int]) -> dict:
        """
        CPU and memory of every given process, by name.

        - cpu_percent: average since the previous call (so, since the previous metrics log). None the first time a process is seen.
            100 is one full core, so it can go over 100 with several threads.
        - cpu_time_seconds: cumulative user + system CPU time. Differences between logs also give the usage, and they don't hide bursts.
        - rss: resident memory. Shared pages (libraries, forked memory) are counted in every process, so the sum overstates.
        - pss: proportional memory, shared pages split between the processes using them. The sum of all pss is the real total.
            Only on Linux. On macOS "uss" (memory only this process has) is given instead.
        """
        usage = {}
        seen_pids = set()

        for name, pid in pids_by_name.items():
            if pid is None:
                continue
            try:
                process = SystemReader._process_cache.get(pid)
                first_time = process is None
                if first_time:
                    process = psutil.Process(pid)
                    process.cpu_percent(None)  # Sets the baseline for the next call.
                    SystemReader._process_cache[pid] = process
                seen_pids.add(pid)

                with process.oneshot():
                    cpu_times = process.cpu_times()
                    entry = {
                        "pid": pid,
                        "cpu_percent": None if first_time else process.cpu_percent(None),
                        "cpu_time_seconds": round(cpu_times.user + cpu_times.system, 1),
                        "threads": process.num_threads(),
                        "rss": process.memory_info().rss,
                    }
                try:
                    full = process.memory_full_info()
                    for field in ("pss", "uss"):
                        if hasattr(full, field):
                            entry[field] = getattr(full, field)
                except (psutil.AccessDenied, NotImplementedError):
                    pass
                usage[name] = entry

            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                usage[name] = {"pid": pid, "error": type(e).__name__}

        # Forget the processes that are gone.
        for pid in [p for p in SystemReader._process_cache if p not in seen_pids]:
            del SystemReader._process_cache[pid]

        return usage

    # ---- Internals ----

    @staticmethod
    def _run(command: list[str]) -> str | None:
        try:
            result = run(command, capture_output=True, timeout=SystemReader.COMMAND_TIMEOUT_SECONDS)
            if result.returncode != 0:
                logger.debug(f"[{' '.join(command)}] failed ({result.returncode}): {result.stderr.decode(errors='replace').strip()}")
                return None
            return result.stdout.decode(errors="replace")
        except Exception as e:
            logger.debug(f"[{' '.join(command)}] could not run: {e}")
            return None
