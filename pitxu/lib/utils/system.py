

class System:
    
    @staticmethod
    def get_dsi_backlight_status():
        return "0" == System._run_command("cat /sys/class/backlight/11-0045/bl_power")

    @staticmethod
    def set_dsi_backlight_on():
        return System._run_command("sudo -E sh -c 'echo 0 > /sys/class/backlight/11-0045/bl_power'")
    
    @staticmethod
    def set_dsi_backlight_off():
        return System._run_command("sudo -E sh -c 'echo 1 > /sys/class/backlight/11-0045/bl_power'")
    
    @staticmethod
    def get_default_network_interface():
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
    def get_cpu_temperature():
        return round(int(System._run_command("cat /sys/class/thermal/thermal_zone*/temp")) / 1000, 1)
    
    @staticmethod
    def get_cpu_fan_speed():
        return round(int(System._run_command("cat /sys/class/hwmon/hwmon*/fan1_input")) / 1000, 1)
    
    @staticmethod
    def get_cpu_volts() -> float: 
        return System._read_hardware_metric(["vcgencmd", "pmic_read_adc", "VDD_CORE_V"], 'V') # return current cpu voltage

    @staticmethod
    def get_cpu_amps() -> float:
        return System._read_hardware_metric(["vcgencmd", "pmic_read_adc", "VDD_CORE_A"], 'A') # reurn current cpu amperage

    @staticmethod
    def get_cpu_temp() -> float:
        return System._read_hardware_metric(["vcgencmd", "measure_temp"], "'C") # return current cpu temp

    @staticmethod
    def get_input_voltage() -> float:
        return System._read_hardware_metric(["vcgencmd", "pmic_read_adc", "EXT5V_V"], 'V') # return input voltage
    
    @staticmethod
    def get_power_throttle_state() -> int:
        try:
            map = {
                0:"currently under-voltage",
                1:"ARM frequency currently capped",
                2:"currently throttled",
                3:"soft temperature limit reached",
                16:"under-voltage has occurred since last reboot",
                17:"ARM frequency capping has occurred since last reboot",
                18:"throttling has occurred since last reboot",
                19:"soft temperature reached since last reboot"
            }

            output = System._read_hardware_metric(["vcgencmd", "get_throttled"])
            throttle_str = output.split("=")[1].strip() # split output string into a list using "=" and select the second element, then strip any leading/trailing whitespace
            code = int(throttle_str, 16) # convert the cleaned-up string to an integer (base 16) and return it.
            return {
                "code": code,
                "description": map.get(code, "Unknown throttle state")
            }
        except Exception as e:
            raise Exception(f"Error reading throttle state: {e}")

    @staticmethod
    def _run_command(command):
        import subprocess
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise Exception(f"Command failed: {result.stderr.decode()}")
        return result.stdout.decode().strip()
    
    @staticmethod
    def _read_hardware_metric(command_args, strip_chars): #(["command","arg1", "arg2",...],'strip_chars') ** not likely to be very useful outside of vcgencmd **
        try:
            output = System._run_command(" ".join(command_args)) # runs a command w/ args and captures its output converting to UTF-8 encoded string
            metric_str = output.split("=")[1].strip().rstrip(strip_chars)
                        # split output string into a list using "="
                        # [1] selects the second element of the list
                        # strip any leading/trailing whitespace
                        # further strips specific characters (strip_chars) from result
            return float(metric_str) # converts the cleaned-up string to float and returns it.
        except (Exception) as e: # command not found, command fails, ValueError could occur if converting cleaned string to float fails
            raise Exception(f"Error reading hardware metric: {e}")