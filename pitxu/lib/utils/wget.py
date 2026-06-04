from urllib import response
import urllib.request

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

class Wget(PyXavi):

    def __init__(self, config: Config = None, params: Dictionary = None, **kwargs):
        super(Wget, self).init_pyxavi(config=config, params=params)
    
    def _get(self, url: str) -> str | bool:
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
    
    def get(self, url: str, retries: int = 1) -> str | bool:
        '''
        Get the content from the given URL.

        Args:
            url (str): The URL to get the content from.


        Returns:
            str | bool: The content as a string, or False if not found.
        '''
        original_retries = retries
        retries = -1
        while retries < 1:
            retries += 1
            self._xlog.debug(f"Getting content from URL: {url}. Try #{retries}")

            wget = Wget(config=self._xconfig, params=self._xparams)
            result = wget._get(url)
        
            if result is not False and len(result) > 0:
                self._xlog.debug(f"Got content from URL [{url}]")
                return result
        
        self._xlog.error(f"🛑 Error getting content from URL {url}: No results found after {original_retries} retries.")
        return False