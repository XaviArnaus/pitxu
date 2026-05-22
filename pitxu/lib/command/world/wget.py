from pyxavi import Config, Dictionary
from pitxu.lib.utils.wget import Wget

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command

class WorldWget(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(WorldWget, self).init_pyxavi(config=config, params=params)

    def get_content_from_url(self, url: str) -> str | bool:
        '''
        Get the content from the given URL.

        Args:
            url (str): The URL to get the content from.


        Returns:
            str | bool: The content as a string, or False if not found.
        '''
        retries = -1
        while retries < 1:
            retries += 1
            self._xlog.debug(f"Getting content from URL: {url}. Try #{retries}")

            wget = Wget(config=self._xconfig, params=self._xparams)
            result = wget.get(url)
        
            if result is not False and len(result) > 0:
                self._xlog.debug(f"Got content from URL [{url}]")
                return result
        
        self._xlog.error(f"🛑 Error getting content from URL {url}: No results found after retries.")
        return False
    
    def get_raw_code_from_github_url(self, url: str) -> str | bool:
        '''
        Get the raw code content from a given GitHub URL.

        Args:
            url (str): The GitHub URL to get the raw code content from.
        Returns:
            str | bool: The raw code content as a string, or False if not found.
        '''
        if "github.com" not in url:
            self._xlog.error(f"URL {url} is not a GitHub URL.")
            return False
        
        # Convert the GitHub URL to a raw content URL
        raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        self._xlog.debug(f"Converted GitHub URL to raw URL: {raw_url}")
        return self.get_content_from_url(raw_url)
    
    def get_pull_request_content_from_github_project(self, account: str, repo: str, pull_request_number: int) -> str | bool:
        '''
        Get the content of a pull request from a GitHub project.

        Args:
            account (str): The GitHub account name.
            repo (str): The GitHub repository name.
            pull_request_number (int): The pull request number.
        Returns:
            str | bool: The content of the pull request as a string, or False if not found.
        '''

        # Construct the URL for the pull request
        url = f"https://github.com/{account}/{repo}/pull/{pull_request_number}"
        self._xlog.debug(f"Constructed GitHub API URL for pull request: {url}")
        return self.get_content_from_url(url)
    
    def get_file_from_github_branch(self, account: str, repo: str, branch: str, file_path: str) -> str | bool:
        '''
        Get the content of a file from a specific branch in a GitHub repository.

        Args:
            account (str): The GitHub account name.
            repo (str): The GitHub repository name.
            branch (str): The branch name.
            file_path (str): The path to the file in the repository.
        Returns:
            str | bool: The content of the file as a string, or False if not found.
        '''
        url = f"https://github.com/{account}/{repo}/blob/{branch}/{file_path}"
        self._xlog.debug(f"Constructed GitHub URL for file: {url}")
        return self.get_content_from_url(url)

    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_content_from_url,
                self.get_raw_code_from_github_url,
                self.get_pull_request_content_from_github_project,
                self.get_file_from_github_branch]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        return self.default_empty_callback