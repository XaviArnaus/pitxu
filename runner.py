import os, time
from dotenv import load_dotenv
import importlib.metadata
import sounddevice

import logging

from pyxavi import TerminalColor, Config, Logger, Dictionary, full_stack, Stopwatch

from pitxu.lib.utils.config_loader import ConfigLoader
from pitxu.lib.eink import EinkDisplay
from pitxu.lib.matrix_led import Max7219

from definitions import ROOT_DIR, CONFIG_DIR

from pitxu.main import Main


def load_environment():
    """
    Loads the environment

    This means to load the environment vars from the .env file and also
    any other parameter related to the environment.
    """
    load_dotenv()


def load_logger(config: Config, loglevel: int = None) -> logging:

    if loglevel is not None:
        # Lets first merge the config with the new value
        logger_config = config.get("logger")
        logger_config["loglevel"] = loglevel
        logger_config["stdout"]["active"] = True
        config.merge_from_dict(parameters={"logger": logger_config})

    return Logger(config=config, base_path=ROOT_DIR).get_logger()

def run():
    try:
        # Instantiating
        load_environment()
        config = ConfigLoader.load_config_files()
        logger = load_logger(config=config)
        parameters = Dictionary({
            "base_path": ROOT_DIR,
            "api_key": os.getenv("API_KEY", None),
            "app_version": importlib.metadata.version('pitxu')
        })

        # Delegate the run to Main
        logger.debug("Starting Main run")
        main = Main(config=config, params=parameters)
        main.run()
        logger.info("End of the Main run")


    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack()) 

def clear_displays():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        logger.debug("Clearing eInk display")
        EinkDisplay(config=config, params=parameters).clear()
        logger.debug("Clearing LED Matrix display")
        Max7219(config=config, params=parameters).clear()
        logger.info("End of work.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def test_switch_and_led():
    try:
        # Instantiating
        config, logger, parameters = _initialize()
        logger.debug("Testing GPIO Switch and LED")

        # This component in special needs the Shared Memory
        # Initialize shared memory
        from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
        shared_memory = SharedMemoryManager(config=config, params=parameters)
        shared_memory.initialize_new_shared_memory_gpio_buttons()
        shared_memory.initialize_new_shared_memory_gpio_leds()

        from gpiozero import LED, Button
        led = LED(16)
        led.on()
        time.sleep(1)

        # Delegate the run to Main
        from pitxu.lib.gpio.switch_and_led import SwitchAndLed
        switch_and_led = SwitchAndLed(config=config, params=parameters)

        logger.debug("Turning Blue LED ON for 2 seconds")
        switch_and_led.set_led_blue_on()
        time.sleep(2)

        logger.debug("Waiting for Mute Toggle to be turned ON, or 5 seconds timeout")
        timeout = time.time() + 5  # 5 seconds from now

        while time.time() < timeout:
            if switch_and_led.update_mute_toggle_state_if_pressed():
                logger.debug("Mute Toggle is ON")
                break

        logger.debug("Turning Blue LED OFF")
        switch_and_led.set_led_blue_off()

        # Clean up Shared Memory
        shared_memory.clean_shared_memory()

        logger.info("End of work.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def test_matrix():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        logger.debug("Testing LED Matrix display")
        Max7219(config=config, params=parameters).test()
        logger.debug("Pausing 2 seconds to let it show")
        time.sleep(2)
        logger.info("End of work.")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack()) 

def query_sound_devices():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        logger.debug("Querying SoundDevice")
        print(sounddevice.query_devices())
        logger.info("End of work.")


    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack()) 

def _initialize():
    load_environment()
    config = ConfigLoader.load_config_files()
    logger = load_logger(config=config)
    parameters = Dictionary({
        "base_path": ROOT_DIR,
        "api_key": os.getenv("API_KEY", None),
        "app_version": importlib.metadata.version('pitxu')
    })

    return config, logger, parameters

if __name__ == '__main__':
    run()