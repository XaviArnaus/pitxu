import os
from dotenv import load_dotenv

import glob
import logging

from pyxavi.terminal_color import TerminalColor
from pyxavi.config import Config
from pyxavi.logger import Logger
from pyxavi.debugger import full_stack

from definitions import ROOT_DIR, CONFIG_DIR

from pitxu.lib.chatbot.geminai_chatbot import GeminaiChatbot
from pitxu.lib.eink.display import EinkDisplay


def load_environment():
    """
    Loads the environment

    This means to load the environment vars from the .env file and also
    any other parameter related to the environment.
    """
    load_dotenv()


def load_config_files() -> Config:
    """
    Loads all configs existing in CONFIG_DIR.

    This is a merge-all-to-one approach, so may be the case that later objects
        overwrite older ones
    """
    config_files = glob.glob(os.path.join(CONFIG_DIR, "*.yaml"))

    # Yes, technically we're loading main.yaml twice
    config = Config(filename=os.path.join(CONFIG_DIR, "main.yaml"))
    for file in config_files:
        config.merge_from_file(filename=os.path.join(CONFIG_DIR, file))

    return config


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
        config = load_config_files()
        logger = load_logger(config=config)
        parameters = {
            "base_path": ROOT_DIR,
            "api_key": os.getenv("API_KEY")
        }

        # Initialise eInk Display
        display = EinkDisplay(config=config, params=parameters)
        display.test()

        # Initialise Chatbot
        logger.debug("Initialising the Chatbot Client")
        chatbot = GeminaiChatbot(config=config, params=parameters)

        # Here we start with the Chatbot
        question = "com es fa un gelat?"
        answer = chatbot.ask(question)

        # Manage the answer
        print(answer)


    except RuntimeError as e:
        print(TerminalColor.RED_BRIGHT + str(e) + TerminalColor.END)
    except Exception:
        print(full_stack()) 