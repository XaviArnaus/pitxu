from pyxavi import Config, Dictionary, TerminalColor, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi

from definitions import ROOT_DIR

import time, json, os

class Util(PyXavi):

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Util, self).init_pyxavi(config=config, params=params)
    
    # -------- The utils themselves --------

    def util_clear_displays(self):
        """
        TODO: Replace this with main.clear_displays().
        """
        try:
            from pitxu.lib.eink.eink import EinkDisplay
            from pitxu.lib.matrix_led import Max7219
            from pitxu.lib.lcd.st7789 import ST7789
            from pitxu.lib.dsi_lcd.device_wrapper import DeviceWrapper as DsiLcd

            # Delegate the run to Main
            try:
                self._xlog.debug("Clearing eInk display")
                EinkDisplay(config=self._xconfig, params=self._xparams).clear()
            except Exception as e:
                self._xlog.warning(f"Could not clear eInk display: {str(e)}")
            try:
                self._xlog.debug("Clearing LED Matrix display")
                Max7219(config=self._xconfig, params=self._xparams).clear()
            except Exception as e:
                self._xlog.warning(f"Could not clear LED Matrix display: {str(e)}")
            try:
                self._xlog.debug("Clearing LCD display")
                ST7789(config=self._xconfig, params=self._xparams).clear()
            except Exception as e:
                self._xlog.warning(f"Could not clear LCD display: {str(e)}")
            self._xlog.info("End of work.")

            try:
                self._xlog.debug("Clearing DSI LCD display")
                DsiLcd(config=self._xconfig, params=self._xparams).clear()
            except Exception as e:
                self._xlog.warning(f"Could not clear DSI LCD display: {str(e)}")
            self._xlog.info("End of work.")

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack())

    def util_query_sound_devices(self):
        try:
            import sounddevice

            # Delegate the run to Main
            self._xlog.debug("Querying SoundDevice")
            print()
            print(sounddevice.query_devices())
            print()
            self._xlog.info("End of work.")

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack()) 

    def util_battery_status(self):
        try:

            # Delegate the run to Main
            from pitxu.lib.ups.ups import UPS
            ups = UPS(config=self._xconfig, params=self._xparams)
            voltage, capacity = ups.read_voltage_and_capacity()
            pld_state = ups.get_pld_state()
            self._xlog.info(f"Battery voltage: {voltage:.2f} V")
            self._xlog.info(f"Battery capacity: {capacity:.2f} %")
            self._xlog.info(f"Power Loss/Adapter Failure State: {'FAIL' if pld_state == 0 else 'OK'}")
            self._xlog.info("End of work.")
            ups.close()

        except RuntimeError as e:
            print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
        except Exception:
            print(full_stack())
