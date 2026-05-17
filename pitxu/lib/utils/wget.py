from urllib import response
import urllib.request

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

class Wget(PyXavi):

    def __init__(self, config: Config = None, params: Dictionary = None, **kwargs):
        super(Wget, self).init_pyxavi(config=config, params=params)
    
    def get(self, url: str) -> str | bool:
        '''Retrieves the content from the given URL and returns it as a text.'''

        self._xlog.debug(f"Retrieving content from URL: {url}")
        try:
            with urllib.request.urlopen(url) as response:
                if response.status != 200:
                    self._xlog.error(f"HTTP error when getting content from URL {url}: Status code {response.status}")
                    return False
                data: bytes = response.read()
                data_str = data.decode('utf-8')
                self._xlog.debug(f"Response: {data_str}")
                return data_str
        except urllib.error.HTTPError as err:
            self._xlog.error(f"HTTP error occurred: {err}")
        except Exception as err:
            self._xlog.error(f"Other error occurred: {err}")
        return False