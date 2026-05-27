from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.utils.wget import Wget
from pitxu.lib.utils.github import Github

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.interaction.interaction import Interaction

import logging

class WorldGithub(PyXavi, Command):

    wget: Wget = None
    github: Github = None

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(WorldGithub, self).init_pyxavi(config=config, params=params)

        self.wget = Wget(config=self._xconfig, params=self._xparams)
        self.github = Github(config=self._xconfig, params=self._xparams)
    
    def get_files_involved_in_pr(self, pr_url: str) -> list[str]:
        """
        Gets the list of files involved in a PR, given the PR URL.

        It uses the GitHub API to get the list of files involved in the PR.

        Args:
            pr_url (str): The URL of the PR.

        Returns:
            list[str]: The list of files involved in the PR.
        """
        github = Github(config=self._xconfig, params=self._xparams)
        return github.get_files_involved_in_pr(pr_url)

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
        # COMMENTED: Now we get the RAW url directly from the GitHub API, so we don't need to convert it ourselves
        # raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        # self._xlog.debug(f"Converted GitHub URL to raw URL: {raw_url}")
        return self.wget.get(url)
    
    # def get_pull_request_content_from_github_project(self, account: str, repo: str, pull_request_number: int) -> str | bool:
    #     '''
    #     Get the content of a pull request from a GitHub project.

    #     Args:
    #         account (str): The GitHub account name.
    #         repo (str): The GitHub repository name.
    #         pull_request_number (int): The pull request number.
    #     Returns:
    #         str | bool: The content of the pull request as a string, or False if not found.
    #     '''

    #     # Construct the URL for the pull request
    #     url = f"https://github.com/{account.lower()}/{repo.lower()}/pull/{pull_request_number}"
    #     self._xlog.debug(f"Constructed GitHub API URL for pull request: {url}")
    #     return self.get_content_from_url(url)
    
    def get_file_from_github_branch(self, account: str, repo: str, branch: str, file_path: str, file_name: str) -> str | bool:
        '''
        Get the content of a file from a specific branch in a GitHub repository.

        Args:
            account (str): The GitHub account name.
            repo (str): The GitHub repository name.
            branch (str): The branch name.
            file_path (str): The path to the file in the repository.
            file_name (str): The name of the file in the repository.
        Returns:
            str | bool: The content of the file as a string, or False if not found.
        '''
        url = f"https://github.com/{account.lower()}/{repo.lower()}/blob/{branch.lower()}/{file_path.lower()}/{file_name.lower()}"
        self._xlog.debug(f"Constructed GitHub URL for file: {url}")
        return self.wget.get(url)
    
    def callback_get_files_involved_in_pr(self, log: logging, interaction: Interaction, value: any, args: dict = None) -> None:
        
        try:
            files = list(value)
            text = "\n".join([f"📄 {file.get('name', '')}" for file in files])
            interaction.show_text_block_on_foreground_while_speaking(text=text)
        except Exception as e:
            log.error(f"🛑 Error showing weather forecast for today on eInk: {e}")
            log.error(full_stack())
    
    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.get_files_involved_in_pr,
                self.get_raw_code_from_github_url,
                # self.get_pull_request_content_from_github_project,
                self.get_file_from_github_branch]

    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "get_files_involved_in_pr":
            return self.callback_get_files_involved_in_pr
        return self.default_empty_callback