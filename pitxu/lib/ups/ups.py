from gpiozero import InputDevice, Button
import sys
import struct
from pathlib import Path
from subprocess import check_output, CalledProcessError, call
import smbus2

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

class UPS(PyXavi):
    '''
    Class to manage an Uninterruptible Power Supply (UPS)
    '''

    CHG_ONOFF_PIN: int = None
    PLD_BUTTON: Button = None
    bus: smbus2.SMBus = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super().init_pyxavi(config=config, params=params)

        # Constants
        self.CHG_ONOFF_PIN = 16 # pinctrl get 16
        self.PLD_BUTTON = Button(6) # down = fail, up = pass
        self.bus = smbus2.SMBus(1) # i2cdetect -y 1

    def read_voltage_and_capacity(self):
        address = 0x36 # i2cget -y 1 0x36 ...
        voltage_read = self.bus.read_word_data(address, 2) # 0x02 w
        capacity_read = self.bus.read_word_data(address, 4) # 0x04 w
        voltage_swapped = struct.unpack("<H", struct.pack(">H", voltage_read))[0] # big endian to little endian
        voltage = voltage_swapped * 1.25 / 1000 / 16 # convert to understandable voltage
        capacity_swapped = struct.unpack("<H", struct.pack(">H", capacity_read))[0] # big endian to little endian
        capacity = capacity_swapped / 256 # convert to 1-100% scale
        return voltage, capacity

    def get_pld_state(self):
        if self.PLD_BUTTON.is_pressed:
            return 0 # power loss/adapter failure
        else:
            return 1 # power ok

    def is_power_cable_connected(self) -> bool:
        pld_state = self.get_pld_state()
        return pld_state == 1

    def read_hardware_metric(self, command_args, strip_chars): #(["command","arg1", "arg2",...],'strip_chars') ** not likely to be very useful outside of vcgencmd **
        try:
            output = check_output(command_args).decode("utf-8") # runs a command w/ args and captures its output converting to UTF-8 encoded string
            metric_str = output.split("=")[1].strip().rstrip(strip_chars)
                        # split output string into a list using "="
                        # [1] selects the second element of the list
                        # strip any leading/trailing whitespace
                        # further strips specific characters (strip_chars) from result
            return float(metric_str) # converts the cleaned-up string to float and returns it.
        except (CalledProcessError, ValueError) as e: # command not found, command fails, ValueError could occur if converting cleaned string to float fails
            print(f"Error reading hardware metric: {e}")
            return None

    def read_cpu_volts(self): 
        return self.read_hardware_metric(["vcgencmd", "pmic_read_adc", "VDD_CORE_V"], 'V') # return current cpu voltage

    def read_cpu_amps(self):
        return self.read_hardware_metric(["vcgencmd", "pmic_read_adc", "VDD_CORE_A"], 'A') # reurn current cpu amperage

    def read_cpu_temp(self):
        return self.read_hardware_metric(["vcgencmd", "measure_temp"], "'C") # return current cpu temp

    def read_input_voltage(self):
        return self.read_hardware_metric(["vcgencmd", "pmic_read_adc", "EXT5V_V"], 'V') # return input voltage

    def get_fan_rpm(self):
        try:
            sys_devices_path = Path('/sys/devices/platform/cooling_fan') 
            fan_input_files = list(sys_devices_path.rglob('fan1_input')) # scan path for fan1_input (sometimes its under hwmon2, sometimes hwmon3...)
            if not fan_input_files: # nothing found?
                return "No fan?"
            with open(fan_input_files[0], 'r') as file: # file found, opened
                rpm = file.read().strip() # read value and strip anything else
            return f"{rpm} RPM" # return "xxxx RPM"
        except FileNotFoundError: 
            return "Fan RPM file not found"
        except PermissionError:
            return "Permission denied accessing the fan RPM file"
        except Exception as e:
            return f"Unexpected error: {e}"

    def power_consumption_watts(self):
        output = check_output(['vcgencmd', 'pmic_read_adc']).decode("utf-8") # gets a printout of all rpi5 voltages/amperages, converts output from binary to utf-8 string
        lines = output.split('\n') # splits the output based on newline
        amperages = {} # initialize amps dictionary
        voltages = {} # initialize volts dictionary
        for line in lines: # go through all lines one by one
            cleaned_line = line.strip() # removes any leading or trailing whitespace from the line
            if cleaned_line: # checks if the line is not empty after stripping
                parts = cleaned_line.split(' ') # split into parts based on spaces
                label, value = parts[0], parts[-1] # label = V or A, value = reading
                val = float(value.split('=')[1][:-1]) # convert value to float
                short_label = label[:-2] # 
                if label.endswith('A'): # If the label ends with 'A', it's an amperage value and is added to the amperages dictionary
                    amperages[short_label] = val
                else: # Otherwise, it's added to the voltages dictionary
                    voltages[short_label] = val
        wattage = sum(amperages[key] * voltages[key] for key in amperages if key in voltages) # iterates over each key in amperages
        return wattage
    
    def close(self):
        '''
        Closes the UPS resources.
        '''
        if self.bus is not None:
            self.bus.close()
            self.bus = None
        
        if self.PLD_BUTTON is not None:
            self.PLD_BUTTON.close()
            self.PLD_BUTTON = None

