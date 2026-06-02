from pyxavi import Config, Dictionary, TerminalColor, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi

from definitions import ROOT_DIR

import time, json, os

class Util(PyXavi):

    VERBOSE_DEBUG: bool = False

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
    
    def util_migrate_db(self):
        from pitxu.lib.utils.memory import Memory
        memory = Memory(config=self._xconfig, params=self._xparams)
        memory.db.migrate_db()
        memory.close()
    
    def util_import_old_memory(self):
        """
        This is a one-time utility to import the old memory from the file-based storage to the new SQLite-based storage.
        After running this, you can delete the old memory file and this utility function.
        """
        from pitxu.lib.utils.memory import Memory
        from pyxavi import Storage, dd

        # Initialize the new Memory (which uses SQLite)
        memory = Memory(config=self._xconfig, params=self._xparams)

        # Path to the old memory file
        old_memory_path = os.path.join(
            self._xconfig.get("storage.path", "storage/"),
            self._xconfig.get("memory.file.path", "memory.yaml"))

        if not os.path.exists(old_memory_path):
            self._xlog.error(f"Old memory file not found at {old_memory_path}. Cannot import.")
            return
        
        self._xlog.info(f"Importing old memory from {old_memory_path} to SQLite database.")

        try:
            old_memory_entries = dict(Storage(filename=old_memory_path).get("entries", {}))
            counter_succeeded = 0
            counter_failed = 0
            for key, entry in old_memory_entries.items():
                summary = entry.get("summary", "")
                content = entry.get("content", "")
                created_at = entry.get("created_at", None)
                if summary and content:
                    created_entry = memory.create_short_memory_entry(
                        summary=summary, 
                        content=content, 
                        created_at=created_at)
                    self._xlog.debug(f"Imported memory entry with ID {created_entry['id']} from old memory.")
                    counter_succeeded += 1
                else:
                    self._xlog.warning(f"Skipping invalid memory entry in old memory: {entry}")
                    counter_failed += 1
            self._xlog.info(f"Old memory import complete. Imported {counter_succeeded} entries, {counter_failed} failed.")
        except Exception as e:
            self._xlog.error(f"Unexpected error during old memory import: {str(e)}")
            self._xlog.debug(full_stack())
        finally:
            memory.close()