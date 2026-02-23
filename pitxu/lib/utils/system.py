

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
    def get_cpu_temperature() -> float:
        return round(int(System._run_command("cat /sys/class/thermal/thermal_zone*/temp")) / 1000, 1)
    
    @staticmethod
    def get_cpu_fan_speed() -> float:
        return round(int(System._run_command("cat /sys/class/hwmon/hwmon*/fan1_input")) / 1000, 1)
    
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
                0: "Surrently under-voltage",
                1: "ARM frequency currently capped",
                2: "Currently throttled",
                3: "Soft temperature limit reached",
                16: "Under-voltage has occurred since last reboot",
                17: "ARM frequency capping has occurred since last reboot",
                18: "Throttling has occurred since last reboot",
                19: "Soft temperature reached since last reboot"
            }

            if test_bin_value is not None:
                throttle_bin = test_bin_value
            else:
                throttle_str = System._read_hardware_metric(["vcgencmd", "get_throttled"], '') # no characters to strip
                throttle_bin = bin(int(throttle_str, 16)) # convert the cleaned-up string to an integer (base 16) and then to binary

            report = []
            for bit, description in map.items():
                if len(throttle_bin) > bit and throttle_bin[0 - bit - 1] == '1':
                    report.append({"code": bit, "description": description})
            return report
        except Exception as e:
            raise Exception(f"Error reading throttle state: {e}")

    @staticmethod
    def _run_command(command) -> str:
        import subprocess
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise Exception(f"Command failed: {result.stderr.decode()}")
        return result.stdout.decode().strip()
    
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