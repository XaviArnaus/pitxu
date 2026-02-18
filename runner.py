import os
from dotenv import load_dotenv
import importlib.metadata
import sounddevice
import asyncio
import logging
import argparse

from pyxavi.terminal_color import TerminalColor
from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary
from pyxavi.debugger import full_stack

from pitxu.lib.utils.config_loader import ConfigLoader

from definitions import ROOT_DIR, CONFIG_DIR


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

def parse_arguments() -> dict:

    parser = argparse.ArgumentParser(description='Run the Pitxu application with optional arguments.')
    parser.add_argument(
        '-t', '--test', 
        type=str, 
        help='Run a specific test instead of the main application. Valid values: "eink_multiline", "matrix", "lcd", "mouth_in_lcd", "thinking_in_lcd", "sound_out", "query_sound_devices", "battery_status", "send_email", "send_to_printer", "test_lists".')
    args = parser.parse_args()

    arguments = {
        'test': args.test
    }

    return arguments

def tests():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        from pitxu.test import Test
        import inspect

        # Delegate the run to the tests
        logger.debug("Starting tests run")

        # Ensure the arguments are logged if they exist
        if parameters.key_exists("arguments.test") and parameters.get("arguments.test") is not None:

            logger.debug(f"Received arguments: {parameters.get('arguments')}")
            test_name = parameters.get("arguments.test")
            test_arguments = parameters.get("arguments") # Remove the test name from the arguments to pass only the relevant ones
            test_arguments.pop("test", None)

            # Delegate the run to the appropriate test function
            logger.debug(f"Starting test: [{test_name}]")
            test = Test(config=config, params=parameters)
            test_function = getattr(test, f"test_{test_name}", None)
            if test_function and callable(test_function):
                test_function(**test_arguments)
            else:
                logger.warning(f"Test function not found: [{test_name}]")
        
        else:
            print("\nNo arguments received, choose one from:")
            # test = Test(config=config, params=parameters)
            for method_name, method in inspect.getmembers(Test, predicate=inspect.isfunction):
                if method_name.startswith("test_") and callable(method):
                    print(f"- {method_name[5:]}")
            print("\nFor example, to run the email test, run: \n    poetry run test -t email")
            
        logger.info("End of the tests run")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def run():
    try:
        # Instantiating
        config, logger, parameters = _initialize()

        from pitxu.main import Main

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
    """
    TODO: Replace this with main.clear_displays().
    """
    try:
        from pitxu.lib.eink.eink import EinkDisplay
        from pitxu.lib.matrix_led import Max7219
        from pitxu.lib.lcd.st7789 import ST7789
        from pitxu.lib.dsi_lcd.device_wrapper import DeviceWrapper as DsiLcd
        # Instantiating
        config, logger, parameters = _initialize()

        # Delegate the run to Main
        try:
            logger.debug("Clearing eInk display")
            EinkDisplay(config=config, params=parameters).clear()
        except Exception as e:
            logger.warning(f"Could not clear eInk display: {str(e)}")
        try:
            logger.debug("Clearing LED Matrix display")
            Max7219(config=config, params=parameters).clear()
        except Exception as e:
            logger.warning(f"Could not clear LED Matrix display: {str(e)}")
        try:
            logger.debug("Clearing LCD display")
            ST7789(config=config, params=parameters).clear()
        except Exception as e:
            logger.warning(f"Could not clear LCD display: {str(e)}")
        logger.info("End of work.")

        try:
            logger.debug("Clearing DSI LCD display")
            DsiLcd(config=config, params=parameters).clear()
        except Exception as e:
            logger.warning(f"Could not clear DSI LCD display: {str(e)}")
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
        print()
        print(sounddevice.query_devices())
        print()
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

def _initialize() -> tuple[Config, Logger, Dictionary]:
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
        "app_version": importlib.metadata.version('pitxu'),
        "arguments": parse_arguments()
    })

    return config, logger, parameters

if __name__ == '__main__':
    run()