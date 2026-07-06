import urllib.request

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

import json

class Github(PyXavi):

    # ATM it only has access to PRs
    GITHUB_TOKEN: str = None

    def __init__(self, config: Config = None, params: Dictionary = None, **kwargs):
        super(Github, self).init_pyxavi(config=config, params=params)

        self.GITHUB_TOKEN = self._xparams.get("github_token", None)

    def get_files_involved_in_pr(self, pr_url: str) -> list[str]:
        """
        Gets the list of files involved in a PR, given the PR URL.

        It uses the GitHub API to get the list of files involved in the PR.

        Args:
            pr_url (str): The URL of the PR.

        Returns:
            list[str]: The list of files involved in the PR.
        """
        if self.GITHUB_TOKEN is None:
            self._xlog.error("🛑 GITHUB_TOKEN is not set. Please set it in the .env file.")
            return []

        # Extract owner, repo and pr number from the URL
        try:
            parts = pr_url.split("/")
            owner = parts[3]
            repo = parts[4]
            pr_number = parts[6]
        except Exception as e:
            self._xlog.error(f"Error parsing PR URL: {e}")
            return []

        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
        headers = {
            "Authorization": f"Bearer {self.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            request = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(request) as response:
                data = response.read()
                
                files_info = json.loads(data)
                files_data = []
                for file_info in files_info:
                    self._log_debug(f"File in PR: {file_info['filename']}")
                    file_data = {
                        "name": file_info["filename"],
                        "status": file_info["status"],
                        "raw_url": file_info["raw_url"],
                        "contents_url": file_info["contents_url"],
                    }
                    files_data.append(file_data)
                return files_data
        except Exception as e:
            self._xlog.error(f"Error fetching PR files: {e}")
            return []
    
    def get_branch_related_to_pr(self, pr_url: str) -> str | bool:
        """
        Gets the branch name related to a PR, given the PR URL.

        It uses the GitHub API to get the branch name related to the PR.

        Args:
            pr_url (str): The URL of the PR. 
        Returns:
            str | bool: The branch name related to the PR, or False if not found.
        """
        if self.GITHUB_TOKEN is None:
            self._xlog.error("🛑 GITHUB_TOKEN is not set. Please set it in the .env file.")
            return False

        # Extract owner, repo and pr number from the URL
        try:
            parts = pr_url.split("/")
            owner = parts[3]
            repo = parts[4]
            pr_number = parts[6]
        except Exception as e:
            self._xlog.error(f"Error parsing PR URL: {e}")
            return False

        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = {
            "Authorization": f"Bearer {self.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            request = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(request) as response:
                data = response.read()
                
                pr_info = json.loads(data)
                branch_name = pr_info.get("head", {}).get("ref", None)
                if branch_name is not None:
                    self._log_debug(f"Branch related to PR: {branch_name}")
                    return branch_name
                else:
                    self._xlog.error("Branch name not found in PR info.")
                    return False
        except Exception as e:
            self._xlog.error(f"Error fetching PR info: {e}")
            return False
    
    def get_contents_from_path(self, url: str) -> list[str]:
        """
        Gets the content of the given path. 
        
        If it's a file, gets the content of the file. 
        If it's a directory, gets the content of all files in the directory.

        It uses the GitHub API to get the list of files involved in the PR.

        Args:
            url (str): The URL to retrieve from.

        Returns:
            list[str]: The list of files involved in the PR.
        """
        if self.GITHUB_TOKEN is None:
            self._xlog.error("🛑 GITHUB_TOKEN is not set. Please set it in the .env file.")
            return []

        # Extract owner, repo and rest of the path from the URL
        try:
            # Example: https://github.com/xaviarnaus/pitxu/blob/main/pitxu/lib/speech_to_text/capture_handler.py
            parts = url.split("/")
            owner = parts[3]
            repo = parts[4]
            path = "/".join(parts[7:])
        except Exception as e:
            self._xlog.error(f"Error parsing URL: {e}")
            return []

        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {
            "Authorization": f"Bearer {self.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            request = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(request) as response:
                data = response.read()
                
                files_info = json.loads(data)

                # If the path is a file, files_info will be a dict, not a list. We need to handle that case.
                if isinstance(files_info, dict):
                    self._log_debug(f"File in path: {path}/{files_info['name']}")
                    file_data = {
                        "name": files_info["name"],
                        "type": files_info["type"],
                        "url": files_info["url"],
                        "download_url": files_info["download_url"],
                        "content": files_info.get("content", None),
                    }
                    return [file_data]
                elif isinstance(files_info, list):
                    files_data = []
                    for file_info in files_info:
                        self._log_debug(f"File in path: {path}/{file_info['name']}")
                        file_data = {
                            "name": file_info["name"],
                            "type": file_info["type"],
                            "url": file_info["url"],
                            "download_url": file_info["download_url"],
                            "content": file_info.get("content", None),
                        }
                        files_data.append(file_data)
                    return files_data
        except Exception as e:
            self._xlog.error(f"Error fetching file(s) content from {url}: {e}")
            return []