from pitxu.lib.hardware import NetworkReader, PowerReader, SystemReader, ThermalReader


class System:
    """
    Facade of the system readings, for the rest of the app.

    The readings themselves are done by the stateless readers of `lib/hardware`.
    This class keeps the contract that the app already relies on: 0.0 outside Linux where it was so,
    and an exception when a reading fails (the readers return None instead).
    It also owns the display backlight, which is not a reading.
    """

    BYTES: int = SystemReader.BYTES
    KILOBYTES: int = SystemReader.KILOBYTES
    MEGABYTES: int = SystemReader.MEGABYTES
    GIGABYTES: int = SystemReader.GIGABYTES

    @staticmethod
    def get_dsi_backlight_status() -> bool:
        return "0" == System._run_command("cat /sys/class/backlight/11-0045/bl_power")

    @staticmethod
    def set_dsi_backlight_on() -> None:
        System._run_command("sudo -E sh -c 'echo 0 > /sys/class/backlight/11-0045/bl_power'")
    
    @staticmethod
    def set_dsi_backlight_off() -> None:
        System._run_command("sudo -E sh -c 'echo 1 > /sys/class/backlight/11-0045/bl_power'")
    
    # ---- Network ----

    @staticmethod
    def get_default_network_interface() -> dict:
        return NetworkReader.default_interface()

    @staticmethod
    def get_connected_wifi() -> list[dict]:
        """
        Get the list of available WiFi networks
        """
        return System._required(NetworkReader.wifi_networks(), "WiFi networks")

    # The CPU, fan and power readings come from the stateless readers of `lib/hardware`.
    # These keep the contract of this class: 0.0 outside Linux, and an exception when the reading fails.

    @staticmethod
    def get_cpu_temperature() -> float:
        if not System.is_linux():
            return 0.0
        return System._required(ThermalReader.cpu_temperature(), "CPU temperature")

    @staticmethod
    def get_cpu_fan_speed() -> float:
        if not System.is_linux():
            return 0.0
        return System._required(ThermalReader.cpu_fan_rpm(), "CPU fan speed")

    @staticmethod
    def get_cpu_volts() -> float:
        if not System.is_linux():
            return 0.0
        return System._required(PowerReader.cpu_volts(), "CPU voltage")

    @staticmethod
    def get_cpu_amps() -> float:
        if not System.is_linux():
            return 0.0
        return System._required(PowerReader.cpu_amps(), "CPU amperage")

    @staticmethod
    def get_cpu_temp() -> float:
        # Same sensor that `vcgencmd measure_temp` reads.
        return System.get_cpu_temperature()

    @staticmethod
    def get_input_voltage() -> float:
        if not System.is_linux():
            return 0.0
        return System._required(PowerReader.input_voltage(), "input voltage")

    @staticmethod
    def _required(value, description: str):
        if value is None:
            raise Exception(f"Error reading hardware metric: could not read the {description}")
        return value
    
    @staticmethod
    def get_power_throttle(test_bin_value = None) -> list[dict]:
        """
        Returns a dictionary describing the current power throttle state of the system.
        
        https://gist.github.com/Paraphraser/17fb6320d0e896c6446fb886e1207c7e
        https://www.raspberrypi.com/documentation/computers/os.html#get_throttled
        https://forum-raspberrypi.de/forum/thread/47322-vcgencmd-get-throttled-in-python-auswerten/
        https://github.com/HarlemSquirrel/scripts/blob/master/rpi-check-throttling.py
        """
        try:

            if not System.is_linux():
                # Faking it for others.
                return []

            map = {
                0: "Currently under-voltage",
                1: "ARM frequency currently capped",
                2: "Currently throttled",
                3: "Soft temperature limit reached",
                16: "Under-voltage has occurred since last reboot",
                17: "ARM frequency capping has occurred since last reboot",
                18: "Throttling has occurred since last reboot",
                19: "Soft temperature reached since last reboot"
            }

            if test_bin_value is not None:
                throttle_bin = bin(test_bin_value)
            else:
                throttle_bin = bin(System._required(PowerReader.throttled_flags(), "throttle state"))

            report = []
            for bit, description in map.items():
                if len(throttle_bin) > bit and throttle_bin[0 - bit - 1] == '1':
                    report.append({"code": bit, "description": description})
            return report
        except Exception as e:
            raise Exception(f"Error reading throttle state: {e}")
    
    # ---- Host ----

    @staticmethod
    def get_system_uptime() -> float:
        return System._required(SystemReader.uptime_seconds(), "system uptime")

    @staticmethod
    def get_system_load() -> list[float]:
        return System._required(SystemReader.load_average(), "system load")

    @staticmethod
    def get_memory_usage() -> dict:
        return System._required(SystemReader.memory_info(), "memory usage")

    @staticmethod
    def get_pitxu_memory_use() -> dict:
        return System._required(SystemReader.process_memory(), "process memory")

    @staticmethod
    def get_processes_usage(pids_by_name: dict[str, int]) -> dict:
        """
        CPU and memory of every given process, by name. See SystemReader.processes_usage().
        """
        return SystemReader.processes_usage(pids_by_name)

    @staticmethod
    def get_disk_usage() -> dict:
        return System._required(SystemReader.disk_usage("/"), "disk usage")

    @staticmethod
    def memory_use(scale: int = None) -> float:
        return System._required(SystemReader.process_rss(scale=scale if scale is not None else System.MEGABYTES), "process memory")

    # ---- Internals ----

    @staticmethod
    def _run_command(command: str) -> str:
        from subprocess import run, CalledProcessError, CompletedProcess

        error = None
        result: CompletedProcess = None
        try:
            result = run(command, shell=True, capture_output=True)
            if result.returncode != 0:
                raise CalledProcessError(result.returncode, command, output=result.stdout, stderr=result.stderr)
            result = result.stdout.decode('utf-8')
        except CalledProcessError as e:
            error = "Command failed. Return code: " + str(e.returncode) + ". Output: " + e.output.decode('utf-8')
        except FileNotFoundError:
            error = "Command not found: " + command
        except Exception as e:
            error = "Error running command: " + str(e)

        if result is None:
            if error is not None:
                print(error)
                raise Exception(error)
            print("Command did not return any output.")
            raise Exception(f"Command failed: [{command}]")

        return result
    
    @staticmethod
    def is_linux() -> bool:
        return SystemReader.is_linux()
    
    @staticmethod
    def is_macos() -> bool:
        return SystemReader.is_macos()
    
    @staticmethod
    def is_windows() -> bool:
        return SystemReader.is_windows()
