import os, time
from dotenv import load_dotenv
import importlib.metadata
import sounddevice
import asyncio
import logging

from pyxavi.terminal_color import TerminalColor
from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary
from pyxavi.debugger import full_stack

from pitxu.lib.utils.config_loader import ConfigLoader
from pitxu.lib.eink import EinkDisplay, Macros, EinkCanvas
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
        asyncio.run(main.run())
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

def test_eink_multiline():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        logger.debug("Testing eInk display multiline text")
        eink = EinkDisplay(config=config, params=parameters)
        macros = Macros(config=config, params=parameters)
        macros.arbitrary_text_with_icon(
            display = eink, 
            text = "This is a test", 
            icon = "⚠️", 
            font_size = EinkCanvas.FONT_BIG_SIZE, 
            header = "Single Line Test", 
            font_header_size = EinkCanvas.FONT_BIG_SIZE)
        logger.debug("Pausing 2 seconds to let it show")
        time.sleep(2)
        macros.arbitrary_text_with_icon(
            display = eink, 
            text = "This is a test of multiline text rendering on the eInk display.", 
            icon = "⚠️", 
            font_size = EinkCanvas.FONT_BIG_SIZE, 
            header = "Multiline Test", 
            font_header_size = EinkCanvas.FONT_BIG_SIZE)
        logger.debug("Pausing 2 seconds to let it show")
        time.sleep(2)
        logger.debug("Clearing eInk display")
        eink.clear()
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

def battery_status():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        from pitxu.lib.ups.ups import UPS
        ups = UPS(config=config, params=parameters)
        voltage, capacity = ups.read_voltage_and_capacity()
        pld_state = ups.get_pld_state()
        logger.info(f"Battery voltage: {voltage:.2f} V")
        logger.info(f"Battery capacity: {capacity:.2f} %")
        logger.info(f"Power Loss/Adapter Failure State: {'FAIL' if pld_state == 0 else 'OK'}")
        logger.info("End of work.")
        ups.close()

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
        "mail": {
            "user_address": os.getenv("EMAIL_USERADDRESS", None),
            "user_name": os.getenv("EMAIL_USERNAME", None),
            "password": os.getenv("EMAIL_PASSWORD", None),
        },
        "app_version": importlib.metadata.version('pitxu')
    })

    return config, logger, parameters

if __name__ == '__main__':
    run()