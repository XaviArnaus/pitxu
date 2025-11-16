import requests

from pyxavi import Config, Logger
from pitxu.lib.utils.config_loader import ConfigLoader

class ApiRequest:
    
    def do(url: str):
        '''Sends an API request and returns the response.'''

        config: Config = ConfigLoader.load_config_files()
        logger = Logger(config=config, base_path="").get_logger()

        logger.debug(f"Making a request to: {url}")
        try:
            response = requests.get(url, headers={"User-Agent": "pitxu-agent/1.0"})
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Response: {data}")
            return data
        except requests.exceptions.HTTPError as err:
            logger.error(f"HTTP error occurred: {err}")
        except Exception as err:
            logger.error(f"Other error occurred: {err}")