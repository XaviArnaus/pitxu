import signal
from contextlib import contextmanager

class System:
    
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
        import platform
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
    def get_power_throttle(test_bin_value = None) -> list:
        """
        Returns a dictionary describing the current power throttle state of the system.
        
        https://gist.github.com/Paraphraser/17fb6320d0e896c6446fb886e1207c7e
        https://www.raspberrypi.com/documentation/computers/os.html#get_throttled
        https://forum-raspberrypi.de/forum/thread/47322-vcgencmd-get-throttled-in-python-auswerten/
        https://github.com/HarlemSquirrel/scripts/blob/master/rpi-check-throttling.py
        """
        try:
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
    def _run_command(command: str) -> str:
        from subprocess import run, PIPE, CalledProcessError

        error = None
        result = None
        try:
            result = run(command, shell=True, stdout=PIPE, stderr=PIPE)
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