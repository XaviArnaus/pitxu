import psutil, os, platform

class System:

    BYTES: int = 1
    KILOBYTES: int = 1024
    MEGABYTES: int = 1024 * 1024
    GIGABYTES: int = 1024 * 1024 * 1024
    
    @staticmethod
    def get_dsi_backlight_status() -> bool:
        return "0" == System._run_command("cat /sys/class/backlight/11-0045/bl_power")

    @staticmethod
    def set_dsi_backlight_on() -> None:
        System._run_command("sudo -E sh -c 'echo 0 > /sys/class/backlight/11-0045/bl_power'")
    
    @staticmethod
    def set_dsi_backlight_off() -> None:
        System._run_command("sudo -E sh -c 'echo 1 > /sys/class/backlight/11-0045/bl_power'")
    
    @staticmethod
    def get_default_network_interface() -> dict:
        import ifcfg

        data = ifcfg.default_interface()
        if data is None:
            return None
        return {
            "name": data.get("name"),
            "ip": data.get("inet"),
            "netmask": data.get("netmask"),
            "broadcast": data.get("broadcast"),
            "mac": data.get("ether"),
        }
    
    @staticmethod
    def get_connected_wifi() -> list[dict]:
        """
        Get the list of available WiFi networks
        """
        os = platform.system()
        networks = []

        if os.lower() == "linux":
            # Use nmcli to get WiFi networks
            result = System._run_command("nmcli -t -f SSID,SECURITY,SIGNAL dev wifi")
            lines = result.strip().split('\n')
            for line in lines:
                parts = line.split(':')
                if len(parts) >= 3:
                    ssid = parts[0]
                    security = parts[1]
                    signal = parts[2]
                    networks.append({
                        "ssid": ssid,
                        "security": security,
                        "signal": signal
                    })
        elif os.lower() == "windows":
            # Use netsh to get WiFi networks
            wifi = System._run_command("netsh WLAN show interfaces")
            # data = wifi.decode('utf-8')
            lines = wifi.split('\n')
            for line in lines:
                if "SSID" in line:
                    ssid = line.split(':')[1].strip()
                    networks.append({
                        "ssid": ssid
                    })
        elif os.lower() == "darwin":
            import macwifi

            data = macwifi.get_wifi_info()
            lines = data.split('\n')
            info = {}
            for line in lines:
                if "SSID" in line and "BSSID" not in line:
                    ssid = line.split(':')[1].strip()
                    info["ssid"] = ssid
                if "link auth" in line:
                    security = line.split(':')[1].strip()
                    info["security"] = security

            if info:
                networks.append(info)
                info = {}
        else:
            # Unsupported OS for WiFi scanning
            pass
        # dd(networks)
        return networks
    
    @staticmethod
    def get_cpu_temperature() -> float:
        return round(int(System._run_command("cat /sys/class/thermal/thermal_zone*/temp")) / 1000, 1)
    
    @staticmethod
    def get_cpu_fan_speed() -> float:
        return int(System._run_command("cat /sys/class/hwmon/hwmon*/fan1_input"))
    
    @staticmethod
    def get_cpu_volts() -> float: 
        return float(System._read_hardware_metric(["vcgencmd", "pmic_read_adc", "VDD_CORE_V"], 'V')) # return current cpu voltage

    @staticmethod
    def get_cpu_amps() -> float:
        return float(System._read_hardware_metric(["vcgencmd", "pmic_read_adc", "VDD_CORE_A"], 'A')) # reurn current cpu amperage

    @staticmethod
    def get_cpu_temp() -> float:
        return float(System._read_hardware_metric(["vcgencmd", "measure_temp"], "'C")) # return current cpu temp

    @staticmethod
    def get_input_voltage() -> float:
        return float(System._read_hardware_metric(["vcgencmd", "pmic_read_adc", "EXT5V_V"], 'V')) # return input voltage
    
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
                throttle_str = System._read_hardware_metric(["vcgencmd", "get_throttled"], '') # no characters to strip
                throttle_bin = bin(int(throttle_str, 0)) # convert the cleaned-up string to an integer (base 16) and then to binary

            report = []
            for bit, description in map.items():
                if len(throttle_bin) > bit and throttle_bin[0 - bit - 1] == '1':
                    report.append({"code": bit, "description": description})
            return report
        except Exception as e:
            raise Exception(f"Error reading throttle state: {e}")
    
    @staticmethod
    def get_system_uptime() -> float:
        if System.is_linux():
            return float(System._run_command("cat /proc/uptime").split()[0]) # returns system uptime in seconds
        elif System.is_macos():
            return float(System._run_command("sysctl -n kern.boottime").split('}')[0].split('=')[2].strip()) # returns system uptime in seconds
        else:
            raise Exception("Unsupported OS for getting system uptime")
    
    @staticmethod
    def get_system_load() -> list[float]:
        if System.is_linux():
            return [float(x) for x in System._run_command("cat /proc/loadavg").split()[:3]] # returns the system load averages for the past 1, 5, and 15 minutes as a list of floats
        elif System.is_macos():
            return [float(x) for x in System._run_command("sysctl -n vm.loadavg").strip('{}\n ').split()[:3]] # returns the system load averages for the past 1, 5, and 15 minutes as a list of floats
        else:
            raise Exception("Unsupported OS for getting system load")
    
    @staticmethod
    def get_memory_usage() -> dict:
        meminfo = System._run_command("cat /proc/meminfo")

        # We only want the following fields from meminfo:
        fields = ["MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached", "SwapTotal", "SwapFree"]

        meminfo_dict = {}
        for line in meminfo.splitlines():
            parts = line.split(':')
            if len(parts) == 2:
                key = parts[0].strip()
                if key in fields:
                    value = parts[1].strip().split()[0] # Get the numeric value, ignoring units
                    meminfo_dict[key] = int(value) # Convert to integer (kilobytes)
        return meminfo_dict

    @staticmethod
    def get_pitxu_memory_use() -> dict:

        pid = os.getpid()
        process = psutil.Process(pid)
        mem_info = process.memory_info()
        return {
            "resident_set_size": mem_info.rss, # Resident Set Size: the non-swapped physical memory the process is using.
            "virtual_memory_size": mem_info.vms, # Virtual Memory Size: the total amount of virtual memory used by the process.
            # "shared_memory": mem_info.shared, # Shared Memory: the amount of memory shared with other processes.
            # "text": mem_info.text, # Text (code): the amount of memory used by executable code.
            # "library": mem_info.lib, # Library: the amount of memory used by loaded libraries.
            # "data": mem_info.data, # Data + Stack: the amount of memory used by data and stack.
            # "dirty": mem_info.dirty # Dirty Pages: the amount of memory that is marked as dirty (modified but not yet written to disk).
        }

    @staticmethod
    def get_disk_usage() -> dict:
        df_output = System._run_command("df -h /") # Get disk usage for root partition
        lines = df_output.splitlines()
        if len(lines) < 2:
            raise Exception("Unexpected output from df command")
        
        # The second line contains the data we need
        parts = lines[1].split()
        if len(parts) < 6:
            raise Exception("Unexpected output format from df command")
        
        return {
            "filesystem": parts[0],
            "size": parts[1],
            "used": parts[2],
            "available": parts[3],
            "use_percent": parts[4],
            "mounted_on": parts[5]
        }
    
    @staticmethod
    def memory_use(scale: int = None) -> float:
        if scale is None:
            scale = System.MEGABYTES
        
        process = psutil.Process()
        usage = process.memory_info().rss 
        # Using memory_info() to check consumption. Returns bytes.
        return float(usage / scale)

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
    def _read_hardware_metric(command_args, strip_chars) -> str: #(["command","arg1", "arg2",...],'strip_chars') ** not likely to be very useful outside of vcgencmd **
        try:
            output = System._run_command(" ".join(command_args)) # runs a command w/ args and captures its output converting to UTF-8 encoded string
            metric_str = output.split("=")[1].strip().rstrip(strip_chars)
                        # split output string into a list using "="
                        # [1] selects the second element of the list
                        # strip any leading/trailing whitespace
                        # further strips specific characters (strip_chars) from result
            return metric_str # converts the cleaned-up string to float and returns it.
        except (Exception) as e: # command not found, command fails, ValueError could occur if converting cleaned string to float fails
            raise Exception(f"Error reading hardware metric: {e}")
    
    @staticmethod
    def is_linux() -> bool:
        return platform.system() == "Linux"
    
    @staticmethod
    def is_macos() -> bool:
        return platform.system() == "Darwin"
    
    @staticmethod
    def is_windows() -> bool:
        return platform.system() == "Windows"