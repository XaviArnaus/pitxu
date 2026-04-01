import os
from dotenv import load_dotenv
import importlib.metadata
import asyncio
import logging
import argparse

from pyxavi.terminal_color import TerminalColor
from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.dictionary import Dictionary
from pyxavi.debugger import full_stack

from pitxu.lib.utils.config_loader import ConfigLoader

from definitions import ROOT_DIR


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
        help='Run a specific test instead of the main application.')
    parser.add_argument(
        '-u', '--util', 
        type=str, 
        help='Run a specific util instead of the main application.')
    args = parser.parse_args()

    arguments = {}
    if args.test:
        arguments["test"] = args.test
    if args.util:
        arguments["util"] = args.util

    return arguments

def tests():
    try:
        # Instantiating
        config, logger, parameters = initialize()

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

def utils():
    try:
        # Instantiating
        config, logger, parameters = initialize()

        from pitxu.util import Util
        import inspect

        # Delegate the run to the utils
        logger.debug("Starting utils run")

        # Ensure the arguments are logged if they exist
        if parameters.key_exists("arguments.util") and parameters.get("arguments.util") is not None:

            logger.debug(f"Received arguments: {parameters.get('arguments')}")
            util_name = parameters.get("arguments.util")
            util_arguments = parameters.get("arguments") # Remove the util name from the arguments to pass only the relevant ones
            util_arguments.pop("util", None)

            # Delegate the run to the appropriate util function
            logger.debug(f"Starting util: [{util_name}]")
            util = Util(config=config, params=parameters)
            util_function = getattr(util, f"util_{util_name}", None)
            if util_function and callable(util_function):
                util_function(**util_arguments)
            else:
                logger.warning(f"Util function not found: [{util_name}]")
        
        else:
            print("\nNo arguments received, choose one from:")
            for method_name, method in inspect.getmembers(Util, predicate=inspect.isfunction):
                if method_name.startswith("util_") and callable(method):
                    print(f"- {method_name[5:]}")
            print("\nFor example, to run the clear_displays util, run: \n    poetry run util -u clear_displays")
            
        logger.info("End of the utils run")

    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

def run():
    try:
        # Instantiating
        config, logger, parameters = initialize()

        # Discover which execution mode we are in, and log it.
        # Get the execution mode. Ensure that we have an accepted value only.
        # Default to the normal (local) execution mode.
        exec_mode = config.get("app.execution_mode", "local")
        if exec_mode not in ["local", "public", "client", "server"]:
            logger.error(f"🛑 Invalid execution mode [{exec_mode}] in config. Accepted values are: local, public, client, server. Defaulting to 'local' mode.")
            exec_mode = "local"
        parameters.set("execution_mode", exec_mode)

        # For "local" and "public" execution modes, we run the normal Main. 
        # There is an IF in the Main to check if the server should be initialized or not.
        if exec_mode in ["local", "public"]:
            from pitxu.main import Main
            logger.info(f"🚀 Starting in {exec_mode.upper()} execution mode")
            main = Main(config=config, params=parameters)
            asyncio.run(main.run())
            logger.info("End of the Main run")

        elif exec_mode == "client":
            from pitxu.main_client_ptt import MainClientPTT
            logger.info("🚀 Starting in CLIENT execution mode")
            main_client = MainClientPTT(config=config, params=parameters)
            asyncio.run(main_client.run())
            logger.info("End of the Main Client run")

        elif exec_mode == "server":
            logger.error("🛑 SERVER execution mode is not implemented yet. Please run in 'local' or 'client' mode for now.")


    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack())

# def patch_time():
#     """
#     Patch the time.sleep function for better performance on Linux systems.
#     https://stackoverflow.com/a/66350772
#     """
#     import platform
#     if platform.system() == "Linux":
#         Xtime.patch_time()

def initialize() -> tuple[Config, Logger, Dictionary]:
    load_environment()
    # patch_time()
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